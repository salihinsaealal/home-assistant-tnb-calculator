"""Sensor platform for TNB Calculator integration."""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import aiohttp
import voluptuous as vol

from homeassistant.components.sensor import (
    PLATFORM_SCHEMA,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_MONETARY,
    ENERGY_KILO_WATT_HOUR,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
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
    CONF_TOU_ENABLED,
    CONF_YEAR,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_IMPORT_ENTITY): cv.entity_id,
        vol.Optional(CONF_EXPORT_ENTITY): cv.entity_id,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_TOU_ENABLED, default=False): cv.boolean,
        vol.Optional(CONF_CALENDARIFIC_API_KEY): cv.string,
        vol.Optional(CONF_COUNTRY, default="MY"): cv.string,
        vol.Optional(CONF_YEAR): cv.year,
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

    sensors = []
    for sensor_type, sensor_config in SENSOR_TYPES.items():
        sensors.append(
            TNBSensor(
                coordinator,
                sensor_type,
                sensor_config["name"],
                sensor_config.get("unit"),
                sensor_config.get("device_class"),
                sensor_config.get("state_class"),
                config_entry.entry_id,
            )
        )

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
        self._tou_enabled = config.get(CONF_TOU_ENABLED, False)
        self._api_key = config.get(CONF_CALENDARIFIC_API_KEY)
        self._country = config.get(CONF_COUNTRY, "MY")
        self._year = config.get(CONF_YEAR, datetime.now().year)

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Home Assistant entities and calculate TNB costs."""
        try:
            # Get current import/export energy values
            import_energy = 0.0
            export_energy = 0.0

            if self._import_entity:
                import_state = self.hass.states.get(self._import_entity)
                if import_state and import_state.state not in ["unknown", "unavailable"]:
                    import_energy = float(import_state.state)

            if self._export_entity:
                export_state = self.hass.states.get(self._export_entity)
                if export_state and export_state.state not in ["unknown", "unavailable"]:
                    export_energy = float(export_state.state)

            net_energy = import_energy - export_energy

            # Check if today is a holiday for ToU calculations
            is_holiday = False
            if self._tou_enabled and self._api_key:
                is_holiday = await self._is_holiday_today()

            # Calculate monthly costs (reset on 1st of month)
            current_month = datetime.now().month
            current_year = datetime.now().year
            
            # Initialize or reset monthly data
            if not hasattr(self, '_monthly_data'):
                self._monthly_data = {
                    'month': current_month,
                    'year': current_year,
                    'import_start': import_energy,
                    'export_start': export_energy,
                    'last_import': import_energy,
                    'last_export': export_energy,
                }
            
            # Check if we need to reset for new month
            if (current_month != self._monthly_data['month'] or 
                current_year != self._monthly_data['year']):
                # Store previous month data
                prev_month_import = self._monthly_data['last_import'] - self._monthly_data['import_start']
                prev_month_export = self._monthly_data['last_export'] - self._monthly_data['export_start']
                
                # Reset for new month
                self._monthly_data = {
                    'month': current_month,
                    'year': current_year,
                    'import_start': import_energy,
                    'export_start': export_energy,
                    'last_import': import_energy,
                    'last_export': export_energy,
                    'prev_month_import': prev_month_import,
                    'prev_month_export': prev_month_export,
                }
            
            # Update current values
            self._monthly_data['last_import'] = import_energy
            self._monthly_data['last_export'] = export_energy
            
            # Calculate monthly consumption
            monthly_import = max(0, import_energy - self._monthly_data['import_start'])
            monthly_export = max(0, export_energy - self._monthly_data['export_start'])
            
            # Calculate costs based on monthly consumption
            total_cost, peak_cost, off_peak_cost = await self._calculate_costs(
                monthly_import, monthly_export, is_holiday
            )

            return {
                "import_energy": monthly_import,
                "export_energy": monthly_export,
                "net_energy": monthly_import - monthly_export,
                "total_cost": total_cost,
                "peak_cost": peak_cost,
                "off_peak_cost": off_peak_cost,
                "is_holiday": is_holiday,
                "last_update": datetime.now().isoformat(),
                "current_month": f"{current_year}-{current_month:02d}",
                "monthly_reset_day": 1,
            }

        except Exception as ex:
            raise UpdateFailed(f"Error updating TNB data: {ex}") from ex

    async def _is_holiday_today(self) -> bool:
        """Check if today is a holiday using Calendarific API."""
        try:
            today = datetime.now().date()
            params = {
                "api_key": self._api_key,
                "country": self._country,
                "year": self._year,
                "month": today.month,
                "day": today.day,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{CALENDARIFIC_BASE_URL}{CALENDARIFIC_HOLIDAYS_ENDPOINT}",
                    params=params,
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        holidays = data.get("response", {}).get("holidays", [])
                        return len(holidays) > 0
                    else:
                        _LOGGER.warning(
                            "Failed to fetch holiday data from Calendarific API: %s",
                            response.status,
                        )
                        return False
        except Exception as ex:
            _LOGGER.error("Error checking holiday status: %s", ex)
            return False

    async def _calculate_costs(
        self, import_energy: float, export_energy: float, is_holiday: bool
    ) -> tuple[float, float, float]:
        """Calculate TNB costs based on actual tariff structure."""
        try:
            import_kwh = import_energy
            export_kwh = export_energy
            
            # ICT Rate calculation based on import consumption tiers
            ict_rate = (
                -0.25 if import_kwh <= 200 else
                -0.245 if import_kwh <= 250 else
                -0.225 if import_kwh <= 300 else
                -0.21 if import_kwh <= 350 else
                -0.17 if import_kwh <= 400 else
                -0.145 if import_kwh <= 450 else
                -0.12 if import_kwh <= 500 else
                -0.105 if import_kwh <= 550 else
                -0.09 if import_kwh <= 600 else
                -0.075 if import_kwh <= 650 else
                -0.055 if import_kwh <= 700 else
                -0.045 if import_kwh <= 750 else
                -0.04 if import_kwh <= 800 else
                -0.025 if import_kwh <= 850 else
                -0.01 if import_kwh <= 900 else
                -0.005 if import_kwh <= 1000 else 0
            )
            
            if self._tou_enabled:
                # ToU calculation (placeholder for now)
                if is_holiday:
                    # Holiday rates (off-peak)
                    total_cost = import_energy * 0.20  # RM/kWh off-peak holiday rate
                    peak_cost = 0.0
                    off_peak_cost = total_cost
                else:
                    # Normal ToU rates (placeholder)
                    peak_cost = import_energy * 0.40  # RM/kWh peak rate
                    off_peak_cost = export_energy * 0.15  # RM/kWh off-peak rate
                    total_cost = peak_cost + off_peak_cost
            else:
                # Non-ToU calculation using actual TNB tariff
                # Import calculation - First tier (up to 600 kWh)
                import_tier1 = min(import_kwh, 600)
                import_caj_tier1 = round(import_tier1 * 0.2703, 2)
                import_capacity_tier1 = round(import_tier1 * 0.0455, 2)
                import_network_tier1 = round(import_tier1 * 0.1285, 2)
                import_runcit_tier1 = 0
                import_ict_tier1 = round(import_tier1 * ict_rate, 2)
                import_kwtbb_tier1 = round((import_caj_tier1 + import_capacity_tier1 + import_network_tier1 + import_ict_tier1) * 0.016, 2)
                
                # Import calculation - Second tier (excess over 600 kWh)
                import_tier2 = max(import_kwh - 600, 0)
                import_caj_tier2 = round(import_tier2 * 0.2703, 2)
                import_capacity_tier2 = round(import_tier2 * 0.0455, 2)
                import_network_tier2 = round(import_tier2 * 0.1285, 2)
                import_runcit_tier2 = 10 if import_tier2 > 0 else 0
                import_ict_tier2 = round(import_tier2 * ict_rate, 2)
                import_kwtbb_tier2 = round((import_caj_tier2 + import_capacity_tier2 + import_network_tier2 + import_ict_tier2) * 0.016, 2)
                import_service_tax = round((import_caj_tier2 + import_capacity_tier2 + import_network_tier2 + import_runcit_tier2 + import_ict_tier2) * 0.08, 2)
                
                # Import totals
                total_import_caj = import_caj_tier1 + import_caj_tier2
                total_import_capacity = import_capacity_tier1 + import_capacity_tier2
                total_import_network = import_network_tier1 + import_network_tier2
                total_import_runcit = import_runcit_tier1 + import_runcit_tier2
                total_import_ict = round(import_kwh * ict_rate, 2)
                total_import_kwtbb = (import_kwtbb_tier1 + import_kwtbb_tier2) if import_kwh > 300 else 0
                total_import_service_tax = import_service_tax
                
                total_import = total_import_caj + total_import_capacity + total_import_network + total_import_runcit + total_import_ict + total_import_kwtbb + total_import_service_tax
                
                # Export calculation (credits)
                export_caj = round(export_kwh * -0.2703, 2)
                export_capacity = round(export_kwh * -0.0455, 2)
                export_network = round(export_kwh * -0.1285, 2)
                export_ict = round(export_kwh * -ict_rate, 2)
                
                total_export = export_caj + export_capacity + export_network + export_ict
                
                # Final subtotal
                total_cost = round(total_import + total_export, 2)
                peak_cost = 0.0  # Not applicable for non-ToU
                off_peak_cost = 0.0  # Not applicable for non-ToU
            
            return total_cost, peak_cost, off_peak_cost
            
        except Exception as ex:
            _LOGGER.error("Error calculating TNB costs: %s", ex)
            return 0.0, 0.0, 0.0


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
        return {
            "last_update": self.coordinator.data.get("last_update"),
            "is_holiday": self.coordinator.data.get("is_holiday"),
        }

    async def async_added_to_hass(self) -> None:
        """Handle entity added to hass."""
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state:
            self._attr_state = state.state
