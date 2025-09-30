"""Sensor platform for TNB Calculator integration."""
import logging
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_MONETARY,
    ENERGY_KILO_WATT_HOUR,
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
PEAK_START = time(8, 0)
PEAK_END = time(22, 0)

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
        
        # Weekday 8AM-10PM is peak
        current_time = timestamp.time()
        return PEAK_START <= current_time < PEAK_END

    def _lookup_ict_rate(self, import_kwh: float) -> float:
        """Lookup ICT rate based on consumption tier."""
        tiers = [
            (200, -0.25),
            (250, -0.245),
            (300, -0.225),
            (350, -0.21),
            (400, -0.17),
            (450, -0.145),
            (500, -0.12),
            (550, -0.105),
            (600, -0.09),
            (650, -0.075),
            (700, -0.055),
            (750, -0.045),
            (800, -0.04),
            (850, -0.025),
            (900, -0.01),
            (1000, -0.005),
        ]
        
        for limit, rate in tiers:
            if import_kwh <= limit:
                return rate
        return 0.0

    def _round_currency(self, value: float) -> float:
        """Round currency to 2 decimal places."""
        return round(value, 2)

    def _round_energy(self, value: float) -> float:
        """Round energy to 3 decimal places."""
        return round(value, 3)


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
