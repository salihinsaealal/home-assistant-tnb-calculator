"""Constants for TNB Calculator integration."""
DOMAIN = "tnb_calculator"

# Default values
DEFAULT_NAME = "TNB Calculator"
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes

# Configuration keys
CONF_IMPORT_ENTITY = "import_entity"
CONF_EXPORT_ENTITY = "export_entity"
CONF_TOU_ENABLED = "tou_enabled"
CONF_CALENDARIFIC_API_KEY = "calendarific_api_key"
CONF_COUNTRY = "country"
CONF_YEAR = "year"

# Sensor types
SENSOR_TYPES = {
    "total_cost": {
        "name": "Total Cost",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "total_increasing",
    },
    "peak_cost": {
        "name": "Peak Cost",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "total_increasing",
    },
    "off_peak_cost": {
        "name": "Off Peak Cost",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "total_increasing",
    },
    "import_energy": {
        "name": "Import Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
    },
    "export_energy": {
        "name": "Export Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
    },
    "net_energy": {
        "name": "Net Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
    },
}

# Calendarific API
CALENDARIFIC_BASE_URL = "https://calendarific.com/api/v2"
CALENDARIFIC_HOLIDAYS_ENDPOINT = "/holidays"
