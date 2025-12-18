"""Sensor platform for TNB Calculator integration."""
import asyncio
import calendar
import logging
from datetime import datetime, time, timedelta
from typing import Any, Dict, Optional, Tuple, Union

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
    # Tariff constants
    DEFAULT_AFA_RATE,
    DEFAULT_AFA_THRESHOLD,
    DEFAULT_RETAILING_CHARGE,
    TARIFF_SOURCE_DEFAULT,
    TARIFF_SOURCE_MANUAL,
    TARIFF_SOURCE_API,
    TARIFF_SOURCE_WEBHOOK,
    CONF_TARIFF_API_URL,
    TARIFF_API_TIMEOUT,
    # Auto-fetch constants
    AUTO_FETCH_API_URL,
    AFA_AUTO_FETCH_API_URL,
    AUTO_FETCH_ENABLED_KEY,
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
    config = {**config_entry.data, **config_entry.options}
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
        sw_version="4.4.4",
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
    
    # Add billing start day helper entities
    billing_day_number = TNBBillingStartDayNumber(
        coordinator,
        config_entry,
        device.id,
    )
    sensors.append(billing_day_number)

    billing_day_status = TNBBillingStartDayStatusSensor(
        coordinator,
        config_entry,
        device.id,
    )
    sensors.append(billing_day_status)

    async_add_entities(sensors)
    
    # If auto-fetch was enabled before restart, re-fetch from API
    if coordinator.auto_fetch_enabled:
        _LOGGER.info("Auto-fetch was enabled - refreshing tariffs from API")
        await coordinator.async_toggle_auto_fetch(enabled=True)


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
        
        # Tariff API configuration (optional)
        self._tariff_api_url = config.get(CONF_TARIFF_API_URL)
        
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
        
        # Tariff overrides (loaded from storage, can be set via service)
        self._tariff_overrides: Dict[str, Any] = {
            "afa_rate": None,           # None = use DEFAULT_AFA_RATE
            "source": TARIFF_SOURCE_DEFAULT,
            "last_updated": None,
        }
        
        # Auto-fetch tariffs state (experimental feature)
        self._auto_fetch_enabled: bool = False
        self._auto_fetch_last_error: Optional[str] = None

    async def _load_monthly_data(self, force_reload: bool = False) -> None:
        """Load monthly data from storage."""
        if self._monthly_data_loaded and not force_reload:
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
            
            # Load tariff overrides
            stored_tariff = stored_data.get("tariff_overrides", {})
            if stored_tariff:
                self._tariff_overrides = {
                    "afa_rate": stored_tariff.get("afa_rate"),
                    "tariffs": stored_tariff.get("tariffs"),
                    "source": stored_tariff.get("source", TARIFF_SOURCE_DEFAULT),
                    "last_updated": stored_tariff.get("last_updated"),
                    "effective_date": stored_tariff.get("effective_date"),
                    "api_url": stored_tariff.get("api_url"),
                }
                if self._tariff_overrides.get("afa_rate") is not None:
                    _LOGGER.debug("Loaded tariff override - AFA rate: %s (source: %s)", 
                                 self._tariff_overrides["afa_rate"],
                                 self._tariff_overrides["source"])
            
            # Load auto-fetch state
            self._auto_fetch_enabled = stored_data.get(AUTO_FETCH_ENABLED_KEY, False)
            if self._auto_fetch_enabled:
                _LOGGER.info("Auto-fetch tariffs is enabled - will fetch from API on startup")
        else:
            self._holiday_cache = {}
            self._last_holiday_fetch = None
            self._historical_months = {}
            self._daily_data = {}
            self._daily_data_loaded = True
            # tariff_overrides already initialized in __init__ with defaults
            
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
                "tariff_overrides": getattr(self, "_tariff_overrides", {}),
                AUTO_FETCH_ENABLED_KEY: getattr(self, "_auto_fetch_enabled", False),
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
            
            # Update configuration in case options changed via reconfigure
            self._import_entity = self.config.get(CONF_IMPORT_ENTITY, self._import_entity)
            self._export_entity = self.config.get(CONF_EXPORT_ENTITY, self._export_entity)
            self._api_key = self.config.get(CONF_CALENDARIFIC_API_KEY)
            self._billing_start_day = self.config.get(CONF_BILLING_START_DAY, self._billing_start_day)
            self._tou_enabled = bool(self._api_key)

            # Load stored data (force reload to pick up calibration changes)
            await self._load_monthly_data(force_reload=True)

            # If AFA source is API (simple endpoint) and full auto-fetch is disabled,
            # refresh AFA-only rate from /afa/simple at most once per week.
            if not self._auto_fetch_enabled and self._tariff_overrides.get("source") == TARIFF_SOURCE_API:
                last_updated_str = self._tariff_overrides.get("last_updated")
                afa_should_refresh = False
                if not last_updated_str:
                    afa_should_refresh = True
                else:
                    try:
                        last_updated_dt = dt_util.parse_datetime(last_updated_str)
                        if last_updated_dt is None:
                            afa_should_refresh = True
                        else:
                            if now - last_updated_dt >= timedelta(days=7):
                                afa_should_refresh = True
                    except Exception:  # pragma: no cover - defensive
                        afa_should_refresh = True

                if afa_should_refresh:
                    # Priority: configured URL > last-used URL > hardcoded fallback
                    base_url = self._tariff_api_url or self._tariff_overrides.get("api_url")
                    if base_url:
                        # Normalise to AFA simple endpoint: strip known paths, then append /afa/simple
                        # Handles both .../afa/simple and .../complete sources.
                        base = (
                            base_url
                            .replace("/afa/simple", "")
                            .replace("/complete", "")
                            .rstrip("/")
                        )
                        afa_api_url = f"{base}/afa/simple"
                    else:
                        afa_api_url = AFA_AUTO_FETCH_API_URL

                    _LOGGER.info(
                        "AFA rate source is API and value is stale or missing - "
                        "refreshing from %s (weekly interval)",
                        afa_api_url
                    )
                    success = await self.async_fetch_afa_rate(api_url=afa_api_url)
                    if not success:
                        _LOGGER.warning(
                            "Weekly AFA auto-fetch refresh failed - keeping existing AFA rate"
                        )

            # If auto-fetch is enabled, refresh full tariffs from /complete at most once per week
            if self._auto_fetch_enabled:
                last_updated_str = self._tariff_overrides.get("last_updated")
                should_refresh = False
                if not last_updated_str:
                    should_refresh = True
                else:
                    try:
                        last_updated_dt = dt_util.parse_datetime(last_updated_str)
                        if last_updated_dt is None:
                            should_refresh = True
                        else:
                            # Refresh if more than 7 days have passed since last update
                            if now - last_updated_dt >= timedelta(days=7):
                                should_refresh = True
                    except Exception:  # pragma: no cover - defensive
                        should_refresh = True

                if should_refresh:
                    _LOGGER.info(
                        "Auto-fetch is enabled and tariffs are stale or missing - "
                        "refreshing from API (weekly interval)"
                    )
                    success = await self.async_toggle_auto_fetch(enabled=True)
                    if not success:
                        _LOGGER.warning(
                            "Weekly auto-fetch refresh failed - keeping existing tariffs"
                        )

            import_total = self._get_entity_state(self._import_entity, "Import entity", is_optional=False)
            export_total = self._get_entity_state(self._export_entity, "Export entity", is_optional=True)

            if not hasattr(self, "_monthly_data") or self._month_changed(now):
                self._monthly_data = self._create_month_bucket(now)
                await self._save_monthly_data()

            # Check and reset daily data if day changed
            if not hasattr(self, "_daily_data") or self._day_changed(now):
                self._daily_data = self._create_day_bucket(now)
                await self._save_monthly_data()

            import_delta = self._compute_delta(import_total, "import_last")
            export_delta = self._compute_delta(export_total, "export_last")

            is_holiday = False
            if self._tou_enabled:
                # Fetch holidays daily
                await self._fetch_holidays_if_needed(now)
                is_holiday = await self._is_holiday(now)

            # Get last update timestamp for boundary-aware daily split
            last_update_ts_str = self._daily_data.get("last_update_ts")
            if last_update_ts_str:
                try:
                    last_update_ts = dt_util.parse_datetime(last_update_ts_str)
                except (ValueError, TypeError):
                    last_update_ts = now
            else:
                last_update_ts = now

            data_changed = False
            if import_delta > 0:
                # Update monthly totals (unchanged logic)
                self._monthly_data["import_total"] += import_delta
                if self._tou_enabled:
                    if self._is_peak_period(now, is_holiday):
                        self._monthly_data["import_peak"] += import_delta
                    else:
                        self._monthly_data["import_offpeak"] += import_delta
                
                # Update daily totals using delta-based accumulation
                self._daily_data["import_total"] = self._daily_data.get("import_total", 0.0) + import_delta
                
                # Split delta into peak/off-peak using boundary-aware logic
                if self._tou_enabled:
                    peak_delta, offpeak_delta = self._split_delta_by_period(
                        import_delta, last_update_ts, now, is_holiday
                    )
                    self._daily_data["import_peak"] = self._daily_data.get("import_peak", 0.0) + peak_delta
                    self._daily_data["import_offpeak"] = self._daily_data.get("import_offpeak", 0.0) + offpeak_delta
                
                data_changed = True

            if export_delta > 0:
                # Update monthly export (unchanged)
                self._monthly_data["export_total"] += export_delta
                # Update daily export using delta-based accumulation
                self._daily_data["export_total"] = self._daily_data.get("export_total", 0.0) + export_delta
                data_changed = True

            # Update last_update_ts for next interval's boundary calculation
            self._daily_data["last_update_ts"] = now.isoformat()

            # Save data after changes
            if data_changed:
                await self._save_monthly_data()

            self._state["timestamp"] = now

            # Get monthly totals
            monthly_import = self._monthly_data["import_total"]
            monthly_export = self._monthly_data["export_total"]
            monthly_peak = self._monthly_data["import_peak"]
            monthly_offpeak = self._monthly_data["import_offpeak"]

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

            current_billing_day = self._monthly_data.get("billing_start_day", self._billing_start_day)
            pending_billing_day = self._billing_start_day if self._billing_start_day != current_billing_day else None

            result: Dict[str, Any] = {
                "import_energy": self._round_energy(monthly_import),
                "export_energy": self._round_energy(monthly_export),
                "net_energy": self._round_energy(monthly_import - monthly_export),
                "day_status": day_status,
                "period_status": period_status,
                "last_update": now.isoformat(),
                "current_month": now.strftime("%Y-%m"),
                "billing_start_day": current_billing_day,
                "billing_start_day_active": current_billing_day,
                "billing_start_day_configured": self._billing_start_day,
                "billing_start_day_pending": pending_billing_day,
                "monthly_reset_day": current_billing_day,  # Deprecated, kept for compatibility
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
            
            # Calculate optimization sensors (AFA sweet spot analysis)
            optimization_data = self._calculate_optimization_data()
            result["ideal_import_kwh"] = optimization_data["ideal_import_kwh"]
            result["ideal_import_kwh_tou"] = optimization_data["ideal_import_kwh_tou"]
            result["ideal_import_kwh_non_tou"] = optimization_data["ideal_import_kwh_non_tou"]
            result["savings_if_ideal_kwh"] = optimization_data["savings_if_ideal_kwh"]
            result["afa_optimization_savings"] = optimization_data["afa_optimization_savings"]
            result["afa_weird_zone"] = "on" if optimization_data["afa_weird_zone"] else "off"
            result["afa_value_zone"] = "on" if optimization_data["afa_value_zone"] else "off"
            # For afa_explanation, keep state as short zone label (normal/weird/value/stay_put/above_threshold)
            # and expose full human-readable explanation via attributes.
            result["afa_explanation"] = optimization_data["optimization_zone"]
            # Store full optimization data for sensor attributes
            result["_optimization_data"] = optimization_data
            
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
        # Check ToU status dynamically in case API key was added after init
        tou_enabled = bool(self._api_key)
        
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
        # Ensure monthly data is loaded
        await self._load_monthly_data()
        
        if not hasattr(self, "_monthly_data") or not self._monthly_data:
            _LOGGER.error("Monthly data not available. Cannot set energy values.")
            raise ValueError("Monthly data not initialized. Please wait for integration to fully load.")
        
        import_total = call.data["import_total"]
        distribution = call.data.get("distribution", "proportional")
        
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
            is_holiday = await self._is_holiday(now)
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
        sensor_import = self._get_entity_state(self._import_entity, "Import", is_optional=False)
        
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
        
        # Log calibration
        _LOGGER.info(
            "Energy calibration applied: Import %.2f kWh (Peak: %.2f, Off-peak: %.2f) using '%s' distribution",
            import_total, new_peak, new_offpeak, distribution
        )
        
        # Save and trigger immediate refresh
        await self._save_monthly_data()
        await self.async_refresh()
    
    async def async_adjust_import_energy_values(self, call) -> None:
        """Service to apply offset adjustments to import values with distribution options."""
        # Ensure monthly data is loaded
        await self._load_monthly_data()
        
        if not hasattr(self, "_monthly_data") or not self._monthly_data:
            _LOGGER.error("Monthly data not available. Cannot adjust import energy values.")
            raise ValueError("Monthly data not initialized. Please wait for integration to fully load.")
        
        import_adj = call.data["import_adjustment"]
        distribution = call.data.get("distribution", "proportional")
        
        # Get current values
        current_import = self._monthly_data.get("import_total", 0)
        current_peak = self._monthly_data.get("import_peak", 0)
        current_offpeak = self._monthly_data.get("import_offpeak", 0)
        
        # Distribute adjustment based on option
        if distribution == "proportional":
            # Maintain current ratio
            if current_import > 0:
                peak_ratio = current_peak / current_import
            else:
                peak_ratio = 0.6
            
            peak_adj = import_adj * peak_ratio
            offpeak_adj = import_adj * (1 - peak_ratio)
        
        elif distribution == "peak_only":
            peak_adj = import_adj
            offpeak_adj = 0
        
        elif distribution == "offpeak_only":
            peak_adj = 0
            offpeak_adj = import_adj
        
        elif distribution == "auto":
            now = dt_util.now()
            is_holiday = await self._is_holiday(now)
            is_peak = self._is_peak_period(now, is_holiday)
            
            if is_peak:
                peak_adj = import_adj
                offpeak_adj = 0
                _LOGGER.info("Auto-distribution: Applied to peak (current time is peak period)")
            else:
                peak_adj = 0
                offpeak_adj = import_adj
                _LOGGER.info("Auto-distribution: Applied to off-peak (current time is off-peak period)")
        
        elif distribution == "manual":
            peak_adj = call.data.get("peak_adjustment")
            offpeak_adj = call.data.get("offpeak_adjustment")
            
            if peak_adj is None or offpeak_adj is None:
                raise ValueError("peak_adjustment and offpeak_adjustment required when distribution='manual'")
            
            # Validate sum equals import_adj
            if abs((peak_adj + offpeak_adj) - import_adj) > 0.01:
                raise ValueError(f"Peak ({peak_adj}) + Off-peak ({offpeak_adj}) must equal Import Adjustment ({import_adj})")
        
        else:
            raise ValueError(f"Invalid distribution option: {distribution}")
        
        # Apply adjustments
        self._monthly_data["import_total"] += import_adj
        self._monthly_data["import_peak"] += peak_adj
        self._monthly_data["import_offpeak"] += offpeak_adj
        
        # Update calibration
        if "calibration" not in self._monthly_data:
            self._monthly_data["calibration"] = {}
        
        self._monthly_data["calibration"]["import_baseline"] = self._monthly_data["calibration"].get("import_baseline", 0) + import_adj
        self._monthly_data["calibration"]["peak_baseline"] = self._monthly_data["calibration"].get("peak_baseline", 0) + peak_adj
        self._monthly_data["calibration"]["offpeak_baseline"] = self._monthly_data["calibration"].get("offpeak_baseline", 0) + offpeak_adj
        self._monthly_data["calibration"]["last_calibrated"] = dt_util.now().isoformat()
        
        # Log adjustment
        _LOGGER.info(
            "Import adjustment applied: Import %+.2f kWh (Peak: %+.2f, Off-peak: %+.2f) using '%s' distribution",
            import_adj, peak_adj, offpeak_adj, distribution
        )
        
        # Save and trigger immediate refresh
        await self._save_monthly_data()
        await self.async_refresh()
    
    async def async_adjust_export_energy_values(self, call) -> None:
        """Service to apply offset adjustment to export value."""
        # Ensure monthly data is loaded
        await self._load_monthly_data()
        
        if not hasattr(self, "_monthly_data") or not self._monthly_data:
            _LOGGER.error("Monthly data not available. Cannot adjust export energy values.")
            raise ValueError("Monthly data not initialized. Please wait for integration to fully load.")
        
        export_adj = call.data["export_adjustment"]
        
        # Apply adjustment
        self._monthly_data["export_total"] += export_adj
        
        # Update calibration
        if "calibration" not in self._monthly_data:
            self._monthly_data["calibration"] = {}
        
        self._monthly_data["calibration"]["export_baseline"] = self._monthly_data["calibration"].get("export_baseline", 0) + export_adj
        self._monthly_data["calibration"]["last_calibrated"] = dt_util.now().isoformat()
        
        # Log adjustment
        _LOGGER.info(
            "Export adjustment applied: Export %+.2f kWh",
            export_adj
        )
        
        # Save and trigger immediate refresh
        await self._save_monthly_data()
        await self.async_refresh()
    
    async def async_set_export_values(self, call) -> None:
        """Service to set exact export energy value."""
        # Ensure monthly data is loaded
        await self._load_monthly_data()
        
        if not hasattr(self, "_monthly_data") or not self._monthly_data:
            _LOGGER.error("Monthly data not available. Cannot set export values.")
            raise ValueError("Monthly data not initialized. Please wait for integration to fully load.")
        
        export_total = call.data["export_total"]
        
        # Get sensor reading for baseline calculation
        sensor_export = self._get_entity_state(self._export_entity, "Export", is_optional=True)
        
        # Calculate baseline (offset from sensor)
        export_baseline = export_total - sensor_export
        
        # Store calibration
        if "calibration" not in self._monthly_data:
            self._monthly_data["calibration"] = {}
        
        self._monthly_data["calibration"]["export_baseline"] = export_baseline
        self._monthly_data["calibration"]["last_calibrated"] = dt_util.now().isoformat()
        
        # Update value
        self._monthly_data["export_total"] = export_total
        
        # Log calibration
        _LOGGER.info(
            "Export calibration applied: Export %.2f kWh",
            export_total
        )
        
        # Save and trigger immediate refresh
        await self._save_monthly_data()
        await self.async_refresh()

    async def async_set_afa_rate(
        self,
        afa_rate: Optional[float] = None,
    ) -> None:
        """Manually set the AFA rate via service call.
        
        This method is for manual AFA rate overrides only.
        For API updates, use async_fetch_afa_rate or async_fetch_all_rates.
        
        Args:
            afa_rate: AFA rate in MYR/kWh (e.g., 0.0891). Must be positive.
        """
        if afa_rate is not None:
            if afa_rate < 0 or afa_rate > 1:
                _LOGGER.warning("Invalid AFA rate: %s (must be 0-1)", afa_rate)
                return
            
            self._tariff_overrides["afa_rate"] = afa_rate
            self._tariff_overrides["source"] = TARIFF_SOURCE_MANUAL
            self._tariff_overrides["last_updated"] = dt_util.now().isoformat()
            
            _LOGGER.info(
                "AFA rate set manually - AFA: %.4f MYR/kWh (source: %s)",
                afa_rate,
                TARIFF_SOURCE_MANUAL
            )
            
            await self._save_monthly_data()
            await self.async_refresh()

    async def async_reset_tariff_rates(self) -> None:
        """Reset ALL tariff rates to hardcoded defaults.
        
        Clears all overrides (AFA, tariffs, etc.) and reverts to:
        - AFA: 0.0145 MYR/kWh (DEFAULT_AFA_RATE)
        - ToU rates: 0.2852/0.2443/0.3852/0.3443
        - Non-ToU: 0.2703
        - Capacity: 0.0455
        - Network: 0.1285
        - Retailing: 10.00
        - ICT: hardcoded tiers
        """
        self._tariff_overrides = {
            "afa_rate": None,  # Will use DEFAULT_AFA_RATE
            "tariffs": None,   # Will use hardcoded values
            "source": TARIFF_SOURCE_DEFAULT,
            "last_updated": dt_util.now().isoformat(),
            "effective_date": None,
            "api_url": None,
        }
        
        _LOGGER.info("All tariff rates reset to hardcoded defaults")
        
        await self._save_monthly_data()
        await self.async_refresh()

    async def async_fetch_afa_rate(self, api_url: Optional[str] = None) -> bool:
        """Fetch AFA rate from /afa/simple API endpoint.
        
        Expected API response format:
        {
            "afa_rate": 0.0891,
            "afa_rate_raw": -0.0891,
            "effective_date": "2025-11-01",
            "last_scraped": "2025-11-29T10:00:00"
        }
        
        Args:
            api_url: Override URL (uses configured URL if not provided)
            
        Returns:
            True if fetch was successful, False otherwise
        """
        url = api_url or self._tariff_api_url
        
        if not url:
            _LOGGER.warning("No tariff API URL configured")
            return False
        
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, timeout=TARIFF_API_TIMEOUT) as response:
                if response.status != 200:
                    _LOGGER.error("AFA API returned status %d", response.status)
                    return False
                
                data = await response.json()
                
                # Extract AFA rate from response
                afa_rate = data.get("afa_rate")
                if afa_rate is None:
                    _LOGGER.error("AFA API response missing 'afa_rate' field")
                    return False
                
                # Validate range
                if not (0 <= afa_rate <= 1):
                    _LOGGER.error("Invalid AFA rate from API: %s (must be 0-1)", afa_rate)
                    return False
                
                # Update tariff overrides
                self._tariff_overrides["afa_rate"] = afa_rate
                self._tariff_overrides["source"] = TARIFF_SOURCE_API
                self._tariff_overrides["last_updated"] = dt_util.now().isoformat()
                self._tariff_overrides["api_url"] = url
                
                if "effective_date" in data:
                    self._tariff_overrides["effective_date"] = data["effective_date"]
                
                _LOGGER.info(
                    "AFA rate fetched from API - AFA: %.4f MYR/kWh (url: %s)",
                    afa_rate,
                    url
                )
                
                await self._save_monthly_data()
                await self.async_refresh()
                return True
                
        except asyncio.TimeoutError:
            _LOGGER.error("AFA API request timed out after %ds", TARIFF_API_TIMEOUT)
            return False
        except Exception as ex:
            _LOGGER.error("Failed to fetch AFA rate from API: %s", ex)
            return False

    async def async_fetch_all_rates(self, api_url: Optional[str] = None) -> bool:
        """Fetch all tariff rates from /complete API endpoint.
        
        Expected API response format:
        {
            "last_scraped": "2025-11-29T11:31:36",
            "current_rate": {
                "afa_rate": 0.0891,
                "effective_date": "2025-11-01"
            },
            "tariffs": {
                "non_tou": {
                    "tier1": {"generation": 0.2703},
                    "tier2": {"generation": 0.3703},
                    "threshold_kwh": 600
                },
                "tou": {
                    "tier1": {"generation_peak": 0.2852, "generation_offpeak": 0.2443},
                    "tier2": {"generation_peak": 0.3852, "generation_offpeak": 0.3443},
                    "threshold_kwh": 1500
                },
                "shared": {
                    "capacity": 0.0455,
                    "network": 0.1285,
                    "retailing": 10.0
                },
                "ict_tiers": [...]
            }
        }
        
        Args:
            api_url: Override URL (uses configured URL with /complete path if not provided)
            
        Returns:
            True if fetch was successful, False otherwise
        """
        # If no URL provided, try to construct from configured base URL
        if api_url:
            url = api_url
        elif self._tariff_api_url:
            # Replace /afa/simple with /complete if present, or append /complete
            base_url = self._tariff_api_url.replace("/afa/simple", "").rstrip("/")
            url = f"{base_url}/complete"
        else:
            _LOGGER.warning("No tariff API URL configured")
            return False
        
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, timeout=TARIFF_API_TIMEOUT) as response:
                if response.status != 200:
                    _LOGGER.error("Complete API returned status %d", response.status)
                    return False
                
                data = await response.json()
                
                # Extract and validate current_rate for AFA
                current_rate = data.get("current_rate", {})
                afa_rate = current_rate.get("afa_rate")
                if afa_rate is None:
                    _LOGGER.error("Complete API response missing 'current_rate.afa_rate'")
                    return False
                
                if not (0 <= afa_rate <= 1):
                    _LOGGER.error("Invalid AFA rate from API: %s (must be 0-1)", afa_rate)
                    return False
                
                # Extract tariffs
                tariffs = data.get("tariffs", {})
                
                # Update all tariff overrides
                self._tariff_overrides["afa_rate"] = afa_rate
                self._tariff_overrides["source"] = TARIFF_SOURCE_API
                self._tariff_overrides["last_updated"] = dt_util.now().isoformat()
                self._tariff_overrides["api_url"] = url
                
                if current_rate.get("effective_date"):
                    self._tariff_overrides["effective_date"] = current_rate["effective_date"]
                
                # Store full tariff data for future use
                if tariffs:
                    self._tariff_overrides["tariffs"] = tariffs
                    
                    # Log what was fetched
                    non_tou = tariffs.get("non_tou", {})
                    tou = tariffs.get("tou", {})
                    shared = tariffs.get("shared", {})
                    ict_count = len(tariffs.get("ict_tiers", []))
                    
                    _LOGGER.info(
                        "All rates fetched from API - AFA: %.4f, "
                        "Non-ToU: tier1=%.4f/tier2=%.4f, "
                        "ToU: peak=%.4f-%.4f/offpeak=%.4f-%.4f, "
                        "Shared: cap=%.4f/net=%.4f/ret=%.2f, "
                        "ICT: %d tiers (url: %s)",
                        afa_rate,
                        non_tou.get("tier1", {}).get("generation", 0),
                        non_tou.get("tier2", {}).get("generation", 0),
                        tou.get("tier1", {}).get("generation_peak", 0),
                        tou.get("tier2", {}).get("generation_peak", 0),
                        tou.get("tier1", {}).get("generation_offpeak", 0),
                        tou.get("tier2", {}).get("generation_offpeak", 0),
                        shared.get("capacity", 0),
                        shared.get("network", 0),
                        shared.get("retailing", 0),
                        ict_count,
                        url
                    )
                else:
                    _LOGGER.info(
                        "AFA rate fetched from complete API - AFA: %.4f MYR/kWh (url: %s)",
                        afa_rate,
                        url
                    )
                
                await self._save_monthly_data()
                await self.async_refresh()
                return True
                
        except asyncio.TimeoutError:
            _LOGGER.error("Complete API request timed out after %ds", TARIFF_API_TIMEOUT)
            return False
        except Exception as ex:
            _LOGGER.error("Failed to fetch all rates from API: %s", ex)
            return False

    async def async_toggle_auto_fetch(self, enabled: bool) -> bool:
        """Toggle auto-fetch tariffs feature.
        
        When enabled: Fetches all rates from AUTO_FETCH_API_URL and uses API data.
        When disabled: Resets ALL tariff overrides to hardcoded defaults.
        
        Args:
            enabled: True to enable auto-fetch (use API rates), False to disable (use hardcoded)
            
        Returns:
            True if operation was successful, False otherwise
        """
        if enabled:
            # Fetch all rates from the hardcoded API URL
            _LOGGER.info("Auto-fetch enabled - fetching tariffs from %s", AUTO_FETCH_API_URL)
            self._auto_fetch_last_error = None
            
            success = await self.async_fetch_all_rates(api_url=AUTO_FETCH_API_URL)
            
            if success:
                self._auto_fetch_enabled = True
                _LOGGER.info(
                    "Auto-fetch tariffs enabled successfully - using live TNB rates from API"
                )
                await self._save_monthly_data()
                return True
            else:
                self._auto_fetch_last_error = "Failed to fetch rates from API"
                _LOGGER.error(
                    "Auto-fetch failed - keeping current rates. Error: %s",
                    self._auto_fetch_last_error
                )
                return False
        else:
            # Disable auto-fetch and reset ALL tariff overrides
            _LOGGER.info("Auto-fetch disabled - resetting all tariff rates to hardcoded defaults")
            
            self._auto_fetch_enabled = False
            self._auto_fetch_last_error = None
            
            # Reset ALL tariff overrides (including AFA)
            self._tariff_overrides = {
                "afa_rate": None,       # Will use DEFAULT_AFA_RATE
                "tariffs": None,        # Will use hardcoded values
                "source": TARIFF_SOURCE_DEFAULT,
                "last_updated": dt_util.now().isoformat(),
                "effective_date": None,
                "api_url": None,
            }
            
            _LOGGER.info(
                "All tariff rates reset to hardcoded defaults (AFA: %.4f MYR/kWh)",
                DEFAULT_AFA_RATE
            )
            
            await self._save_monthly_data()
            await self.async_refresh()
            return True

    @property
    def auto_fetch_enabled(self) -> bool:
        """Return whether auto-fetch is enabled."""
        return self._auto_fetch_enabled

    @property
    def auto_fetch_last_error(self) -> Optional[str]:
        """Return the last auto-fetch error message, if any."""
        return self._auto_fetch_last_error

    async def async_update_tariff_from_webhook(self, data: Dict[str, Any]) -> bool:
        """Update tariff rates from webhook payload.
        
        Expected webhook payload format:
        {
            "afa_rate": 0.0145,
            "effective_date": "2025-01-01"  // optional
        }
        
        Args:
            data: Webhook payload dictionary
            
        Returns:
            True if update was successful, False otherwise
        """
        afa_rate = data.get("afa_rate")
        
        if afa_rate is None:
            _LOGGER.error("Webhook payload missing 'afa_rate' field")
            return False
        
        # Validate type and range
        try:
            afa_rate = float(afa_rate)
        except (ValueError, TypeError):
            _LOGGER.error("Invalid AFA rate from webhook: %s (not a number)", afa_rate)
            return False
        
        if not (0 <= afa_rate <= 1):
            _LOGGER.error("Invalid AFA rate from webhook: %s (must be 0-1)", afa_rate)
            return False
        
        # Update tariff overrides
        self._tariff_overrides["afa_rate"] = afa_rate
        self._tariff_overrides["source"] = TARIFF_SOURCE_WEBHOOK
        self._tariff_overrides["last_updated"] = dt_util.now().isoformat()
        
        if "effective_date" in data:
            self._tariff_overrides["effective_date"] = data["effective_date"]
        
        _LOGGER.info(
            "Tariff rates updated from webhook - AFA: %.4f RM/kWh",
            afa_rate
        )
        
        await self._save_monthly_data()
        await self.async_refresh()
        return True

    def _get_entity_state(self, entity_id: Optional[str], source: str, is_optional: bool = False) -> float:
        """Get numeric state from entity, return 0.0 if unavailable.
        
        Args:
            entity_id: Entity ID to read
            source: Source name for logging (e.g., "Import entity", "Export entity")
            is_optional: If True, don't log validation errors for missing/unconfigured entities
                        (still return 0.0 gracefully). Errors are still recorded for diagnostics.
        """
        if not entity_id:
            if not is_optional:
                self._add_validation_error(source, "entity not configured")
            return 0.0

        state = self.hass.states.get(entity_id)
        if state is None:
            if not is_optional:
                self._add_validation_error(source, f"entity '{entity_id}' not found")
            return 0.0

        if state.state in ["unknown", "unavailable"]:
            if not is_optional:
                self._add_validation_error(source, f"entity '{entity_id}' state is {state.state}")
            return 0.0

        try:
            return float(state.state)
        except (ValueError, TypeError):
            if not is_optional:
                self._add_validation_error(source, f"entity '{entity_id}' reported non-numeric state '{state.state}'")
            return 0.0

    def _get_tariff_rate(self, key: str, default: float) -> float:
        """Get tariff rate from overrides or return default.
        
        This abstraction allows future sources (API, webhook) to update rates
        while keeping calculation code unchanged.
        
        Args:
            key: The tariff key (e.g., "afa_rate")
            default: Default value if no override is set
            
        Returns:
            The overridden value or default
        """
        value = self._tariff_overrides.get(key)
        return value if value is not None else default

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
            "import_last": self._get_entity_state(self._import_entity, "Import entity", is_optional=False),
            "export_last": self._get_entity_state(self._export_entity, "Export entity", is_optional=True),
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
        """Create new daily data bucket.
        
        Daily totals are accumulated via deltas (like monthly), ensuring:
        - import_peak + import_offpeak == import_total (within rounding)
        - Accurate ToU split based on actual usage timing
        """
        return {
            "date": now.date().isoformat(),
            "import_total": 0.0,
            "export_total": 0.0,
            "import_peak": 0.0,
            "import_offpeak": 0.0,
            "last_update_ts": now.isoformat(),  # For boundary-aware delta splitting
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

    # =========================================================================
    # TARIFF RATE HELPERS - Read from stored tariffs with hardcoded fallbacks
    # =========================================================================

    def _get_stored_tariffs(self) -> Dict[str, Any]:
        """Get stored tariffs from API, or empty dict if not available."""
        return self._tariff_overrides.get("tariffs") or {}

    def _get_tou_generation_rates(self, import_total: float) -> Tuple[float, float]:
        """Get ToU generation rates (peak, offpeak) based on import threshold.
        
        Returns (peak_rate, offpeak_rate) in MYR/kWh.
        Uses stored tariffs if available, otherwise hardcoded defaults.
        """
        tariffs = self._get_stored_tariffs()
        tou = tariffs.get("tou", {})
        
        # Determine tier based on threshold (default 1500 kWh)
        threshold = tou.get("threshold_kwh", 1500)
        
        if import_total < threshold:
            tier = tou.get("tier1", {})
            peak = tier.get("generation_peak", 0.2852)
            offpeak = tier.get("generation_offpeak", 0.2443)
        else:
            tier = tou.get("tier2", {})
            peak = tier.get("generation_peak", 0.3852)
            offpeak = tier.get("generation_offpeak", 0.3443)
        
        return peak, offpeak

    def _get_non_tou_generation_rate(self) -> float:
        """Get non-ToU generation rate in MYR/kWh.
        
        Uses stored tariffs if available, otherwise hardcoded default.
        Note: Non-ToU uses tier1 rate (for ≤600 kWh threshold).
        """
        tariffs = self._get_stored_tariffs()
        non_tou = tariffs.get("non_tou", {})
        tier1 = non_tou.get("tier1", {})
        return tier1.get("generation", 0.2703)

    def _get_capacity_rate(self) -> float:
        """Get capacity rate in MYR/kWh."""
        tariffs = self._get_stored_tariffs()
        shared = tariffs.get("shared", {})
        return shared.get("capacity", 0.0455)

    def _get_network_rate(self) -> float:
        """Get network rate in MYR/kWh."""
        tariffs = self._get_stored_tariffs()
        shared = tariffs.get("shared", {})
        return shared.get("network", 0.1285)

    def _get_retailing_charge(self) -> float:
        """Get retailing charge in MYR."""
        tariffs = self._get_stored_tariffs()
        shared = tariffs.get("shared", {})
        return shared.get("retailing", DEFAULT_RETAILING_CHARGE)

    def _get_ict_rate_from_stored(self, import_kwh: float, use_tou_logic: bool = True) -> Optional[float]:
        """Get ICT rate from stored tiers if available.
        
        Args:
            import_kwh: Total import kWh for tier lookup
            use_tou_logic: If True, uses >= logic (ToU). If False, uses <= logic (non-ToU).
            
        Returns:
            ICT rate in MYR/kWh, or None if no stored tiers available.
        """
        tariffs = self._get_stored_tariffs()
        ict_tiers = tariffs.get("ict_tiers", [])
        
        if not ict_tiers:
            return None
        
        # Sort tiers by min_kwh
        sorted_tiers = sorted(ict_tiers, key=lambda x: x.get("min_kwh", 0))
        
        if use_tou_logic:
            # ToU logic: find highest tier where import_kwh >= min_kwh
            rate = sorted_tiers[0].get("rate_rm", -0.25)  # Default to first tier
            for tier in sorted_tiers:
                if import_kwh >= tier.get("min_kwh", 0):
                    rate = tier.get("rate_rm", rate)
            return rate
        else:
            # Non-ToU logic: find tier where import_kwh <= max_kwh
            for tier in sorted_tiers:
                if import_kwh <= tier.get("max_kwh", float("inf")):
                    return tier.get("rate_rm", -0.25)
            # If above all tiers, return 0 (no rebate)
            return 0.0

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

    def _split_delta_by_period(
        self, 
        delta_kwh: float, 
        start_ts: datetime, 
        end_ts: datetime, 
        is_holiday: bool
    ) -> Tuple[float, float]:
        """Split an energy delta into peak and off-peak portions based on time interval.
        
        Handles boundary crossings (2PM, 10PM) by allocating delta proportionally
        by time spent in each period. Assumes uniform usage rate within interval.
        
        Args:
            delta_kwh: Total energy delta to split
            start_ts: Start of the interval
            end_ts: End of the interval
            is_holiday: Whether the interval is during a holiday
            
        Returns:
            Tuple of (peak_kwh, offpeak_kwh) where peak + offpeak == delta_kwh
        """
        if delta_kwh <= 0:
            return (0.0, 0.0)
        
        # If holiday or weekend, all is off-peak
        if is_holiday or start_ts.weekday() >= 5:
            return (0.0, delta_kwh)
        
        # Edge case: end_ts before or equal to start_ts
        if end_ts <= start_ts:
            # Use end_ts period classification
            if self._is_peak_period(end_ts, is_holiday):
                return (delta_kwh, 0.0)
            else:
                return (0.0, delta_kwh)
        
        total_seconds = (end_ts - start_ts).total_seconds()
        if total_seconds <= 0:
            # Fallback: classify by end timestamp
            if self._is_peak_period(end_ts, is_holiday):
                return (delta_kwh, 0.0)
            else:
                return (0.0, delta_kwh)
        
        # Calculate seconds spent in peak vs off-peak
        peak_seconds = 0.0
        current = start_ts
        
        # Walk through the interval, finding boundary crossings
        while current < end_ts:
            # Find next boundary (2PM or 10PM on same day, or midnight)
            current_date = current.date()
            peak_start_dt = datetime.combine(current_date, PEAK_START)
            peak_end_dt = datetime.combine(current_date, PEAK_END)
            midnight_dt = datetime.combine(current_date + timedelta(days=1), time(0, 0))
            
            # Make datetimes timezone-aware if current is aware
            if current.tzinfo is not None:
                peak_start_dt = peak_start_dt.replace(tzinfo=current.tzinfo)
                peak_end_dt = peak_end_dt.replace(tzinfo=current.tzinfo)
                midnight_dt = midnight_dt.replace(tzinfo=current.tzinfo)
            
            # Determine if current moment is in peak
            in_peak = self._is_peak_period(current, is_holiday)
            
            # Find the next boundary we might cross
            if in_peak:
                # Currently in peak, next boundary is peak_end or end_ts
                next_boundary = min(peak_end_dt, end_ts)
            else:
                # Currently off-peak
                if current.time() < PEAK_START:
                    # Before peak window, next boundary is peak_start or end_ts
                    next_boundary = min(peak_start_dt, end_ts)
                else:
                    # After peak window (>= 10PM), next boundary is midnight or end_ts
                    next_boundary = min(midnight_dt, end_ts)
            
            # Ensure we don't go backwards
            if next_boundary <= current:
                next_boundary = end_ts
            
            # Calculate time in this segment
            segment_seconds = (next_boundary - current).total_seconds()
            if in_peak:
                peak_seconds += segment_seconds
            
            current = next_boundary
            
            # Safety: if we somehow get stuck, break
            if segment_seconds <= 0 and current < end_ts:
                break
        
        # Calculate proportions
        offpeak_seconds = total_seconds - peak_seconds
        
        if total_seconds > 0:
            peak_kwh = delta_kwh * (peak_seconds / total_seconds)
            offpeak_kwh = delta_kwh * (offpeak_seconds / total_seconds)
        else:
            # Fallback
            if self._is_peak_period(end_ts, is_holiday):
                peak_kwh, offpeak_kwh = delta_kwh, 0.0
            else:
                peak_kwh, offpeak_kwh = 0.0, delta_kwh
        
        return (peak_kwh, offpeak_kwh)

    def _lookup_ict_rate_tou(self, import_kwh: float) -> float:
        """Lookup ICT rate for ToU calculation - uses >= logic.
        
        Uses stored ICT tiers if available, otherwise hardcoded defaults.
        """
        # Try stored tiers first
        stored_rate = self._get_ict_rate_from_stored(import_kwh, use_tou_logic=True)
        if stored_rate is not None:
            return stored_rate
        
        # Fallback to hardcoded tiers
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
        """Lookup ICT rate for non-ToU calculation - uses <= logic.
        
        Uses stored ICT tiers if available, otherwise hardcoded defaults.
        """
        # Try stored tiers first
        stored_rate = self._get_ict_rate_from_stored(import_kwh, use_tou_logic=False)
        if stored_rate is not None:
            return stored_rate
        
        # Fallback to hardcoded tiers
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

    def _round_rate(self, value: Optional[float]) -> Optional[float]:
        """Round rate (MYR/kWh) to 3 decimal places."""
        if value is None:
            return None
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
        """Calculate ToU-based costs following the template exactly.
        
        Uses stored tariffs from API if available, otherwise hardcoded defaults.
        """
        # Derived quantities (Excel: E2,E6,E7)
        import_total = import_peak + import_offpeak
        export_peak = min(import_peak, export_total)
        export_offpeak = export_total - export_peak
        
        # Effective import energy rates (from stored tariffs or hardcoded)
        gen_peak_eff, gen_off_eff = self._get_tou_generation_rates(import_total)
        
        # Fixed rates (from stored tariffs or hardcoded)
        cap_rate = self._get_capacity_rate()
        netw_rate = self._get_network_rate()
        
        # AFA & Retailing (using tariff overrides or defaults)
        afa_rate = self._get_tariff_rate("afa_rate", DEFAULT_AFA_RATE)
        afa_threshold = DEFAULT_AFA_THRESHOLD  # Future: can also be overridable
        retailing_charge = self._get_retailing_charge()
        
        afa = 0.0 if import_total < afa_threshold else import_total * afa_rate
        retailing = retailing_charge if import_total > afa_threshold else 0.0
        
        # ICT lookup (uses stored tiers or hardcoded)
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
        
        # NEM rebate lines use tier1 base energy rates (always lowest tier for export credits)
        nem_peak_rate, nem_off_rate = self._get_tou_generation_rates(0)  # tier1 rates
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
            "rate_afa": afa_rate,
            "tariff_source": self._tariff_overrides.get("source", TARIFF_SOURCE_DEFAULT),
            "tariff_last_updated": self._tariff_overrides.get("last_updated"),
        }

    def _calculate_non_tou_costs(
        self, import_kwh: float, export_kwh: float
    ) -> Dict[str, Any]:
        """Calculate non-ToU-based costs following the template exactly.
        
        Uses stored tariffs from API if available, otherwise hardcoded defaults.
        """
        # Get rates from stored tariffs or hardcoded defaults
        gen_rate = self._get_non_tou_generation_rate()
        cap_rate = self._get_capacity_rate()
        netw_rate = self._get_network_rate()
        retailing_charge = self._get_retailing_charge()
        
        # ICT Rate calculation (uses stored tiers or hardcoded)
        ict_rate = self._lookup_ict_rate_non_tou(import_kwh)
        
        # Import calculation - First tier (up to 600 kWh)
        import_tier1 = min(import_kwh, 600)
        import_caj_tier1 = import_tier1 * gen_rate
        import_capacity_tier1 = import_tier1 * cap_rate
        import_network_tier1 = import_tier1 * netw_rate
        import_runcit_tier1 = 0
        import_ict_tier1 = import_tier1 * ict_rate
        import_kwtbb_tier1 = (import_caj_tier1 + import_capacity_tier1 + import_network_tier1 + import_ict_tier1) * 0.016
        
        # Import calculation - Second tier (excess over 600 kWh)
        import_tier2 = max(import_kwh - 600, 0)
        import_caj_tier2 = import_tier2 * gen_rate
        import_capacity_tier2 = import_tier2 * cap_rate
        import_network_tier2 = import_tier2 * netw_rate
        import_runcit_tier2 = retailing_charge if import_tier2 > 0 else 0
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
        export_caj = export_kwh * -gen_rate
        export_capacity = export_kwh * -cap_rate
        export_network = export_kwh * -netw_rate
        export_ict = export_kwh * -ict_rate
        
        total_export = export_caj + export_capacity + export_network + export_ict
        
        # Final subtotal
        subtotal = total_import + total_export
        
        return {
            "total_cost": self._round_currency(subtotal),
            "peak_cost": self._round_currency(0.0),
            "off_peak_cost": self._round_currency(total_import_caj),
            "rate_import": gen_rate,
            "rate_capacity": cap_rate,
            "rate_network": netw_rate,
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

    # =========================================================================
    # OPTIMIZATION SENSORS - AFA Sweet Spot Analysis
    # =========================================================================

    def _simulate_bill_for_import(
        self,
        target_import_kwh: float,
        export_kwh: float,
        current_import_kwh: Optional[float] = None,
        return_both: bool = False,
    ) -> Union[float, Dict[str, float]]:
        """Simulate bill for a hypothetical import kWh.
        
        Uses the same calculation logic as the main update cycle,
        but with a specified import value instead of actual.
        
        For ToU mode: distributes delta (target - current) proportionally 
        to current peak/offpeak ratio, then adds to current peak/offpeak.
        For non-ToU mode: uses target_import_kwh directly.
        
        Args:
            target_import_kwh: Hypothetical total import kWh
            export_kwh: Export kWh (fixed, from actual data)
            current_import_kwh: Current import for delta-based distribution (optional)
            return_both: If True, returns dict with both tou and non_tou costs
            
        Returns:
            Total bill in MYR (float) or dict with tou/non_tou costs if return_both=True
        """
        # Get current peak/offpeak for proportional distribution
        current_peak = self._monthly_data.get("import_peak", 0)
        current_offpeak = self._monthly_data.get("import_offpeak", 0)
        current_total = current_peak + current_offpeak
        
        # Calculate peak ratio for distribution
        if current_total > 0:
            peak_ratio = current_peak / current_total
        else:
            peak_ratio = 0.5  # Default assumption: 50% peak when no data
        
        # For ToU simulation: distribute delta proportionally
        if current_import_kwh is not None and current_total > 0:
            # Delta-based distribution: add delta proportionally to current values
            delta = target_import_kwh - current_import_kwh
            sim_peak = current_peak + (delta * peak_ratio)
            sim_offpeak = current_offpeak + (delta * (1 - peak_ratio))
        else:
            # Absolute distribution when no current reference
            sim_peak = target_import_kwh * peak_ratio
            sim_offpeak = target_import_kwh * (1 - peak_ratio)
        
        # Ensure non-negative values
        sim_peak = max(0.0, sim_peak)
        sim_offpeak = max(0.0, sim_offpeak)
        
        # Calculate costs
        tou_result = self._calculate_tou_costs(sim_peak, sim_offpeak, export_kwh)
        non_tou_result = self._calculate_non_tou_costs(target_import_kwh, export_kwh)
        
        if return_both:
            return {
                "tou": tou_result["total_cost"],
                "non_tou": non_tou_result["total_cost"],
            }
        
        # Return primary cost based on ToU mode
        if self._tou_enabled:
            return tou_result["total_cost"]
        else:
            return non_tou_result["total_cost"]

    def _generate_afa_explanation(
        self,
        zone: str,
        current_import: float,
        cost_now: float,
        cost_600: float,
        kwh_to_600: float,
        afa_savings: float,
        avg_marginal_rate: Optional[float],
    ) -> str:
        """Generate human-readable explanation of AFA optimization situation.
        
        Args:
            zone: "weird", "value", "normal", or "above_threshold"
            current_import: Current month import kWh
            cost_now: Bill at current import
            cost_600: Bill at 600 kWh
            kwh_to_600: 600 - current_import
            afa_savings: cost_now - cost_600 (positive = weird zone)
            avg_marginal_rate: Cost per extra kWh to 600 (if < 600)
            
        Returns:
            Explanation string
        """
        if zone == "above_threshold":
            afa_rate = self._get_tariff_rate("afa_rate", DEFAULT_AFA_RATE)
            afa_amount = current_import * afa_rate
            return (
                f"Already above 600 kWh ({current_import:.0f} kWh). "
                f"AFA rebate of RM {afa_amount:.2f} is active."
            )
        
        if zone == "weird":
            return (
                f"AFA weird zone: {current_import:.0f} kWh = RM {cost_now:.2f}. "
                f"If 600 kWh: RM {cost_600:.2f}. "
                f"Extra {kwh_to_600:.0f} kWh could SAVE RM {afa_savings:.2f} due to AFA rebate."
            )
        
        if zone == "value":
            extra_cost = cost_600 - cost_now
            rate_str = f"RM {avg_marginal_rate:.2f}/kWh" if avg_marginal_rate else "N/A"
            return (
                f"Value opportunity: {current_import:.0f} kWh = RM {cost_now:.2f}. "
                f"If 600 kWh: RM {cost_600:.2f}. "
                f"Extra {kwh_to_600:.0f} kWh costs only RM {extra_cost:.2f} ({rate_str} - below normal rates)."
            )
        
        # Normal zone
        savings = cost_600 - cost_now  # Positive means 600 costs more
        if avg_marginal_rate is not None and kwh_to_600 > 0:
            return (
                f"Normal zone: {current_import:.0f} kWh = RM {cost_now:.2f}. "
                f"If 600 kWh: RM {cost_600:.2f} (RM {avg_marginal_rate:.2f}/kWh extra). "
                f"Staying below 600 kWh saves RM {savings:.2f}."
            )
        return (
            f"Current: {current_import:.0f} kWh = RM {cost_now:.2f}. "
            f"If 600 kWh: RM {cost_600:.2f}."
        )

    def _generate_afa_explanation_v2(
        self,
        zone: str,
        label: str,
        current_import: float,
        best_target: int,
        cost_now: float,
        cost_target: float,
        marginal_rate: float,
        avg_rate_now: Optional[float],
    ) -> str:
        """Generate human-readable explanation using rate-based messaging.
        
        Focuses on marginal rate and average rate to explain recommendations.
        
        Args:
            zone: "weird", "value", "normal", "stay_put", or "above_threshold"
            label: "saves_money", "super_value", "value", "normal", "expensive", "stay_put"
            current_import: Current month import kWh
            best_target: Recommended target kWh
            cost_now: Bill at current import
            cost_target: Bill at best target
            marginal_rate: Cost per extra kWh to target
            avg_rate_now: Current average cost per kWh
            
        Returns:
            Explanation string
        """
        delta_kwh = best_target - current_import
        delta_cost = cost_target - cost_now
        avg_rate_str = f"RM {avg_rate_now:.2f}/kWh" if avg_rate_now else "N/A"
        
        if label == "saves_money":
            # Negative marginal rate - using more saves money
            savings = -delta_cost
            return (
                f"Weird zone: Using more saves money! "
                f"Current: {current_import:.0f} kWh (RM {cost_now:.2f}). "
                f"Target: {best_target} kWh (RM {cost_target:.2f}). "
                f"Add {delta_kwh:.0f} kWh to save RM {savings:.2f}."
            )
        
        if label == "super_value":
            return (
                f"Super value! Extra kWh to {best_target} kWh costs only "
                f"RM {marginal_rate:.2f}/kWh (vs {avg_rate_str} average). "
                f"Current: {current_import:.0f} kWh (RM {cost_now:.2f}). "
                f"Add {delta_kwh:.0f} kWh for RM {delta_cost:.2f} extra."
            )
        
        if label == "value":
            return (
                f"Value opportunity: Extra kWh to {best_target} kWh costs "
                f"RM {marginal_rate:.2f}/kWh (below {avg_rate_str} average). "
                f"Current: {current_import:.0f} kWh (RM {cost_now:.2f}). "
                f"Add {delta_kwh:.0f} kWh for RM {delta_cost:.2f} extra."
            )
        
        if label == "stay_put":
            return (
                f"Stay put: No value in adding kWh. "
                f"Current: {current_import:.0f} kWh (RM {cost_now:.2f}, {avg_rate_str}). "
                f"Extra kWh would cost more than your average rate."
            )
        
        if label == "expensive":
            return (
                f"Extra kWh would cost more than average. "
                f"Current: {current_import:.0f} kWh (RM {cost_now:.2f}, {avg_rate_str}). "
                f"No recommendation to increase usage."
            )
        
        # Normal (low usage, not near threshold)
        return (
            f"Current: {current_import:.0f} kWh (RM {cost_now:.2f}, {avg_rate_str}). "
            f"No immediate action recommended."
        )

    def _calculate_optimization_data(self) -> Dict[str, Any]:
        """Calculate all optimization sensor data in one pass.
        
        Uses MARGINAL RATE approach to find the best target import in 550-600 kWh range.
        Computes SEPARATE recommendations for ToU and non-ToU models.
        
        Key principles:
        - Target is always >= current_import (practical, actionable)
        - Search range: 550-600 kWh in 5 kWh steps
        - Primary metric: marginal rate = (cost_target - cost_now) / (target - current)
        - Labels based on marginal rate vs average rate
        - Option B gating: only recommend if label is favorable (saves_money/super_value/value)
        - Z2-B: stay_put zone when current >= 550 and not worth moving up
        - Both ToU and non-ToU computed independently
        
        Returns:
            Dict with keys for all optimization sensors and rich attributes
        """
        FAVORABLE_LABELS = {"saves_money", "super_value", "value"}
        STAY_PUT_THRESHOLD = 550  # Z2-B: only use stay_put zone when >= this
        
        # Get current month data
        current_import = self._monthly_data.get("import_total", 0.0)
        export_total = self._monthly_data.get("export_total", 0.0)
        
        # Get costs at current import (both models)
        costs_now = self._simulate_bill_for_import(
            current_import, export_total, current_import, return_both=True
        )
        cost_now_tou = costs_now["tou"]
        cost_now_non_tou = costs_now["non_tou"]
        
        # Primary cost based on mode
        cost_now_primary = cost_now_tou if self._tou_enabled else cost_now_non_tou
        
        # Average rate now (cost / kWh)
        if current_import > 0:
            avg_rate_now_tou = cost_now_tou / current_import
            avg_rate_now_non_tou = cost_now_non_tou / current_import
        else:
            avg_rate_now_tou = None
            avg_rate_now_non_tou = None
        
        # Cost at exactly 600 kWh (AFA threshold) for reference
        costs_600 = self._simulate_bill_for_import(
            600.0, export_total, current_import, return_both=True
        )
        cost_600_tou = costs_600["tou"]
        cost_600_non_tou = costs_600["non_tou"]
        cost_600_primary = cost_600_tou if self._tou_enabled else cost_600_non_tou
        
        # =========================================================================
        # MARGINAL RATE OPTIMIZATION: Find best target in 550-600 range
        # =========================================================================
        
        # Edge case: already above 600 kWh
        if current_import >= 600:
            return self._build_above_threshold_result(
                current_import, export_total, 
                cost_now_tou, cost_now_non_tou,
                cost_600_tou, cost_600_non_tou,
                avg_rate_now_tou, avg_rate_now_non_tou
            )
        
        # Generate candidate targets: 550 to 600 in 5 kWh steps, filtered to >= current
        candidates = [t for t in range(550, 605, 5) if t >= current_import]
        
        # If no candidates (current_import > 600 handled above, but edge case)
        if not candidates:
            candidates = [600]  # Fallback to 600
        
        # Evaluate each candidate for BOTH models
        best_target_tou = None
        best_marginal_tou = float('inf')
        best_label_tou = None
        best_target_non_tou = None
        best_marginal_non_tou = float('inf')
        best_label_non_tou = None
        
        evaluated_targets = []
        
        for target in candidates:
            delta_kwh = target - current_import
            
            # Skip if delta is 0 (current == target)
            if delta_kwh <= 0:
                continue
            
            # Simulate cost at this target
            costs_target = self._simulate_bill_for_import(
                float(target), export_total, current_import, return_both=True
            )
            
            # Marginal rate = (cost_target - cost_now) / delta_kwh
            marginal_tou = (costs_target["tou"] - cost_now_tou) / delta_kwh
            marginal_non_tou = (costs_target["non_tou"] - cost_now_non_tou) / delta_kwh
            
            # Classify labels for this candidate
            label_tou_candidate = self._classify_marginal_label(marginal_tou, avg_rate_now_tou)
            label_non_tou_candidate = self._classify_marginal_label(marginal_non_tou, avg_rate_now_non_tou)
            
            evaluated_targets.append({
                "target_kwh": target,
                "delta_kwh": delta_kwh,
                "cost_tou_myr": self._round_currency(costs_target["tou"]),
                "cost_non_tou_myr": self._round_currency(costs_target["non_tou"]),
                "marginal_tou_myr_per_kwh": self._round_rate(marginal_tou),
                "marginal_non_tou_myr_per_kwh": self._round_rate(marginal_non_tou),
                "label_tou": label_tou_candidate,
                "label_non_tou": label_non_tou_candidate,
            })
            
            # Track best (lowest marginal rate) for each model
            if marginal_tou < best_marginal_tou:
                best_marginal_tou = marginal_tou
                best_target_tou = target
                best_label_tou = label_tou_candidate
            if marginal_non_tou < best_marginal_non_tou:
                best_marginal_non_tou = marginal_non_tou
                best_target_non_tou = target
                best_label_non_tou = label_non_tou_candidate
        
        # =========================================================================
        # OPTION B GATING: Apply per-model stay_put logic
        # Only recommend if label is favorable, otherwise stay at current
        # =========================================================================
        
        # ToU model gating
        if best_label_tou is None or best_label_tou not in FAVORABLE_LABELS:
            # Not favorable - recommend staying at current
            final_target_tou = int(current_import)
            final_marginal_tou = 0.0
            # Z2-B: only use stay_put zone when >= threshold, else normal
            if current_import >= STAY_PUT_THRESHOLD:
                final_label_tou = "stay_put"
                zone_tou = "stay_put"
            else:
                final_label_tou = best_label_tou if best_label_tou else "normal"
                zone_tou = "normal"
        else:
            # Favorable - recommend moving to target
            final_target_tou = best_target_tou
            final_marginal_tou = best_marginal_tou
            final_label_tou = best_label_tou
            # Zone based on label
            if final_label_tou == "saves_money":
                zone_tou = "weird"
            elif final_label_tou in ["super_value", "value"]:
                zone_tou = "value"
            else:
                zone_tou = "normal"
        
        # Non-ToU model gating
        if best_label_non_tou is None or best_label_non_tou not in FAVORABLE_LABELS:
            # Not favorable - recommend staying at current
            final_target_non_tou = int(current_import)
            final_marginal_non_tou = 0.0
            # Z2-B: only use stay_put zone when >= threshold, else normal
            if current_import >= STAY_PUT_THRESHOLD:
                final_label_non_tou = "stay_put"
                zone_non_tou = "stay_put"
            else:
                final_label_non_tou = best_label_non_tou if best_label_non_tou else "normal"
                zone_non_tou = "normal"
        else:
            # Favorable - recommend moving to target
            final_target_non_tou = best_target_non_tou
            final_marginal_non_tou = best_marginal_non_tou
            final_label_non_tou = best_label_non_tou
            # Zone based on label
            if final_label_non_tou == "saves_money":
                zone_non_tou = "weird"
            elif final_label_non_tou in ["super_value", "value"]:
                zone_non_tou = "value"
            else:
                zone_non_tou = "normal"
        
        # Primary values based on mode
        final_target = final_target_tou if self._tou_enabled else final_target_non_tou
        final_marginal = final_marginal_tou if self._tou_enabled else final_marginal_non_tou
        primary_label = final_label_tou if self._tou_enabled else final_label_non_tou
        zone = zone_tou if self._tou_enabled else zone_non_tou
        
        # Get costs at final targets (for each model)
        costs_final_tou = self._simulate_bill_for_import(
            float(final_target_tou), export_total, current_import, return_both=True
        )
        costs_final_non_tou = self._simulate_bill_for_import(
            float(final_target_non_tou), export_total, current_import, return_both=True
        )
        
        # Average rate at final targets
        avg_rate_target_tou = costs_final_tou["tou"] / final_target_tou if final_target_tou > 0 else None
        avg_rate_target_non_tou = costs_final_non_tou["non_tou"] / final_target_non_tou if final_target_non_tou > 0 else None
        
        # Zone classification for backward compatibility
        weird_zone = zone == "weird"
        value_zone = zone == "value"
        
        # Delta calculations (per model)
        delta_to_target_tou = final_target_tou - current_import
        delta_to_target_non_tou = final_target_non_tou - current_import
        delta_cost_to_target_tou = costs_final_tou["tou"] - cost_now_tou
        delta_cost_to_target_non_tou = costs_final_non_tou["non_tou"] - cost_now_non_tou
        
        # Primary deltas
        delta_to_target = final_target - current_import
        delta_cost_primary = delta_cost_to_target_tou if self._tou_enabled else delta_cost_to_target_non_tou
        
        # Savings if at ideal (vs current cost)
        savings_if_ideal = -delta_cost_primary if delta_cost_primary < 0 else 0.0
        
        # AFA optimization savings (vs 600 kWh reference)
        afa_savings = cost_now_primary - cost_600_primary
        
        # Marginal rate to 600 (for backward compatibility)
        kwh_to_600 = 600.0 - current_import
        if kwh_to_600 > 0:
            marginal_to_600_tou = (cost_600_tou - cost_now_tou) / kwh_to_600
            marginal_to_600_non_tou = (cost_600_non_tou - cost_now_non_tou) / kwh_to_600
        else:
            marginal_to_600_tou = None
            marginal_to_600_non_tou = None
        
        avg_marginal_rate = marginal_to_600_tou if self._tou_enabled else marginal_to_600_non_tou
        
        # Generate explanation with new rate-based messaging
        explanation = self._generate_afa_explanation_v2(
            zone=zone,
            label=primary_label,
            current_import=current_import,
            best_target=final_target,
            cost_now=cost_now_primary,
            cost_target=costs_final_tou["tou"] if self._tou_enabled else costs_final_non_tou["non_tou"],
            marginal_rate=final_marginal,
            avg_rate_now=avg_rate_now_tou if self._tou_enabled else avg_rate_now_non_tou,
        )
        
        # Debug logging for validation
        _LOGGER.debug(
            "AFA Optimization: import=%.1f kWh, tou_target=%d (%s), non_tou_target=%d (%s), "
            "primary=%s, zone=%s",
            current_import, final_target_tou, final_label_tou,
            final_target_non_tou, final_label_non_tou,
            "tou" if self._tou_enabled else "non_tou", zone
        )
        
        return {
            # Main sensor values (backward compatible)
            "ideal_import_kwh": self._round_energy(float(final_target)),
            "ideal_import_kwh_tou": self._round_energy(float(final_target_tou)),
            "ideal_import_kwh_non_tou": self._round_energy(float(final_target_non_tou)),
            "savings_if_ideal_kwh": self._round_currency(max(savings_if_ideal, 0)),
            "afa_optimization_savings": self._round_currency(afa_savings),
            "afa_weird_zone": weird_zone,
            "afa_value_zone": value_zone,
            "afa_explanation": explanation,
            
            # Zone and labels
            "optimization_zone": zone,
            "primary_label": primary_label,
            "primary_model": "tou" if self._tou_enabled else "non_tou",
            
            # Current state
            "current_import_kwh": self._round_energy(current_import),
            "export_total_kwh": self._round_energy(export_total),
            
            # ToU metrics (normalized keys with unit suffixes)
            "tou": {
                "cost_now_myr": self._round_currency(cost_now_tou),
                "cost_target_myr": self._round_currency(costs_final_tou["tou"]),
                "cost_600_myr": self._round_currency(cost_600_tou),
                "recommended_target_kwh": final_target_tou,
                "delta_kwh": self._round_energy(delta_to_target_tou),
                "delta_cost_myr": self._round_currency(delta_cost_to_target_tou),
                "marginal_rate_myr_per_kwh": self._round_rate(final_marginal_tou),
                "marginal_rate_to_600_myr_per_kwh": self._round_rate(marginal_to_600_tou),
                "avg_rate_now_myr_per_kwh": self._round_rate(avg_rate_now_tou),
                "avg_rate_target_myr_per_kwh": self._round_rate(avg_rate_target_tou),
                "label": final_label_tou,
                "zone": zone_tou,
                # Backward compatibility aliases
                "best_target_kwh": final_target_tou,
                "delta_kwh_to_target": self._round_energy(delta_to_target_tou),
                "delta_cost_to_target_myr": self._round_currency(delta_cost_to_target_tou),
                "marginal_rate_to_target": self._round_rate(final_marginal_tou),
                "marginal_rate_to_600": self._round_rate(marginal_to_600_tou),
                "avg_rate_now": self._round_rate(avg_rate_now_tou),
                "avg_rate_target": self._round_rate(avg_rate_target_tou),
            },
            
            # Non-ToU metrics (normalized keys with unit suffixes)
            "non_tou": {
                "cost_now_myr": self._round_currency(cost_now_non_tou),
                "cost_target_myr": self._round_currency(costs_final_non_tou["non_tou"]),
                "cost_600_myr": self._round_currency(cost_600_non_tou),
                "recommended_target_kwh": final_target_non_tou,
                "delta_kwh": self._round_energy(delta_to_target_non_tou),
                "delta_cost_myr": self._round_currency(delta_cost_to_target_non_tou),
                "marginal_rate_myr_per_kwh": self._round_rate(final_marginal_non_tou),
                "marginal_rate_to_600_myr_per_kwh": self._round_rate(marginal_to_600_non_tou),
                "avg_rate_now_myr_per_kwh": self._round_rate(avg_rate_now_non_tou),
                "avg_rate_target_myr_per_kwh": self._round_rate(avg_rate_target_non_tou),
                "label": final_label_non_tou,
                "zone": zone_non_tou,
                # Backward compatibility aliases
                "best_target_kwh": final_target_non_tou,
                "delta_kwh_to_target": self._round_energy(delta_to_target_non_tou),
                "delta_cost_to_target_myr": self._round_currency(delta_cost_to_target_non_tou),
                "marginal_rate_to_target": self._round_rate(final_marginal_non_tou),
                "marginal_rate_to_600": self._round_rate(marginal_to_600_non_tou),
                "avg_rate_now": self._round_rate(avg_rate_now_non_tou),
                "avg_rate_target": self._round_rate(avg_rate_target_non_tou),
            },
            
            # Backward compatibility attributes
            "cost_now_myr": self._round_currency(cost_now_primary),
            "cost_at_600_myr": self._round_currency(cost_600_primary),
            "ideal_cost_myr": self._round_currency(costs_final_tou["tou"] if self._tou_enabled else costs_final_non_tou["non_tou"]),
            "kwh_to_600": self._round_energy(kwh_to_600),
            "delta_to_ideal_kwh": self._round_energy(delta_to_target),
            "avg_marginal_rate": self._round_rate(avg_marginal_rate),
            "afa_rate": self._get_tariff_rate("afa_rate", DEFAULT_AFA_RATE),
            
            # Debug info
            "evaluated_targets": evaluated_targets,
        }
    
    def _classify_marginal_label(
        self, 
        marginal_rate: float, 
        avg_rate_now: Optional[float]
    ) -> str:
        """Classify marginal rate into a human-readable label.
        
        Labels based on marginal rate relative to average rate:
        - saves_money: marginal < 0 (using more reduces bill)
        - super_value: marginal <= 0.25 * avg_rate
        - value: marginal <= 0.60 * avg_rate
        - normal: marginal <= 1.00 * avg_rate
        - expensive: marginal > avg_rate
        
        When avg_rate <= 0 (negative bills, early month), use absolute thresholds.
        
        Args:
            marginal_rate: Cost per extra kWh to target
            avg_rate_now: Current average cost per kWh
            
        Returns:
            Label string
        """
        # Saves money: marginal rate is negative
        if marginal_rate < 0:
            return "saves_money"
        
        # Handle edge cases where avg_rate is None, zero, or negative
        if avg_rate_now is None or avg_rate_now <= 0:
            # Use absolute thresholds
            if marginal_rate <= 0.05:  # Very cheap
                return "value"
            else:
                return "normal"
        
        # Relative thresholds based on average rate
        if marginal_rate <= 0.25 * avg_rate_now:
            return "super_value"
        elif marginal_rate <= 0.60 * avg_rate_now:
            return "value"
        elif marginal_rate <= 1.00 * avg_rate_now:
            return "normal"
        else:
            return "expensive"
    
    def _build_above_threshold_result(
        self,
        current_import: float,
        export_total: float,
        cost_now_tou: float,
        cost_now_non_tou: float,
        cost_600_tou: float,
        cost_600_non_tou: float,
        avg_rate_now_tou: Optional[float],
        avg_rate_now_non_tou: Optional[float],
    ) -> Dict[str, Any]:
        """Build result dict for above_threshold case (current >= 600 kWh).
        
        When already above 600 kWh, there's no target to recommend.
        Just report current state.
        """
        cost_now_primary = cost_now_tou if self._tou_enabled else cost_now_non_tou
        avg_rate_primary = avg_rate_now_tou if self._tou_enabled else avg_rate_now_non_tou
        
        afa_rate = self._get_tariff_rate("afa_rate", DEFAULT_AFA_RATE)
        afa_amount = current_import * afa_rate
        
        explanation = (
            f"Already above 600 kWh ({current_import:.0f} kWh). "
            f"AFA rebate of RM {afa_amount:.2f} is active. "
            f"Average rate: RM {avg_rate_primary:.2f}/kWh."
        )
        
        return {
            # Main sensor values
            "ideal_import_kwh": self._round_energy(current_import),
            "savings_if_ideal_kwh": 0.0,
            "afa_optimization_savings": 0.0,
            "afa_weird_zone": False,
            "afa_value_zone": False,
            "afa_explanation": explanation,
            
            # Zone and labels
            "optimization_zone": "above_threshold",
            "primary_label": "above_threshold",
            "primary_model": "tou" if self._tou_enabled else "non_tou",
            
            # Current state
            "current_import_kwh": self._round_energy(current_import),
            "export_total_kwh": self._round_energy(export_total),
            
            # ToU metrics
            "tou": {
                "cost_now_myr": self._round_currency(cost_now_tou),
                "cost_target_myr": self._round_currency(cost_now_tou),
                "cost_600_myr": self._round_currency(cost_600_tou),
                "best_target_kwh": int(current_import),
                "delta_kwh_to_target": 0,
                "delta_cost_to_target_myr": 0.0,
                "marginal_rate_to_target": None,
                "marginal_rate_to_600": None,
                "avg_rate_now": self._round_currency(avg_rate_now_tou) if avg_rate_now_tou else None,
                "avg_rate_target": self._round_currency(avg_rate_now_tou) if avg_rate_now_tou else None,
                "label": "above_threshold",
            },
            
            # Non-ToU metrics
            "non_tou": {
                "cost_now_myr": self._round_currency(cost_now_non_tou),
                "cost_target_myr": self._round_currency(cost_now_non_tou),
                "cost_600_myr": self._round_currency(cost_600_non_tou),
                "best_target_kwh": int(current_import),
                "delta_kwh_to_target": 0,
                "delta_cost_to_target_myr": 0.0,
                "marginal_rate_to_target": None,
                "marginal_rate_to_600": None,
                "avg_rate_now": self._round_currency(avg_rate_now_non_tou) if avg_rate_now_non_tou else None,
                "avg_rate_target": self._round_currency(avg_rate_now_non_tou) if avg_rate_now_non_tou else None,
                "label": "above_threshold",
            },
            
            # Backward compatibility attributes
            "cost_now_myr": self._round_currency(cost_now_primary),
            "cost_at_600_myr": self._round_currency(cost_600_tou if self._tou_enabled else cost_600_non_tou),
            "ideal_cost_myr": self._round_currency(cost_now_primary),
            "kwh_to_600": 0.0,
            "delta_to_ideal_kwh": 0.0,
            "avg_marginal_rate": None,
            "afa_rate": afa_rate,
            
            # Debug info
            "evaluated_targets": [],
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
            "sw_version": "4.4.4",
        }

    @property
    def native_unit_of_measurement(self) -> Optional[str]:
        """Return the unit of measurement."""
        return self._attr_unit_of_measurement

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
        
        attrs: Dict[str, Any] = {}
        
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
        
        # Add holiday cache info only to diagnostic sensors
        if self._sensor_type in ["cached_holidays_count", "storage_health"]:
            attrs["cached_holidays"] = self.coordinator.data.get("cached_holidays")
            attrs["cached_holidays_last_fetch"] = self.coordinator.data.get("cached_holidays_last_fetch")
        
        # Add common attributes only to main sensors (costs and energy)
        if self._sensor_type in ["total_cost_tou", "total_cost_non_tou", "import_energy", "export_energy", "net_energy"]:
            attrs["last_update"] = self.coordinator.data.get("last_update")
            attrs["current_month"] = self.coordinator.data.get("current_month")
            attrs["billing_start_day"] = self.coordinator.data.get("billing_start_day_active")
            attrs["billing_start_day_configured"] = self.coordinator.data.get("billing_start_day_configured")
            pending_day = self.coordinator.data.get("billing_start_day_pending")
            if pending_day is not None:
                attrs["billing_start_day_pending"] = pending_day
                attrs["billing_start_day_note"] = (
                    f"New billing start day {pending_day} will activate next billing cycle"
                )
        
        # Add ToU energy breakdown to relevant sensors
        if self._sensor_type in ["import_energy", "total_cost_tou"]:
            for key in ["import_peak_energy", "import_offpeak_energy"]:
                value = self.coordinator.data.get(key)
                if value is not None:
                    attrs[key] = value
        
        if self._sensor_type in ["export_energy", "total_cost_tou"]:
            value = self.coordinator.data.get("export_total_energy")
            if value is not None:
                attrs["export_total_energy"] = value
        
        # Add optimization sensor attributes
        optimization_data = self.coordinator.data.get("_optimization_data", {})
        
        # Get ToU and non-ToU metrics from optimization data
        tou_metrics = optimization_data.get("tou", {})
        non_tou_metrics = optimization_data.get("non_tou", {})
        primary_model = optimization_data.get("primary_model", "non_tou")
        
        if self._sensor_type == "ideal_import_kwh":
            primary_metrics = tou_metrics if primary_model == "tou" else non_tou_metrics
            attrs.update({
                "current_month_import_kwh": optimization_data.get("current_import_kwh"),
                "delta_to_target_kwh": optimization_data.get("delta_to_ideal_kwh"),
                "estimated_bill_at_current_myr": optimization_data.get("cost_now_myr"),
                "estimated_bill_at_target_myr": optimization_data.get("ideal_cost_myr"),
                "primary_model": primary_model,
                "primary_label": optimization_data.get("primary_label"),
                "zone": optimization_data.get("optimization_zone"),
                # Rate metrics (normalized keys)
                "avg_rate_now_myr_per_kwh": primary_metrics.get("avg_rate_now_myr_per_kwh"),
                "avg_rate_target_myr_per_kwh": primary_metrics.get("avg_rate_target_myr_per_kwh"),
                "marginal_rate_myr_per_kwh": primary_metrics.get("marginal_rate_myr_per_kwh"),
                # Both models for comparison
                "tou": tou_metrics,
                "non_tou": non_tou_metrics,
            })
        
        if self._sensor_type == "ideal_import_kwh_tou":
            attrs.update({
                "current_month_import_kwh": optimization_data.get("current_import_kwh"),
                "delta_kwh": tou_metrics.get("delta_kwh"),
                "cost_now_myr": tou_metrics.get("cost_now_myr"),
                "cost_target_myr": tou_metrics.get("cost_target_myr"),
                "delta_cost_myr": tou_metrics.get("delta_cost_myr"),
                "label": tou_metrics.get("label"),
                "zone": tou_metrics.get("zone"),
                # Rate metrics
                "avg_rate_now_myr_per_kwh": tou_metrics.get("avg_rate_now_myr_per_kwh"),
                "avg_rate_target_myr_per_kwh": tou_metrics.get("avg_rate_target_myr_per_kwh"),
                "marginal_rate_myr_per_kwh": tou_metrics.get("marginal_rate_myr_per_kwh"),
                "marginal_rate_to_600_myr_per_kwh": tou_metrics.get("marginal_rate_to_600_myr_per_kwh"),
            })
        
        if self._sensor_type == "ideal_import_kwh_non_tou":
            attrs.update({
                "current_month_import_kwh": optimization_data.get("current_import_kwh"),
                "delta_kwh": non_tou_metrics.get("delta_kwh"),
                "cost_now_myr": non_tou_metrics.get("cost_now_myr"),
                "cost_target_myr": non_tou_metrics.get("cost_target_myr"),
                "delta_cost_myr": non_tou_metrics.get("delta_cost_myr"),
                "label": non_tou_metrics.get("label"),
                "zone": non_tou_metrics.get("zone"),
                # Rate metrics
                "avg_rate_now_myr_per_kwh": non_tou_metrics.get("avg_rate_now_myr_per_kwh"),
                "avg_rate_target_myr_per_kwh": non_tou_metrics.get("avg_rate_target_myr_per_kwh"),
                "marginal_rate_myr_per_kwh": non_tou_metrics.get("marginal_rate_myr_per_kwh"),
                "marginal_rate_to_600_myr_per_kwh": non_tou_metrics.get("marginal_rate_to_600_myr_per_kwh"),
            })
        
        if self._sensor_type == "savings_if_ideal_kwh":
            attrs.update({
                "current_bill_myr": optimization_data.get("cost_now_myr"),
                "target_bill_myr": optimization_data.get("ideal_cost_myr"),
                "target_import_kwh": optimization_data.get("ideal_import_kwh"),
                "delta_kwh": optimization_data.get("delta_to_ideal_kwh"),
                "primary_model": primary_model,
                "primary_label": optimization_data.get("primary_label"),
            })
        
        if self._sensor_type == "afa_optimization_savings":
            attrs.update({
                "current_month_import_kwh": optimization_data.get("current_import_kwh"),
                "kwh_to_600": optimization_data.get("kwh_to_600"),
                "cost_if_stop_now_myr": optimization_data.get("cost_now_myr"),
                "cost_if_600kwh_myr": optimization_data.get("cost_at_600_myr"),
                "marginal_rate_to_600_myr_per_kwh": optimization_data.get("avg_marginal_rate"),
                "primary_model": primary_model,
                # Rate comparison
                "avg_rate_now_myr_per_kwh": tou_metrics.get("avg_rate_now") if primary_model == "tou" else non_tou_metrics.get("avg_rate_now"),
            })
        
        if self._sensor_type == "afa_weird_zone":
            attrs.update({
                "savings_myr": optimization_data.get("afa_optimization_savings"),
                "kwh_to_600": optimization_data.get("kwh_to_600"),
                "current_import_kwh": optimization_data.get("current_import_kwh"),
                "primary_label": optimization_data.get("primary_label"),
                "marginal_rate_to_target": tou_metrics.get("marginal_rate_to_target") if primary_model == "tou" else non_tou_metrics.get("marginal_rate_to_target"),
            })
        
        if self._sensor_type == "afa_value_zone":
            primary_metrics = tou_metrics if primary_model == "tou" else non_tou_metrics
            attrs.update({
                "marginal_rate_to_target_myr_per_kwh": primary_metrics.get("marginal_rate_to_target"),
                "avg_rate_now_myr_per_kwh": primary_metrics.get("avg_rate_now"),
                "delta_cost_to_target_myr": primary_metrics.get("delta_cost_to_target_myr"),
                "delta_kwh_to_target": primary_metrics.get("delta_kwh_to_target"),
                "primary_label": optimization_data.get("primary_label"),
            })
        
        if self._sensor_type == "afa_explanation":
            primary_metrics = tou_metrics if primary_model == "tou" else non_tou_metrics
            attrs.update({
                "zone": optimization_data.get("optimization_zone"),
                "explanation": optimization_data.get("afa_explanation"),
                "current_import_kwh": optimization_data.get("current_import_kwh"),
                "cost_now_myr": optimization_data.get("cost_now_myr"),
                "cost_600_myr": optimization_data.get("cost_at_600_myr"),
                "afa_rate": optimization_data.get("afa_rate"),
                # New rate-based attributes
                "primary_model": primary_model,
                "primary_label": optimization_data.get("primary_label"),
                "recommended_target_kwh": optimization_data.get("ideal_import_kwh"),
                "avg_rate_now_myr_per_kwh": primary_metrics.get("avg_rate_now"),
                "avg_rate_target_myr_per_kwh": primary_metrics.get("avg_rate_target"),
                "marginal_rate_to_target_myr_per_kwh": primary_metrics.get("marginal_rate_to_target"),
                "delta_kwh_to_target": primary_metrics.get("delta_kwh_to_target"),
                "delta_cost_to_target_myr": primary_metrics.get("delta_cost_to_target_myr"),
                # Both models for advanced users
                "tou": tou_metrics,
                "non_tou": non_tou_metrics,
            })

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
        data = self.coordinator.data or {}
        return data.get("billing_start_day_active", self.coordinator._billing_start_day)
    
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
        self.coordinator.config[CONF_BILLING_START_DAY] = new_day

        # Trigger refresh
        await self.coordinator.async_refresh()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Expose pending billing start day information."""
        data = self.coordinator.data or {}
        attrs: Dict[str, Any] = {
            "billing_start_day_active": data.get("billing_start_day_active", self.coordinator._billing_start_day),
            "billing_start_day_configured": data.get("billing_start_day_configured", self.coordinator._billing_start_day),
        }
        pending_day = data.get("billing_start_day_pending")
        if pending_day is not None:
            attrs["billing_start_day_pending"] = pending_day
            attrs["note"] = f"Will switch to {pending_day} next billing cycle"
        return attrs


class TNBBillingStartDayStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor entity showing billing start day with pending change info."""

    _attr_icon = "mdi:calendar-start"

    def __init__(
        self,
        coordinator: TNBDataCoordinator,
        config_entry: ConfigEntry,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"{DEFAULT_NAME} Billing Start Day Status"
        self._attr_unique_id = f"{config_entry.entry_id}_billing_start_day_status"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
        }
        self._device_id = device_id

    @property
    def native_value(self) -> Optional[str]:
        """Return formatted billing start day string."""
        data = self.coordinator.data or {}
        active = data.get("billing_start_day_active")
        pending = data.get("billing_start_day_pending")

        if active is None:
            return None

        if pending is None:
            return str(active)

        return f"{active} (→ {pending} next cycle)"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Expose billing start day metadata."""
        data = self.coordinator.data or {}
        attrs: Dict[str, Any] = {
            "billing_start_day_active": data.get("billing_start_day_active"),
            "billing_start_day_configured": data.get("billing_start_day_configured"),
        }
        pending = data.get("billing_start_day_pending")
        if pending is not None:
            attrs["billing_start_day_pending"] = pending
            attrs["note"] = f"Will switch to {pending} next billing cycle"
        return attrs