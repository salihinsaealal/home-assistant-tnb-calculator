"""Sensor platform for TNB Calculator integration."""
import logging
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    CALENDARIFIC_BASE_URL,
    CALENDARIFIC_HOLIDAYS_ENDPOINT,
    CONF_CALENDARIFIC_API_KEY,
    CONF_COUNTRY,
    CONF_EXPORT_ENTITY,
    CONF_IMPORT_ENTITY,
    CONF_YEAR,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    BASE_SENSOR_TYPES,
    TOU_SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)

PEAK_DAYS = {0, 1, 2, 3, 4}  # Monday to Friday
PEAK_START = time(14, 0)  # 2PM
PEAK_END = time(22, 0)    # 10PM

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_IMPORT_ENTITY): cv.entity_id,
        vol.Optional(CONF_EXPORT_ENTITY): cv.entity_id,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_CALENDARIFIC_API_KEY): cv.string,
        vol.Optional(CONF_COUNTRY, default="MY"): cv.string,
        vol.Optional(CONF_YEAR): cv.positive_int,
    }
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the TNB Calculator sensors."""
    config = config_entry.data

    coordinator = TNBDataCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()

    sensors = [
        TNBSensor(
            coordinator,
            sensor_type,
            sensor_config["name"],
            sensor_config.get("unit"),
            sensor_config.get("device_class"),
            sensor_config.get("state_class"),
            config_entry.entry_id,
        )
        for sensor_type, sensor_config in coordinator.sensor_definitions.items()
    ]

    async_add_entities(sensors)


class TNBDataCoordinator(DataUpdateCoordinator):
    """TNB Calculator data coordinator."""

    def __init__(self, hass: HomeAssistant, config: Dict[str, Any]) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_UPDATE_INTERVAL),
        )
        self.config = config
        self._import_entity = config.get(CONF_IMPORT_ENTITY)
        self._export_entity = config.get(CONF_EXPORT_ENTITY)
        self._api_key = config.get(CONF_CALENDARIFIC_API_KEY)
        self._country = config.get(CONF_COUNTRY, "MY")
        self._year = config.get(CONF_YEAR, dt_util.now().year)

        self._tou_enabled = bool(self._api_key)
        self.sensor_definitions = dict(BASE_SENSOR_TYPES)
        if self._tou_enabled:
            self.sensor_definitions.update(TOU_SENSOR_TYPES)

        self._state: Dict[str, Any] = {}
        self._last_update: Optional[datetime] = None
        self._holiday_cache: Dict[str, bool] = {}

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Home Assistant entities and calculate TNB costs."""
        try:
            now = dt_util.now()

            import_total = self._get_entity_state(self._import_entity)
            export_total = self._get_entity_state(self._export_entity)

            if not hasattr(self, "_monthly_data") or self._month_changed(now):
                self._monthly_data = self._create_month_bucket(now)

            import_delta = self._compute_delta(import_total, "import_last")
            export_delta = self._compute_delta(export_total, "export_last")

            is_holiday = False
            if self._tou_enabled:
                is_holiday = await self._is_holiday(now)

            if import_delta > 0:
                self._monthly_data["import_total"] += import_delta
                if self._tou_enabled:
                    if self._is_peak_period(now, is_holiday):
                        self._monthly_data["import_peak"] += import_delta
                    else:
                        self._monthly_data["import_offpeak"] += import_delta

            if export_delta > 0:
                self._monthly_data["export_total"] += export_delta

            self._state["timestamp"] = now

            monthly_import = self._monthly_data["import_total"]
            monthly_export = self._monthly_data["export_total"]
            monthly_peak = self._monthly_data["import_peak"]
            monthly_offpeak = self._monthly_data["import_offpeak"]

            result: Dict[str, Any] = {
                "import_energy": self._round_energy(monthly_import),
                "export_energy": self._round_energy(monthly_export),
                "net_energy": self._round_energy(monthly_import - monthly_export),
                "last_update": now.isoformat(),
                "current_month": now.strftime("%Y-%m"),
                "monthly_reset_day": 1,
                "is_holiday": is_holiday,
            }

            if self._tou_enabled:
                result["import_peak_energy"] = self._round_energy(monthly_peak)
                result["import_offpeak_energy"] = self._round_energy(monthly_offpeak)
                result.update(
                    self._calculate_tou_costs(
                        monthly_peak,
                        monthly_offpeak,
                        monthly_export,
                    )
                )
            else:
                result.update(self._calculate_non_tou_costs(monthly_import, monthly_export))

            return result

        except Exception as ex:
            raise UpdateFailed(f"Error updating TNB data: {ex}") from ex

    def _get_entity_state(self, entity_id: Optional[str]) -> float:
        """Get numeric state from entity, return 0.0 if unavailable."""
        if not entity_id:
            return 0.0
        
        state = self.hass.states.get(entity_id)
        if not state or state.state in ["unknown", "unavailable"]:
            return 0.0
        
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return 0.0

    def _month_changed(self, now: datetime) -> bool:
        """Check if we've moved to a new month."""
        if not hasattr(self, "_monthly_data"):
            return True
        return (
            now.month != self._monthly_data["month"]
            or now.year != self._monthly_data["year"]
        )

    def _create_month_bucket(self, now: datetime) -> Dict[str, Any]:
        """Create new monthly data bucket."""
        return {
            "month": now.month,
            "year": now.year,
            "import_total": 0.0,
            "export_total": 0.0,
            "import_peak": 0.0,
            "import_offpeak": 0.0,
            "import_last": self._get_entity_state(self._import_entity),
            "export_last": self._get_entity_state(self._export_entity),
        }

    def _compute_delta(self, current_value: float, last_key: str) -> float:
        """Compute delta from last reading, handling meter resets."""
        if not hasattr(self, "_monthly_data"):
            return 0.0
        
        last_value = self._monthly_data.get(last_key, current_value)
        delta = current_value - last_value
        
        # Handle meter reset (negative delta)
        if delta < 0:
            delta = current_value
        
        self._monthly_data[last_key] = current_value
        return delta

    def _is_peak_period(self, timestamp: datetime, is_holiday: bool) -> bool:
        """Determine if timestamp falls in peak period based on TNB ToU schedule."""
        if is_holiday:
            return False
        
        # Weekend (Saturday=5, Sunday=6)
        if timestamp.weekday() >= 5:
            return False
        
        # Weekday 2PM-10PM is peak
        current_time = timestamp.time()
        return PEAK_START <= current_time < PEAK_END

    def _lookup_ict_rate_tou(self, import_kwh: float) -> float:
        """Lookup ICT rate for ToU calculation - uses >= logic."""
        tiers = [
            (1, -0.25),
            (201, -0.245),
            (251, -0.225),
            (301, -0.21),
            (351, -0.17),
            (401, -0.145),
            (451, -0.12),
            (501, -0.105),
            (551, -0.09),
            (601, -0.075),
            (651, -0.055),
            (701, -0.045),
            (751, -0.04),
            (801, -0.025),
            (851, -0.01),
            (901, -0.005),
        ]
        
        ict_rate = tiers[0][1]
        for limit, rate in tiers:
            if import_kwh >= limit:
                ict_rate = rate
        return ict_rate

    def _lookup_ict_rate_non_tou(self, import_kwh: float) -> float:
        """Lookup ICT rate for non-ToU calculation - uses <= logic."""
        if import_kwh <= 200:
            return -0.25
        elif import_kwh <= 250:
            return -0.245
        elif import_kwh <= 300:
            return -0.225
        elif import_kwh <= 350:
            return -0.21
        elif import_kwh <= 400:
            return -0.17
        elif import_kwh <= 450:
            return -0.145
        elif import_kwh <= 500:
            return -0.12
        elif import_kwh <= 550:
            return -0.105
        elif import_kwh <= 600:
            return -0.09
        elif import_kwh <= 650:
            return -0.075
        elif import_kwh <= 700:
            return -0.055
        elif import_kwh <= 750:
            return -0.045
        elif import_kwh <= 800:
            return -0.04
        elif import_kwh <= 850:
            return -0.025
        elif import_kwh <= 900:
            return -0.01
        elif import_kwh <= 1000:
            return -0.005
        else:
            return 0

    def _round_currency(self, value: float) -> float:
        """Round currency to 2 decimal places."""
        return round(value, 2)

    def _round_energy(self, value: float) -> float:
        """Round energy to 3 decimal places."""
        return round(value, 3)

    async def _is_holiday(self, timestamp: datetime) -> bool:
        """Check if the date is a holiday using Calendarific API."""
        if not self._api_key:
            return False
        
        date_str = timestamp.strftime("%Y-%m-%d")
        
        # Check cache first
        if date_str in self._holiday_cache:
            return self._holiday_cache[date_str]
        
        try:
            session = async_get_clientsession(self.hass)
            url = f"{CALENDARIFIC_BASE_URL}{CALENDARIFIC_HOLIDAYS_ENDPOINT}"
            params = {
                "api_key": self._api_key,
                "country": self._country,
                "year": timestamp.year,
                "type": "national",
            }
            
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    holidays = data.get("response", {}).get("holidays", [])
                    
                    # Cache all holidays for the year
                    for holiday in holidays:
                        holiday_date = holiday.get("date", {}).get("iso")
                        if holiday_date:
                            self._holiday_cache[holiday_date] = True
                    
                    # Check if current date is in holidays
                    is_holiday = date_str in self._holiday_cache
                    if not is_holiday:
                        self._holiday_cache[date_str] = False
                    
                    return is_holiday
                else:
                    _LOGGER.warning(
                        "Failed to fetch holidays: HTTP %s", response.status
                    )
                    return False
        except Exception as ex:
            _LOGGER.error("Error checking holiday status: %s", ex)
            return False

    def _calculate_tou_costs(
        self,
        import_peak: float,
        import_offpeak: float,
        export_total: float,
    ) -> Dict[str, Any]:
        """Calculate ToU-based costs following the template exactly."""
        # Derived quantities
        import_total = import_peak + import_offpeak
        export_peak = import_peak
        export_offpeak = export_total - export_peak
        
        # Effective import energy rates (based on import_total threshold)
        if import_total < 1500:
            gen_peak_eff = 0.2852
            gen_off_eff = 0.2443
        else:
            gen_peak_eff = 0.3852
            gen_off_eff = 0.3443
        
        # Fixed rates
        cap_rate = 0.0455
        netw_rate = 0.1285
        
        # AFA & Retailing
        afa = 0.0 if import_total < 600 else import_total * 0.0145
        retailing = 10.0 if import_total > 600 else 0.0
        
        # ICT lookup
        ict_rate = self._lookup_ict_rate_tou(import_total)
        ict_adj = import_total * ict_rate
        
        # Import-side charges
        e10_peak = import_peak * gen_peak_eff
        e11_off = import_offpeak * gen_off_eff
        e13_cap = import_total * cap_rate
        e14_netw = import_total * netw_rate
        e12_afa = afa
        e15_retail = retailing
        e17_ict = ict_adj
        e18_import_charge = e10_peak + e11_off + e12_afa + e13_cap + e14_netw + e15_retail + e17_ict
        
        # Service Tax & KWTBB (both based on E18)
        e19_st = (e18_import_charge * 0.08) if import_total > 600 else 0.0
        e20_kw = (e18_import_charge * 0.016) if import_total > 300 else 0.0
        
        # NEM rebate lines use base energy rates
        nem_peak_rate = 0.2852
        nem_off_rate = 0.2443
        e23_nem_peak = -export_peak * nem_peak_rate
        e24_nem_off = -export_offpeak * nem_off_rate
        e25_nem_cap = -export_total * cap_rate
        e26_nem_netw = -export_total * netw_rate
        nem_rebate_sum = e23_nem_peak + e24_nem_off + e25_nem_cap + e26_nem_netw
        
        # Insentif Leveling
        e28_insentif = -export_total * ict_rate
        
        # Final total
        e30_final = e18_import_charge + e19_st + e20_kw + nem_rebate_sum + e28_insentif
        
        return {
            "total_cost": self._round_currency(e30_final),
            "peak_cost": self._round_currency(e10_peak),
            "off_peak_cost": self._round_currency(e11_off),
            "charge_generation_peak": self._round_currency(e10_peak),
            "charge_generation_offpeak": self._round_currency(e11_off),
            "charge_afa": self._round_currency(e12_afa),
            "charge_capacity": self._round_currency(e13_cap),
            "charge_network": self._round_currency(e14_netw),
            "charge_retailing": self._round_currency(e15_retail),
            "charge_ict": self._round_currency(e17_ict),
            "charge_service_tax": self._round_currency(e19_st),
            "charge_kwtbb": self._round_currency(e20_kw),
            "rebate_nem_peak": self._round_currency(e23_nem_peak),
            "rebate_nem_offpeak": self._round_currency(e24_nem_off),
            "rebate_nem_capacity": self._round_currency(e25_nem_cap),
            "rebate_nem_network": self._round_currency(e26_nem_netw),
            "rebate_insentif": self._round_currency(e28_insentif),
            "rate_generation_peak": gen_peak_eff,
            "rate_generation_offpeak": gen_off_eff,
            "rate_capacity": cap_rate,
            "rate_network": netw_rate,
            "rate_nem_peak": nem_peak_rate,
            "rate_nem_offpeak": nem_off_rate,
            "rate_ict": ict_rate,
        }

    def _calculate_non_tou_costs(
        self, import_kwh: float, export_kwh: float
    ) -> Dict[str, Any]:
        """Calculate non-ToU-based costs following the template exactly."""
        # ICT Rate calculation
        ict_rate = self._lookup_ict_rate_non_tou(import_kwh)
        
        # Import calculation - First tier (up to 600 kWh)
        import_tier1 = min(import_kwh, 600)
        import_caj_tier1 = import_tier1 * 0.2703
        import_capacity_tier1 = import_tier1 * 0.0455
        import_network_tier1 = import_tier1 * 0.1285
        import_runcit_tier1 = 0
        import_ict_tier1 = import_tier1 * ict_rate
        import_kwtbb_tier1 = (import_caj_tier1 + import_capacity_tier1 + import_network_tier1 + import_ict_tier1) * 0.016
        
        # Import calculation - Second tier (excess over 600 kWh)
        import_tier2 = max(import_kwh - 600, 0)
        import_caj_tier2 = import_tier2 * 0.2703
        import_capacity_tier2 = import_tier2 * 0.0455
        import_network_tier2 = import_tier2 * 0.1285
        import_runcit_tier2 = 10 if import_tier2 > 0 else 0
        import_ict_tier2 = import_tier2 * ict_rate
        import_kwtbb_tier2 = (import_caj_tier2 + import_capacity_tier2 + import_network_tier2 + import_ict_tier2) * 0.016
        import_service_tax = (import_caj_tier2 + import_capacity_tier2 + import_network_tier2 + import_runcit_tier2 + import_ict_tier2) * 0.08
        
        # Import totals
        total_import_caj = import_caj_tier1 + import_caj_tier2
        total_import_capacity = import_capacity_tier1 + import_capacity_tier2
        total_import_network = import_network_tier1 + import_network_tier2
        total_import_runcit = import_runcit_tier1 + import_runcit_tier2
        total_import_ict = import_kwh * ict_rate
        total_import_kwtbb = (import_kwtbb_tier1 + import_kwtbb_tier2) if import_kwh > 300 else 0
        total_import_service_tax = import_service_tax
        
        total_import = total_import_caj + total_import_capacity + total_import_network + total_import_runcit + total_import_ict + total_import_kwtbb + total_import_service_tax
        
        # Export calculation (credits)
        export_caj = export_kwh * -0.2703
        export_capacity = export_kwh * -0.0455
        export_network = export_kwh * -0.1285
        export_ict = export_kwh * -ict_rate
        
        total_export = export_caj + export_capacity + export_network + export_ict
        
        # Final subtotal
        subtotal = total_import + total_export
        
        return {
            "total_cost": self._round_currency(subtotal),
            "peak_cost": self._round_currency(0.0),
            "off_peak_cost": self._round_currency(total_import_caj),
        }


class TNBSensor(CoordinatorEntity, RestoreEntity, SensorEntity):
    """TNB Calculator sensor entity."""

    def __init__(
        self,
        coordinator: TNBDataCoordinator,
        sensor_type: str,
        name: str,
        unit: Optional[str],
        device_class: Optional[str],
        state_class: Optional[str],
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = f"{DEFAULT_NAME} {name}"
        self._attr_unique_id = f"{entry_id}_{sensor_type}"
        self._attr_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def state(self) -> Any:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._sensor_type)

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes."""
        if self.coordinator.data is None:
            return {}
        attrs: Dict[str, Any] = {
            "last_update": self.coordinator.data.get("last_update"),
            "is_holiday": self.coordinator.data.get("is_holiday"),
            "current_month": self.coordinator.data.get("current_month"),
            "monthly_reset_day": self.coordinator.data.get("monthly_reset_day"),
        }

        for key in [
            "import_peak_energy",
            "import_offpeak_energy",
            "export_total_energy",
        ]:
            value = self.coordinator.data.get(key)
            if value is not None:
                attrs[key] = value

        return attrs

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            self._attr_state = state.state
