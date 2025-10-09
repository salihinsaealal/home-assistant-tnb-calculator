"""Sensor platform for TNB Calculator integration."""
import calendar
import logging
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA, SensorEntity
from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME,
    UnitOfEnergy,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.storage import Store
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
    CONF_BILLING_START_DAY,
    DEFAULT_NAME,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    BASE_SENSOR_TYPES,
    TOU_SENSOR_TYPES,
    MAX_DELTA_PER_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

PEAK_DAYS = {0, 1, 2, 3, 4}  # Monday to Friday
PEAK_START = time(14, 0)  # 2PM
PEAK_END = time(22, 0)    # 10PM

# Storage constants
STORAGE_VERSION = 1
STORAGE_KEY = "tnb_calculator_monthly_data"

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
    config = dict(config_entry.data)
    config["entry_id"] = config_entry.entry_id

    coordinator = TNBDataCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()

    # Create device registry entry
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, config_entry.entry_id)},
        name=DEFAULT_NAME,
        manufacturer="Cikgu Saleh",
        model="TNB Calculator",
        sw_version="3.7.3e",
    )

    sensors = [
        TNBSensor(
            coordinator,
            sensor_type,
            sensor_config["name"],
            sensor_config.get("unit"),
            sensor_config.get("device_class"),
            sensor_config.get("state_class"),
            sensor_config.get("entity_category"),
            config_entry.entry_id,
            device.id,
        )
        for sensor_type, sensor_config in coordinator.sensor_definitions.items()
    ]
    
    # Add billing start day number entity
    billing_day_number = TNBBillingStartDayNumber(
        coordinator,
        config_entry,
        device.id,
    )
    sensors.append(billing_day_number)

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
        self._billing_start_day = config.get(CONF_BILLING_START_DAY, 1)

        self._tou_enabled = bool(self._api_key)
        self.sensor_definitions = dict(BASE_SENSOR_TYPES)
        if self._tou_enabled:
            self.sensor_definitions.update(TOU_SENSOR_TYPES)

        self._state: Dict[str, Any] = {}
        self._last_update: Optional[datetime] = None
        
        # Setup persistent storage with stable identifier
        # Use import entity as stable key so data survives delete/re-add
        if self._import_entity:
            storage_id = self._import_entity.replace(".", "_").replace("sensor_", "")
        else:
            _LOGGER.warning("No import entity configured, using default storage")
            storage_id = "default"
        
        self._store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}_{storage_id}")
        self._entry_id = config.get('entry_id')
        _LOGGER.debug("Using storage key: %s", f"{STORAGE_KEY}_{storage_id}")
        self._monthly_data_loaded = False
        self._holiday_data_loaded = False
        self._historical_months: Dict[str, Dict[str, float]] = {}
        self._last_calculated_cost = 0.0
        self._daily_data: Dict[str, Any] = {}
        self._daily_data_loaded = False
        self._integration_start_time = dt_util.now()
        self._last_successful_update = None
        self._validation_errors: list[str] = []
        self._last_validation_status: str = "OK"

    async def _load_monthly_data(self) -> None:
        """Load monthly data from storage."""
        if self._monthly_data_loaded:
            return
            
        stored_data = await self._store.async_load()
        
        # Try migration from old entry_id-based storage if new storage is empty
        if not stored_data and self._entry_id:
            _LOGGER.info("Attempting to migrate data from old storage format")
            old_store = Store(self.hass, STORAGE_VERSION, f"{STORAGE_KEY}_{self._entry_id}")
            old_data = await old_store.async_load()
            if old_data:
                # Check if old data is in old format (monthly_data directly) or new format (wrapped)
                if "monthly_data" in old_data:
                    # Already in new format
                    stored_data = old_data
                elif "month" in old_data and "year" in old_data:
                    # Old format - monthly data was stored directly
                    _LOGGER.info("Converting old storage format to new format")
                    stored_data = {
                        "monthly_data": old_data,
                        "holiday_cache": {},
                        "last_holiday_fetch": None,
                    }
                else:
                    stored_data = old_data
                
                if stored_data:
                    _LOGGER.info("Successfully migrated data from old storage. Saving to new location.")
                    await self._store.async_save(stored_data)
        
        if stored_data:
            _LOGGER.debug("Loaded monthly data from storage: %s", stored_data)
            monthly_data = stored_data.get("monthly_data", {})
            
            # Only load monthly_data if it has required keys
            if monthly_data and "month" in monthly_data and "year" in monthly_data:
                # Migration: Add billing_start_day if missing
                if "billing_start_day" not in monthly_data:
                    monthly_data["billing_start_day"] = 1
                    _LOGGER.info("Migrated monthly_data: added billing_start_day=1")
                
                # Migration: Add billing_month and billing_year if missing
                if "billing_month" not in monthly_data or "billing_year" not in monthly_data:
                    # Use calendar month/year as billing period for existing data
                    monthly_data["billing_month"] = monthly_data["month"]
                    monthly_data["billing_year"] = monthly_data["year"]
                    _LOGGER.info("Migrated monthly_data: added billing_month=%d, billing_year=%d",
                                monthly_data["billing_month"], monthly_data["billing_year"])
                
                # Migration: Add calibration structure if missing
                if "calibration" not in monthly_data:
                    monthly_data["calibration"] = {
                        "import_baseline": 0.0,
                        "peak_baseline": 0.0,
                        "offpeak_baseline": 0.0,
                        "export_baseline": 0.0,
                        "last_calibrated": None,
                        "distribution_method": None,
                    }
                    _LOGGER.info("Migrated monthly_data: added calibration structure")
                
                self._monthly_data = monthly_data
            else:
                _LOGGER.debug("No valid monthly data in storage, will create new bucket")
            
            # Load holiday cache from storage
            if not self._holiday_data_loaded:
                self._holiday_cache = stored_data.get("holiday_cache", {})
                self._last_holiday_fetch = stored_data.get("last_holiday_fetch")
                self._holiday_data_loaded = True
                _LOGGER.debug("Loaded %d holidays from storage, last fetch: %s", 
                             len(self._holiday_cache), self._last_holiday_fetch)
            
            # Load historical data
            self._historical_months = stored_data.get("historical_months", {})
            
            # Migration: Add billing_start_day to historical months
            migrated_count = 0
            for month_key, month_data in self._historical_months.items():
                if "billing_start_day" not in month_data:
                    month_data["billing_start_day"] = 1
                    migrated_count += 1
            
            if migrated_count > 0:
                _LOGGER.info("Migrated %d historical months with billing_start_day=1", migrated_count)
            
            _LOGGER.debug("Loaded %d months of historical data", len(self._historical_months))
            
            # Load daily data
            self._daily_data = stored_data.get("daily_data", {})
            if self._daily_data and "date" in self._daily_data:
                _LOGGER.debug("Loaded daily data for %s", self._daily_data["date"])
            self._daily_data_loaded = True
        else:
            self._holiday_cache = {}
            self._last_holiday_fetch = None
            self._historical_months = {}
            self._daily_data = {}
            self._daily_data_loaded = True
            
        self._monthly_data_loaded = True

    async def _save_monthly_data(self) -> None:
        """Save monthly data to storage."""
        if hasattr(self, "_monthly_data"):
            storage_data = {
                "monthly_data": self._monthly_data,
                "holiday_cache": getattr(self, "_holiday_cache", {}),
                "last_holiday_fetch": getattr(self, "_last_holiday_fetch", None),
                "historical_months": getattr(self, "_historical_months", {}),
                "daily_data": getattr(self, "_daily_data", {}),
            }
            await self._store.async_save(storage_data)
            _LOGGER.debug("Saved data to storage: monthly + daily + %d holidays + %d historical months", 
                         len(getattr(self, "_holiday_cache", {})),
                         len(getattr(self, "_historical_months", {})))

    async def async_reset_storage(self) -> None:
        """Clear stored data and reset runtime counters."""
        _LOGGER.info("Resetting TNB Calculator storage and runtime buffers")
        await self._store.async_remove()

        now = dt_util.now()

        # Reset caches and counters
        self._holiday_cache = {}
        self._holiday_data_loaded = True
        self._last_holiday_fetch = None
        self._historical_months = {}
        self._monthly_data = self._create_month_bucket(now)
        self._monthly_data_loaded = True
        self._daily_data = self._create_day_bucket(now)
        self._daily_data_loaded = True
        self._last_calculated_cost = 0.0
        self._validation_errors = []
        self._last_validation_status = "OK"

        await self._save_monthly_data()
        self.async_set_updated_data({})

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Home Assistant entities and calculate TNB costs."""
        try:
            self._validation_errors = []
            now = dt_util.now()

            # Load stored data on first run
            await self._load_monthly_data()

            import_total = self._get_entity_state(self._import_entity, "Import entity")
            export_total = self._get_entity_state(self._export_entity, "Export entity")

            if not hasattr(self, "_monthly_data") or self._month_changed(now):
                self._monthly_data = self._create_month_bucket(now)
                await self._save_monthly_data()

            # Check and reset daily data if day changed
            if not hasattr(self, "_daily_data") or self._day_changed(now):
                self._daily_data = self._create_day_bucket(now)
                await self._save_monthly_data()

            import_delta = self._compute_delta(import_total, "import_last")
            export_delta = self._compute_delta(export_total, "export_last")
            
            # Compute daily deltas (from midnight start)
            daily_import_delta = import_total - self._daily_data.get("import_start", import_total)
            daily_export_delta = export_total - self._daily_data.get("export_start", export_total)

            is_holiday = False
            if self._tou_enabled:
                # Fetch holidays daily
                await self._fetch_holidays_if_needed(now)
                is_holiday = await self._is_holiday(now)

            data_changed = False
            if import_delta > 0:
                self._monthly_data["import_total"] += import_delta
                if self._tou_enabled:
                    if self._is_peak_period(now, is_holiday):
                        self._monthly_data["import_peak"] += import_delta
                    else:
                        self._monthly_data["import_offpeak"] += import_delta
                data_changed = True

            if export_delta > 0:
                self._monthly_data["export_total"] += export_delta
                data_changed = True

            # Save data after changes
            if data_changed:
                await self._save_monthly_data()

            self._state["timestamp"] = now

            # Get monthly totals (must be BEFORE daily calculations that use them)
            monthly_import = self._monthly_data["import_total"]
            monthly_export = self._monthly_data["export_total"]
            monthly_peak = self._monthly_data["import_peak"]
            monthly_offpeak = self._monthly_data["import_offpeak"]

            # Update daily data (always set to current delta from midnight)
            if daily_import_delta >= 0:  # Handle meter resets
                self._daily_data["import_total"] = daily_import_delta
                if self._tou_enabled:
                    # Estimate peak/offpeak split for today based on current period
                    # This is approximate - we don't track historical intraday splits
                    if self._is_peak_period(now, is_holiday):
                        # Rough estimate: assume proportional to monthly ratio
                        if monthly_import > 0:
                            peak_ratio = monthly_peak / monthly_import
                        else:
                            peak_ratio = 0.6
                        self._daily_data["import_peak"] = daily_import_delta * peak_ratio
                        self._daily_data["import_offpeak"] = daily_import_delta * (1 - peak_ratio)
                    else:
                        if monthly_import > 0:
                            offpeak_ratio = monthly_offpeak / monthly_import
                        else:
                            offpeak_ratio = 0.4
                        self._daily_data["import_peak"] = daily_import_delta * (1 - offpeak_ratio)
                        self._daily_data["import_offpeak"] = daily_import_delta * offpeak_ratio
            
            if daily_export_delta >= 0:
                self._daily_data["export_total"] = daily_export_delta

            # Determine day status (Weekday/Weekend/Holiday)
            if is_holiday:
                day_status = "Holiday"
            elif now.weekday() >= 5:  # Saturday=5, Sunday=6
                day_status = "Weekend"
            else:
                day_status = "Weekday"
            
            # Determine period status (Peak/Off-Peak with reason)
            is_peak = self._is_peak_period(now, is_holiday)
            if is_peak:
                period_status = "Peak"
            else:
                # Show reason for off-peak
                if is_holiday:
                    period_status = "Off-Peak (Holiday)"
                elif now.weekday() >= 5:
                    period_status = "Off-Peak (Weekend)"
                else:
                    # Weekday but outside peak hours (before 2PM or after 10PM)
                    period_status = "Off-Peak"

            result: Dict[str, Any] = {
                "import_energy": self._round_energy(monthly_import),
                "export_energy": self._round_energy(monthly_export),
                "net_energy": self._round_energy(monthly_import - monthly_export),
                "day_status": day_status,
                "period_status": period_status,
                "last_update": now.isoformat(),
                "current_month": now.strftime("%Y-%m"),
                "billing_start_day": self._billing_start_day,
                "monthly_reset_day": self._billing_start_day,  # Deprecated, kept for compatibility
                "is_holiday": is_holiday,
            }

            # Always calculate non-ToU costs
            non_tou_costs = self._calculate_non_tou_costs(monthly_import, monthly_export)
            result["total_cost_non_tou"] = non_tou_costs["total_cost"]
            
            # Calculate ToU costs if enabled
            if self._tou_enabled:
                result["import_peak_energy"] = self._round_energy(monthly_peak)
                result["import_offpeak_energy"] = self._round_energy(monthly_offpeak)
                tou_costs = self._calculate_tou_costs(
                    monthly_peak,
                    monthly_offpeak,
                    monthly_export,
                )
                result["total_cost_tou"] = tou_costs["total_cost"]
                # Add detailed ToU breakdown
                result.update(tou_costs)
            else:
                # ToU not enabled - set to None (shows as "unavailable")
                result["total_cost_tou"] = None
                # Add non-ToU breakdown for peak/off-peak cost sensors
                result["peak_cost"] = non_tou_costs.get("peak_cost", 0.0)
                result["off_peak_cost"] = non_tou_costs.get("off_peak_cost", 0.0)

            # Store last calculated cost for historical tracking
            self._last_calculated_cost = result.get("total_cost_tou" if self._tou_enabled else "total_cost_non_tou", 0.0)
            
            # Calculate predictions
            prediction_data = self._calculate_predictions(now, monthly_import, monthly_peak, monthly_offpeak, monthly_export)
            result.update(prediction_data)
            
            # Add daily usage sensors
            daily_import = self._daily_data.get("import_total", 0.0)
            daily_export = self._daily_data.get("export_total", 0.0)
            daily_peak = self._daily_data.get("import_peak", 0.0)
            daily_offpeak = self._daily_data.get("import_offpeak", 0.0)
            
            result["today_import_kwh"] = self._round_energy(daily_import)
            result["today_export_kwh"] = self._round_energy(daily_export)
            result["today_net_kwh"] = self._round_energy(daily_import - daily_export)
            result["today_import_peak_kwh"] = self._round_energy(daily_peak)
            result["today_import_offpeak_kwh"] = self._round_energy(daily_offpeak)
            
            # Calculate today's costs
            daily_non_tou_costs = self._calculate_non_tou_costs(daily_import, daily_export)
            result["today_cost_non_tou"] = daily_non_tou_costs["total_cost"]
            
            if self._tou_enabled:
                daily_tou_costs = self._calculate_tou_costs(daily_peak, daily_offpeak, daily_export)
                result["today_cost_tou"] = daily_tou_costs["total_cost"]
            else:
                # ToU not enabled - set to None (shows as "unavailable")
                result["today_cost_tou"] = None
            
            # Binary sensors for automations
            result["peak_period"] = "on" if self._is_peak_period(now, is_holiday) else "off"
            result["holiday_today"] = "on" if is_holiday else "off"
            
            # High usage alert (approaching 600 kWh tier)
            usage_threshold = 550  # Alert at 550 kWh (50 kWh before tier change)
            result["high_usage_alert"] = "on" if monthly_import >= usage_threshold else "off"
            
            # Tier status
            if monthly_import < 600:
                tier_status = "Below 600 kWh"
            elif monthly_import < 1500:
                tier_status = "600-1500 kWh"
            else:
                tier_status = "Above 1500 kWh"
            result["tier_status"] = tier_status
            
            # Configuration scenario sensor
            scenario_data = self._determine_configuration_scenario()
            result["configuration_scenario"] = scenario_data["state"]
            result["configuration_scenario_details"] = scenario_data["attributes"]
            
            # Diagnostic sensors
            result["storage_health"] = self._check_storage_health()
            result["cached_holidays_count"] = len(self._holiday_cache)
            holidays_by_year: Dict[str, list[str]] = {}
            for date_str in sorted(self._holiday_cache.keys()):
                year = date_str[:4]
                holidays_by_year.setdefault(year, []).append(date_str)
            result["cached_holidays"] = holidays_by_year
            result["cached_holidays_last_fetch"] = self._last_holiday_fetch
            result["last_update"] = now.isoformat()
            
            # Calculate uptime in hours
            uptime_delta = now - self._integration_start_time
            uptime_hours = uptime_delta.total_seconds() / 3600
            result["integration_uptime"] = round(uptime_hours, 2)
            result["validation_status"] = (
                "; ".join(self._validation_errors) if self._validation_errors else "OK"
            )
            self._last_validation_status = result["validation_status"]

            # Mark successful update
            self._last_successful_update = now

            return result

        except Exception as ex:
            raise UpdateFailed(f"Error updating TNB data: {ex}") from ex

    def _add_validation_error(self, source: str, message: str) -> None:
        """Record a validation error for diagnostics and logging."""
        full_message = f"{source}: {message}"
        if full_message not in self._validation_errors:
            self._validation_errors.append(full_message)
            _LOGGER.warning("Validation warning - %s", full_message)
    
    def _determine_configuration_scenario(self) -> Dict[str, Any]:
        """Determine current configuration scenario and return state with attributes."""
        has_import = bool(self._import_entity)
        has_export = bool(self._export_entity)
        has_api = bool(self._api_key)
        tou_enabled = self._tou_enabled
        
        # Determine state
        if has_export and tou_enabled:
            state = "Import + Export (ToU)"
            description = "Full configuration with import, export tracking, and Time of Use calculations. Peak/off-peak splitting active with holiday detection."
        elif has_export and not tou_enabled:
            state = "Import + Export (Non-ToU)"
            description = "Import and export tracking without Time of Use. Costs calculated using flat tariff. No peak/off-peak splitting."
        elif not has_export and tou_enabled:
            state = "Import Only (ToU)"
            description = "Import-only configuration with Time of Use. Peak/off-peak splitting active with holiday detection. Export energy not tracked."
        else:
            state = "Import Only (Non-ToU)"
            description = "Import-only configuration without Time of Use. Costs calculated using flat tariff. Export energy not tracked."
        
        # Build attributes
        attributes = {
            "has_import": has_import,
            "has_export": has_export,
            "has_api_key": has_api,
            "tou_enabled": tou_enabled,
            "cost_calculation_mode": "ToU" if tou_enabled else "Non-ToU",
            "export_tracking": "Enabled" if has_export else "Disabled",
            "description": description,
        }
        
        return {"state": state, "attributes": attributes}
    
    async def async_set_energy_values(self, call) -> None:
        """Service to set exact energy values with distribution options."""
        import_total = call.data["import_total"]
        distribution = call.data.get("distribution", "proportional")
        export_total = call.data.get("export_total")
        
        # Get current values
        current_import = self._monthly_data.get("import_total", 0)
        current_peak = self._monthly_data.get("import_peak", 0)
        current_offpeak = self._monthly_data.get("import_offpeak", 0)
        
        # Calculate difference
        import_diff = import_total - current_import
        
        # Distribute based on option
        if distribution == "proportional":
            # Maintain current ratio
            if current_import > 0:
                peak_ratio = current_peak / current_import
            else:
                peak_ratio = 0.6  # Default 60% peak
            
            new_peak = import_total * peak_ratio
            new_offpeak = import_total * (1 - peak_ratio)
        
        elif distribution == "peak_only":
            # Add difference to peak only
            new_peak = current_peak + import_diff
            new_offpeak = current_offpeak
        
        elif distribution == "offpeak_only":
            # Add difference to off-peak only
            new_peak = current_peak
            new_offpeak = current_offpeak + import_diff
        
        elif distribution == "auto":
            # Auto-detect based on current time
            now = dt_util.now()
            is_holiday = self._is_holiday(now)
            is_peak = self._is_peak_period(now, is_holiday)
            
            if is_peak:
                # Currently peak time - assume adjustment is peak-related
                new_peak = current_peak + import_diff
                new_offpeak = current_offpeak
                _LOGGER.info("Auto-distribution: Applied to peak (current time is peak period)")
            else:
                # Currently off-peak - assume adjustment is off-peak-related
                new_peak = current_peak
                new_offpeak = current_offpeak + import_diff
                _LOGGER.info("Auto-distribution: Applied to off-peak (current time is off-peak period)")
        
        elif distribution == "manual":
            # User provides exact values
            new_peak = call.data.get("import_peak")
            new_offpeak = call.data.get("import_offpeak")
            
            if new_peak is None or new_offpeak is None:
                raise ValueError("import_peak and import_offpeak required when distribution='manual'")
            
            # Validate sum
            if abs((new_peak + new_offpeak) - import_total) > 0.01:
                raise ValueError(f"Peak ({new_peak}) + Off-peak ({new_offpeak}) must equal Import Total ({import_total})")
        
        else:
            raise ValueError(f"Invalid distribution option: {distribution}")
        
        # Validate non-negative
        if new_peak < 0 or new_offpeak < 0:
            raise ValueError("Peak and off-peak values cannot be negative")
        
        # Get sensor readings for baseline calculation
        sensor_import = self._get_entity_state(self._import_entity, "Import")
        sensor_export = self._get_entity_state(self._export_entity, "Export")
        
        # Calculate baselines (offset from sensor)
        import_baseline = import_total - sensor_import
        peak_baseline = new_peak - current_peak
        offpeak_baseline = new_offpeak - current_offpeak
        
        # Store calibration
        if "calibration" not in self._monthly_data:
            self._monthly_data["calibration"] = {}
        
        self._monthly_data["calibration"]["import_baseline"] = import_baseline
        self._monthly_data["calibration"]["peak_baseline"] = peak_baseline
        self._monthly_data["calibration"]["offpeak_baseline"] = offpeak_baseline
        self._monthly_data["calibration"]["last_calibrated"] = dt_util.now().isoformat()
        self._monthly_data["calibration"]["distribution_method"] = distribution
        
        # Update values
        self._monthly_data["import_total"] = import_total
        self._monthly_data["import_peak"] = new_peak
        self._monthly_data["import_offpeak"] = new_offpeak
        
        # Export calibration
        if export_total is not None:
            export_baseline = export_total - sensor_export
            self._monthly_data["calibration"]["export_baseline"] = export_baseline
            self._monthly_data["export_total"] = export_total
        
        # Log calibration
        _LOGGER.info(
            "Energy calibration applied: Import %.2f kWh (Peak: %.2f, Off-peak: %.2f) using '%s' distribution",
            import_total, new_peak, new_offpeak, distribution
        )
        
        # Save and refresh
        await self._save_monthly_data()
        await self.async_request_refresh()
    
    async def async_adjust_energy_values(self, call) -> None:
        """Service to apply offset adjustments to current values."""
        import_adj = call.data.get("import_adjustment", 0)
        peak_adj = call.data.get("peak_adjustment", 0)
        offpeak_adj = call.data.get("offpeak_adjustment", 0)
        export_adj = call.data.get("export_adjustment", 0)
        
        # Apply adjustments
        if import_adj != 0:
            self._monthly_data["calibration"]["import_baseline"] += import_adj
            self._monthly_data["import_total"] += import_adj
        
        if peak_adj != 0 or offpeak_adj != 0:
            # Validate sum still equals total
            new_peak = self._monthly_data["import_peak"] + peak_adj
            new_offpeak = self._monthly_data["import_offpeak"] + offpeak_adj
            
            if abs((new_peak + new_offpeak) - self._monthly_data["import_total"]) > 0.01:
                raise ValueError("Peak + Off-peak adjustment must maintain Import Total")
            
            self._monthly_data["calibration"]["peak_baseline"] += peak_adj
            self._monthly_data["calibration"]["offpeak_baseline"] += offpeak_adj
            self._monthly_data["import_peak"] = new_peak
            self._monthly_data["import_offpeak"] = new_offpeak
        
        if export_adj != 0:
            self._monthly_data["calibration"]["export_baseline"] += export_adj
            self._monthly_data["export_total"] += export_adj
        
        # Update calibration timestamp
        if "calibration" not in self._monthly_data:
            self._monthly_data["calibration"] = {}
        self._monthly_data["calibration"]["last_calibrated"] = dt_util.now().isoformat()
        
        # Log adjustment
        _LOGGER.info(
            "Energy adjustment applied: Import %+.2f kWh (Peak: %+.2f, Off-peak: %+.2f, Export: %+.2f)",
            import_adj, peak_adj, offpeak_adj, export_adj
        )
        
        # Save and refresh
        await self._save_monthly_data()
        await self.async_request_refresh()

    def _get_entity_state(self, entity_id: Optional[str], source: str) -> float:
        """Get numeric state from entity, return 0.0 if unavailable."""
        if not entity_id:
            self._add_validation_error(source, "entity not configured")
            return 0.0

        state = self.hass.states.get(entity_id)
        if state is None:
            self._add_validation_error(source, f"entity '{entity_id}' not found")
            return 0.0

        if state.state in ["unknown", "unavailable"]:
            self._add_validation_error(source, f"entity '{entity_id}' state is {state.state}")
            return 0.0

        try:
            return float(state.state)
        except (ValueError, TypeError):
            self._add_validation_error(source, f"entity '{entity_id}' reported non-numeric state '{state.state}'")
            return 0.0

    def _get_billing_period(self, dt: datetime) -> tuple[int, int]:
        """Calculate billing month/year based on start day.
        
        Returns (billing_month, billing_year) tuple.
        Example: Oct 10 with billing day 15 → (9, 2024) (still in Sept 15 - Oct 14 period)
        """
        billing_start_day = self._billing_start_day
        
        if dt.day >= billing_start_day:
            # Current calendar month is the billing month
            return dt.month, dt.year
        else:
            # Still in previous billing period
            if dt.month == 1:
                return 12, dt.year - 1
            else:
                return dt.month - 1, dt.year
    
    def _normalize_billing_day(self, year: int, month: int, day: int) -> int:
        """Normalize billing day to valid day in given month.
        
        Example: day 31 in February → returns 28 or 29
        """
        last_day = calendar.monthrange(year, month)[1]
        return min(day, last_day)
    
    def _month_changed(self, now: datetime) -> bool:
        """Check if we've moved to a new billing period and save historical data if needed."""
        if not hasattr(self, "_monthly_data"):
            return True
        
        # Get current and stored billing periods
        current_billing_month, current_billing_year = self._get_billing_period(now)
        stored_billing_month = self._monthly_data.get("billing_month", self._monthly_data.get("month"))
        stored_billing_year = self._monthly_data.get("billing_year", self._monthly_data.get("year"))
        
        month_changed = (
            current_billing_month != stored_billing_month
            or current_billing_year != stored_billing_year
        )
        
        if month_changed and hasattr(self, "_monthly_data"):
            # Save completed month to historical data before reset
            month_key = f"{self._monthly_data['year']}-{self._monthly_data['month']:02d}"
            self._historical_months[month_key] = {
                "total_kwh": self._monthly_data.get("import_total", 0),
                "total_cost": self._last_calculated_cost,
                "peak_kwh": self._monthly_data.get("import_peak", 0),
                "offpeak_kwh": self._monthly_data.get("import_offpeak", 0),
                "export_kwh": self._monthly_data.get("export_total", 0),
            }
            
            # Keep only last 12 months
            if len(self._historical_months) > 12:
                oldest_keys = sorted(self._historical_months.keys())[:-12]
                for old_key in oldest_keys:
                    del self._historical_months[old_key]
            
            _LOGGER.info("Saved month %s to historical data: %.2f kWh, RM %.2f",
                        month_key,
                        self._historical_months[month_key]["total_kwh"],
                        self._historical_months[month_key]["total_cost"])
        
        return month_changed

    def _create_month_bucket(self, now: datetime) -> Dict[str, Any]:
        """Create new monthly data bucket."""
        billing_month, billing_year = self._get_billing_period(now)
        return {
            "month": now.month,  # Keep calendar month for reference
            "year": now.year,
            "billing_month": billing_month,  # Actual billing period
            "billing_year": billing_year,
            "billing_start_day": self._billing_start_day,
            "import_total": 0.0,
            "export_total": 0.0,
            "import_peak": 0.0,
            "import_offpeak": 0.0,
            "import_last": self._get_entity_state(self._import_entity, "Import entity"),
            "export_last": self._get_entity_state(self._export_entity, "Export entity"),
            "calibration": {
                "import_baseline": 0.0,
                "peak_baseline": 0.0,
                "offpeak_baseline": 0.0,
                "export_baseline": 0.0,
                "last_calibrated": None,
                "distribution_method": None,
            },
        }

    def _day_changed(self, now: datetime) -> bool:
        """Check if day changed and reset daily data if needed."""
        if not hasattr(self, "_daily_data") or not self._daily_data:
            return True
        
        day_changed = now.date().isoformat() != self._daily_data.get("date")
        
        if day_changed:
            _LOGGER.info("Day changed from %s to %s, resetting daily counters",
                        self._daily_data.get("date"), now.date().isoformat())
        
        return day_changed

    def _create_day_bucket(self, now: datetime) -> Dict[str, Any]:
        """Create new daily data bucket."""
        return {
            "date": now.date().isoformat(),
            "import_total": 0.0,
            "export_total": 0.0,
            "import_peak": 0.0,
            "import_offpeak": 0.0,
            "import_start": self._get_entity_state(self._import_entity, "Import entity"),
            "export_start": self._get_entity_state(self._export_entity, "Export entity"),
        }

    def _compute_delta(self, current_value: float, last_key: str) -> float:
        """Compute delta from last reading, handling meter resets and spikes."""
        if not hasattr(self, "_monthly_data"):
            return 0.0
        
        last_value = self._monthly_data.get(last_key, current_value)
        delta = current_value - last_value
        
        # Handle meter reset (negative delta)
        if delta < 0:
            _LOGGER.warning(
                "Meter reset detected for %s: previous=%.3f, current=%.3f. "
                "Treating current value as delta.",
                last_key,
                last_value,
                current_value,
            )
            delta = current_value
        
        # Handle unrealistic spikes (likely sensor glitches)
        if delta > MAX_DELTA_PER_INTERVAL:
            _LOGGER.warning(
                "Spike detected for %s: delta=%.3f kWh exceeds threshold of %.1f kWh. "
                "Previous=%.3f, Current=%.3f. Ignoring this reading to prevent data corruption.",
                last_key,
                delta,
                MAX_DELTA_PER_INTERVAL,
                last_value,
                current_value,
            )
            # Don't update last_value, so next reading will compare against valid baseline
            return 0.0
        
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

    def _check_storage_health(self) -> str:
        """Check storage health status."""
        try:
            # Check if monthly data exists and has required fields
            if not hasattr(self, "_monthly_data") or not self._monthly_data:
                return "Missing"
            
            required_fields = ["month", "year", "import_total", "export_total"]
            for field in required_fields:
                if field not in self._monthly_data:
                    return "Corrupted"
            
            # Check if data is reasonable
            if self._monthly_data.get("import_total", 0) < 0:
                return "Corrupted"
            
            return "OK"
        except Exception:
            return "Error"

    async def _fetch_holidays_if_needed(self, timestamp: datetime) -> None:
        """Fetch holidays from API daily and cache them."""
        if not self._api_key:
            return
        
        now = dt_util.now()
        
        # Check if we need to fetch (once per day)
        if self._last_holiday_fetch:
            last_fetch = dt_util.parse_datetime(self._last_holiday_fetch)
            if last_fetch and (now - last_fetch).total_seconds() < 86400:  # 24 hours
                return
        
        # Fetch holidays for current year
        try:
            session = async_get_clientsession(self.hass)
            url = f"{CALENDARIFIC_BASE_URL}{CALENDARIFIC_HOLIDAYS_ENDPOINT}"
            params = {
                "api_key": self._api_key,
                "country": self._country,
                "year": timestamp.year,
                "type": "national",
            }
            
            _LOGGER.info("Fetching holidays for year %s from Calendarific API", timestamp.year)
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    holidays = data.get("response", {}).get("holidays", [])
                    
                    # Clear old cache for this year and rebuild
                    year_prefix = f"{timestamp.year}-"
                    self._holiday_cache = {
                        k: v for k, v in self._holiday_cache.items() 
                        if not k.startswith(year_prefix)
                    }
                    
                    # Cache all holidays for the year
                    for holiday in holidays:
                        holiday_date = holiday.get("date", {}).get("iso")
                        holiday_name = holiday.get("name", "").lower()
                        
                        # Skip Hari Raya Haji Day 2 - TNB only recognizes 1 day
                        if holiday_date and "haji" in holiday_name and "day 2" in holiday_name:
                            _LOGGER.debug("Skipping %s (TNB only recognizes 1 day of Hari Raya Haji)", holiday_date)
                            continue
                            
                        if holiday_date:
                            self._holiday_cache[holiday_date] = True
                    
                    # Add TNB-specific holidays that Calendarific misses
                    # New Year's Day is always a TNB holiday but not in Calendarific's "national" type
                    new_year_date = f"{timestamp.year}-01-01"
                    if new_year_date not in self._holiday_cache:
                        self._holiday_cache[new_year_date] = True
                        _LOGGER.info("Added New Year's Day %s (TNB official holiday)", new_year_date)
                    
                    self._last_holiday_fetch = now.isoformat()
                    await self._save_monthly_data()
                    _LOGGER.info("Successfully cached %d holidays for %s (matching TNB's 15 official holidays)", 
                               len([k for k in self._holiday_cache.keys() if k.startswith(year_prefix)]),
                               timestamp.year)
                else:
                    _LOGGER.warning(
                        "Failed to fetch holidays: HTTP %s. Using cached data if available.",
                        response.status
                    )
        except Exception as ex:
            _LOGGER.error("Error fetching holidays: %s. Using cached data if available.", ex)
    
    async def _is_holiday(self, timestamp: datetime) -> bool:
        """Check if the date is a holiday using cached data."""
        if not self._api_key:
            return False
        
        date_str = timestamp.strftime("%Y-%m-%d")
        
        # Check cache
        if date_str in self._holiday_cache:
            return self._holiday_cache[date_str]
        
        # Not in cache means it's not a holiday (already fetched all holidays for the year)
        return False

    def _calculate_tou_costs(
        self,
        import_peak: float,
        import_offpeak: float,
        export_total: float,
    ) -> Dict[str, Any]:
        """Calculate ToU-based costs following the template exactly."""
        # Derived quantities (Excel: E2,E6,E7)
        import_total = import_peak + import_offpeak
        export_peak = min(import_peak, export_total)
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
            "rate_import": 0.0,  # Not used in ToU (uses peak/offpeak instead)
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
            "rate_import": 0.2703,  # Generation rate for non-ToU
            "rate_capacity": 0.0455,
            "rate_network": 0.1285,
            "rate_ict": ict_rate,
        }

    def _calculate_predictions(
        self,
        now: datetime,
        monthly_import: float,
        monthly_peak: float,
        monthly_offpeak: float,
        monthly_export: float,
    ) -> Dict[str, Any]:
        """Calculate hybrid cost predictions (Method 2 + Method 3)."""
        days_elapsed = now.day
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        days_remaining = days_in_month - days_elapsed
        
        # Initialize predictions
        predictions = {
            "predicted_monthly_cost": 0.0,
            "predicted_monthly_kwh": 0.0,
            "predicted_from_trend": None,
            "predicted_from_history": None,
            "prediction_confidence": "Low",
            "daily_average_cost": 0.0,
            "daily_average_kwh": 0.0,
            "days_remaining": days_remaining,
        }
        
        if days_elapsed == 0:
            return predictions
        
        # Calculate daily averages
        daily_avg_kwh = monthly_import / days_elapsed
        current_cost = self._last_calculated_cost
        daily_avg_cost = current_cost / days_elapsed
        
        predictions["daily_average_kwh"] = self._round_energy(daily_avg_kwh)
        predictions["daily_average_cost"] = self._round_currency(daily_avg_cost)
        
        # METHOD 2: Direct cost-based prediction (simplified and more accurate)
        # Instead of projecting kWh then recalculating cost, directly average the cost
        base_prediction = daily_avg_cost * days_in_month
        tolerance_percent = 0.05  # 5% dynamic tolerance
        tolerance = base_prediction * tolerance_percent
        
        trend_prediction = base_prediction
        predictions["predicted_from_trend"] = self._round_currency(trend_prediction)
        predictions["prediction_tolerance"] = self._round_currency(tolerance)
        predictions["prediction_range_min"] = self._round_currency(base_prediction - tolerance)
        predictions["prediction_range_max"] = self._round_currency(base_prediction + tolerance)
        
        # Still project kWh for reference (informational only)
        projected_import = (monthly_import / days_elapsed) * days_in_month
        predictions["predicted_monthly_kwh"] = self._round_energy(projected_import)
        
        # METHOD 3: Historical average prediction (if available)
        historical_prediction = None
        if len(self._historical_months) >= 2:
            # Average of last 3 months (or fewer if not available)
            recent_months = list(self._historical_months.values())[-3:]
            avg_historical_kwh = sum(m["total_kwh"] for m in recent_months) / len(recent_months)
            
            # Calculate cost at historical average
            if self._tou_enabled:
                # Use current peak/offpeak ratio
                if monthly_import > 0:
                    peak_ratio = monthly_peak / monthly_import
                else:
                    # Use historical ratio if available
                    hist_peak_ratio = sum(m.get("peak_kwh", 0) for m in recent_months) / sum(m.get("total_kwh", 1) for m in recent_months)
                    peak_ratio = hist_peak_ratio if hist_peak_ratio > 0 else 0.6
                
                hist_peak = avg_historical_kwh * peak_ratio
                hist_offpeak = avg_historical_kwh * (1 - peak_ratio)
                hist_export = sum(m.get("export_kwh", 0) for m in recent_months) / len(recent_months)
                
                hist_costs = self._calculate_tou_costs(hist_peak, hist_offpeak, hist_export)
                historical_prediction = hist_costs["total_cost"]
            else:
                hist_export = sum(m.get("export_kwh", 0) for m in recent_months) / len(recent_months)
                hist_costs = self._calculate_non_tou_costs(avg_historical_kwh, hist_export)
                historical_prediction = hist_costs["total_cost"]
            
            predictions["predicted_from_history"] = self._round_currency(historical_prediction)
            
            # HYBRID: Weighted prediction based on days elapsed
            if days_elapsed < 7:
                # Early month: trust history more (70% history, 30% trend)
                weight_trend = 0.3
            elif days_elapsed > 20:
                # Late month: trust current trend more (80% trend, 20% history)
                weight_trend = 0.8
            else:
                # Mid month: balanced (60% trend, 40% history)
                weight_trend = 0.6
            
            weight_history = 1 - weight_trend
            hybrid_prediction = (trend_prediction * weight_trend + 
                               historical_prediction * weight_history)
            
            predictions["predicted_monthly_cost"] = self._round_currency(hybrid_prediction)
            
            # Set confidence level
            months_count = len(self._historical_months)
            if months_count >= 3:
                predictions["prediction_confidence"] = "High"
            elif months_count >= 1:
                predictions["prediction_confidence"] = "Medium"
            else:
                predictions["prediction_confidence"] = "Low"
            
            # Populate prediction method sensor
            predictions["prediction_method"] = "Hybrid (Cost + History)"
            predictions["prediction_method_details"] = {
                "method": "hybrid",
                "trend_weight": int(weight_trend * 100),
                "history_weight": int(weight_history * 100),
                "historical_months": months_count,
                "description": f"Using hybrid prediction: {int(weight_trend * 100)}% cost trend (RM {trend_prediction:.2f}) + {int(weight_history * 100)}% historical average (RM {historical_prediction:.2f}) = RM {hybrid_prediction:.2f}"
            }
        else:
            # No history: use Method 2 only
            predictions["predicted_monthly_cost"] = self._round_currency(trend_prediction)
            predictions["prediction_confidence"] = "Low" if days_elapsed < 7 else "Medium"
            
            # Populate prediction method sensor
            predictions["prediction_method"] = "Cost Trend"
            predictions["prediction_method_details"] = {
                "method": "cost_trend",
                "trend_weight": 100,
                "history_weight": 0,
                "historical_months": 0,
                "description": f"Using direct cost averaging: RM {current_cost:.2f} over {days_elapsed} days = RM {daily_avg_cost:.2f}/day × {days_in_month} days = RM {trend_prediction:.2f} ± {tolerance:.2f}"
            }
        
        return predictions


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
        entity_category: Optional[str],
        entry_id: str,
        device_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = f"{DEFAULT_NAME} {name}"
        self._attr_unique_id = f"{entry_id}_{sensor_type}"
        self._attr_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_entity_category = entity_category
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry_id)},
            "name": DEFAULT_NAME,
            "manufacturer": "Cikgu Saleh",
            "model": "TNB Calculator",
            "sw_version": "3.7.3e",
        }

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
            "cached_holidays": self.coordinator.data.get("cached_holidays"),
            "cached_holidays_last_fetch": self.coordinator.data.get("cached_holidays_last_fetch"),
        }
        
        # Add prediction method details as attributes
        if self._sensor_type == "prediction_method":
            method_details = self.coordinator.data.get("prediction_method_details", {})
            attrs.update({
                "method": method_details.get("method"),
                "trend_weight": method_details.get("trend_weight"),
                "history_weight": method_details.get("history_weight"),
                "historical_months": method_details.get("historical_months"),
                "days_elapsed": self.coordinator.data.get("days_remaining"),
                "daily_average_cost": self.coordinator.data.get("daily_average_cost"),
                "description": method_details.get("description"),
            })
            return attrs
        
        # Add configuration scenario details as attributes
        if self._sensor_type == "configuration_scenario":
            scenario_details = self.coordinator.data.get("configuration_scenario_details", {})
            attrs.update(scenario_details)
            return attrs

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


class TNBBillingStartDayNumber(CoordinatorEntity, NumberEntity):
    """Number entity to set billing start day."""
    
    _attr_native_min_value = 1
    _attr_native_max_value = 31
    _attr_native_step = 1
    _attr_mode = "box"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-start"
    
    def __init__(
        self,
        coordinator: TNBDataCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"{DEFAULT_NAME} Billing Start Day"
        self._attr_unique_id = f"{config_entry.entry_id}_billing_start_day"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
        }
    
    @property
    def native_value(self) -> float:
        """Return the current billing start day."""
        return self.coordinator._billing_start_day
    
    async def async_set_native_value(self, value: float) -> None:
        """Update billing start day."""
        new_day = int(value)
        
        # Update config entry
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            data={**self._config_entry.data, CONF_BILLING_START_DAY: new_day}
        )
        
        # Update coordinator
        self.coordinator._billing_start_day = new_day
        
        # Trigger refresh
        await self.coordinator.async_request_refresh()
