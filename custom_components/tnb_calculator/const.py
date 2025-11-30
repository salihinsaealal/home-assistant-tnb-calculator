"""Constants for TNB Calculator integration."""

from homeassistant.helpers.entity import EntityCategory

DOMAIN = "tnb_calculator"

DEFAULT_NAME = "TNB Calculator"
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes

# Spike detection threshold - maximum reasonable kWh change per update interval
# At 300s (5 min) interval, 50 kWh would mean 600 kW power which is unrealistic for residential
# Typical home: 10 kW max = 0.83 kWh per 5 min
# With solar: 20 kW max = 1.67 kWh per 5 min
# Set threshold at 10 kWh per interval to catch anomalies while allowing burst usage
MAX_DELTA_PER_INTERVAL = 10.0  # kWh

# Configuration keys
CONF_IMPORT_ENTITY = "import_entity"
CONF_EXPORT_ENTITY = "export_entity"
CONF_CALENDARIFIC_API_KEY = "calendarific_api_key"
CONF_COUNTRY = "country"
CONF_YEAR = "year"
CONF_BILLING_START_DAY = "billing_start_day"
CONF_VERSION = "4.3.0"

# Tariff defaults (can be overridden via service)
DEFAULT_AFA_RATE = 0.0145          # RM/kWh for usage >= 600 kWh
DEFAULT_AFA_THRESHOLD = 600        # kWh threshold for AFA
DEFAULT_RETAILING_CHARGE = 10.0    # RM fixed charge for usage > 600 kWh

# Tariff source types
TARIFF_SOURCE_DEFAULT = "default"
TARIFF_SOURCE_MANUAL = "manual"
TARIFF_SOURCE_API = "api"
TARIFF_SOURCE_WEBHOOK = "webhook"

# Tariff API configuration
CONF_TARIFF_API_URL = "tariff_api_url"
DEFAULT_TARIFF_API_URL = None  # No default - user must configure
TARIFF_API_TIMEOUT = 10  # seconds

# Auto-fetch tariff configuration (experimental)
AUTO_FETCH_API_URL = "https://tnb.cikgusaleh.work/complete"
AUTO_FETCH_ENABLED_KEY = "auto_fetch_enabled"

# Webhook configuration
WEBHOOK_ID = "tnb_calculator_tariff_webhook"

# Base sensor types (always exposed) - ordered by priority
BASE_SENSOR_TYPES = {
    # PRIORITY: Most important sensors at the top - Both cost types for easy comparison
    "total_cost_tou": {
        "name": "Total Cost (ToU)",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": None,  # Main entity
    },
    "total_cost_non_tou": {
        "name": "Total Cost (Non-ToU)",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": None,  # Main entity
    },
    "import_energy": {
        "name": "Import Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": None,  # Main entity
    },
    "export_energy": {
        "name": "Export Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": None,  # Main entity
    },
    "net_energy": {
        "name": "Net Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": None,  # Main entity
    },
    # Status sensors for monitoring
    "day_status": {
        "name": "Day Status",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": None,  # Main entity
    },
    "period_status": {
        "name": "Period Status",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": None,  # Main entity
    },
    # Prediction sensors
    "predicted_monthly_cost": {
        "name": "Predicted Monthly Cost",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": None,
        "entity_category": None,  # Main entity
    },
    "predicted_monthly_kwh": {
        "name": "Predicted Monthly Import",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": None,
        "entity_category": None,  # Main entity
    },
    "predicted_from_trend": {
        "name": "Predicted Cost (Current Trend)",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "predicted_from_history": {
        "name": "Predicted Cost (Historical)",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "prediction_confidence": {
        "name": "Prediction Confidence",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "daily_average_cost": {
        "name": "Daily Average Cost",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "daily_average_kwh": {
        "name": "Daily Average Consumption",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "days_remaining": {
        "name": "Days Until Reset",
        "unit": "days",
        "device_class": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Daily usage sensors (today's consumption)
    "today_import_kwh": {
        "name": "Today Import",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": None,  # Main entity
    },
    "today_export_kwh": {
        "name": "Today Export",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": None,  # Main entity
    },
    "today_net_kwh": {
        "name": "Today Net Usage",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "measurement",
        "entity_category": None,  # Main entity
    },
    "today_cost_tou": {
        "name": "Today Cost (ToU)",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": None,  # Main entity
    },
    "today_cost_non_tou": {
        "name": "Today Cost (Non-ToU)",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": None,  # Main entity
    },
    "today_import_peak_kwh": {
        "name": "Today Import Peak",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "today_import_offpeak_kwh": {
        "name": "Today Import Off-Peak",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Binary sensors for automations
    "peak_period": {
        "name": "Peak Period",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": None,  # Main entity (for automations)
    },
    "high_usage_alert": {
        "name": "High Usage Alert",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": None,  # Main entity (for automations)
    },
    "holiday_today": {
        "name": "Holiday Today",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": None,  # Main entity (for automations)
    },
    # Status sensors
    "tier_status": {
        "name": "Usage Tier",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": None,  # Main entity
    },
    # Diagnostic sensors (health & monitoring)
    "storage_health": {
        "name": "Storage Health",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "cached_holidays_count": {
        "name": "Cached Holidays",
        "unit": "holidays",
        "device_class": None,
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "last_update": {
        "name": "Last Update",
        "unit": None,
        "device_class": "timestamp",
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "integration_uptime": {
        "name": "Integration Uptime",
        "unit": "hours",
        "device_class": "duration",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "validation_status": {
        "name": "Validation Status",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "prediction_method": {
        "name": "Prediction Method",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "configuration_scenario": {
        "name": "Configuration Scenario",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Secondary cost breakdown
    "peak_cost": {
        "name": "Peak Cost",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "off_peak_cost": {
        "name": "Off Peak Cost",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Rate sensors (always visible)
    "rate_import": {
        "name": "Import Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rate_capacity": {
        "name": "Capacity Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rate_network": {
        "name": "Network Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rate_ict": {
        "name": "ICT Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}

# Additional sensors exposed when ToU processing is available
TOU_SENSOR_TYPES = {
    # PRIORITY: ToU energy breakdown at top
    "import_peak_energy": {
        "name": "Import Peak Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": None,  # Main entity
    },
    "import_offpeak_energy": {
        "name": "Import Off Peak Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "entity_category": None,  # Main entity
    },
    # Detailed charges (diagnostic - hidden by default)
    "charge_generation_peak": {
        "name": "Generation Charge Peak",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "charge_generation_offpeak": {
        "name": "Generation Charge Offpeak",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "charge_afa": {
        "name": "AFA Charge",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "charge_capacity": {
        "name": "Capacity Charge",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "charge_network": {
        "name": "Network Charge",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "charge_retailing": {
        "name": "Retailing Charge",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "charge_ict": {
        "name": "ICT Adjustment",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "charge_service_tax": {
        "name": "Service Tax",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "charge_kwtbb": {
        "name": "KWTBB Charge",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Rebates (diagnostic - hidden by default)
    "rebate_nem_peak": {
        "name": "NEM Rebate Peak",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rebate_nem_offpeak": {
        "name": "NEM Rebate Offpeak",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rebate_nem_capacity": {
        "name": "NEM Rebate Capacity",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rebate_nem_network": {
        "name": "NEM Rebate Network",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rebate_insentif": {
        "name": "Insentif Leveling Rebate",
        "unit": "MYR",
        "device_class": "monetary",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # ToU-specific rates (diagnostic - hidden by default)
    "rate_generation_peak": {
        "name": "Generation Peak Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rate_generation_offpeak": {
        "name": "Generation Off Peak Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rate_nem_peak": {
        "name": "NEM Peak Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "rate_nem_offpeak": {
        "name": "NEM Offpeak Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    # Tariff override sensors
    "rate_afa": {
        "name": "AFA Rate",
        "unit": "RM/kWh",
        "device_class": None,
        "state_class": "measurement",
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "tariff_source": {
        "name": "Tariff Source",
        "unit": None,
        "device_class": None,
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
    "tariff_last_updated": {
        "name": "Tariff Last Updated",
        "unit": None,
        "device_class": "timestamp",
        "state_class": None,
        "entity_category": EntityCategory.DIAGNOSTIC,
    },
}

ALL_SENSOR_TYPES = {**BASE_SENSOR_TYPES, **TOU_SENSOR_TYPES}

# Calendarific API
CALENDARIFIC_BASE_URL = "https://calendarific.com/api/v2"
CALENDARIFIC_HOLIDAYS_ENDPOINT = "/holidays"
