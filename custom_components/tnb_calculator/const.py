"""Constants for TNB Calculator integration."""

DOMAIN = "tnb_calculator"

DEFAULT_NAME = "TNB Calculator"
DEFAULT_UPDATE_INTERVAL = 300  # 5 minutes

# Configuration keys
CONF_IMPORT_ENTITY = "import_entity"
CONF_EXPORT_ENTITY = "export_entity"
CONF_CALENDARIFIC_API_KEY = "calendarific_api_key"
CONF_COUNTRY = "country"
CONF_YEAR = "year"

# Base sensor types (always exposed)
BASE_SENSOR_TYPES = {
    "total_cost": {
        "name": "Total Cost",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "peak_cost": {
        "name": "Peak Cost",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "off_peak_cost": {
        "name": "Off Peak Cost",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
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

# Additional sensors exposed when ToU processing is available
TOU_SENSOR_TYPES = {
    "import_peak_energy": {
        "name": "Import Peak Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
    },
    "import_offpeak_energy": {
        "name": "Import Off Peak Energy",
        "unit": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
    },
    "charge_generation_peak": {
        "name": "Generation Charge Peak",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "charge_generation_offpeak": {
        "name": "Generation Charge Offpeak",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "charge_afa": {
        "name": "AFA Charge",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "charge_capacity": {
        "name": "Capacity Charge",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "charge_network": {
        "name": "Network Charge",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "charge_retailing": {
        "name": "Retailing Charge",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "charge_ict": {
        "name": "ICT Adjustment",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "charge_service_tax": {
        "name": "Service Tax",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "charge_kwtbb": {
        "name": "KWTBB Charge",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "rebate_nem_peak": {
        "name": "NEM Rebate Peak",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "rebate_nem_offpeak": {
        "name": "NEM Rebate Offpeak",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "rebate_nem_capacity": {
        "name": "NEM Rebate Capacity",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "rebate_nem_network": {
        "name": "NEM Rebate Network",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "rebate_insentif": {
        "name": "Insentif Leveling Rebate",
        "unit": "RM",
        "device_class": "monetary",
        "state_class": "measurement",
    },
    "rate_generation_peak": {
        "name": "Generation Peak Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
    },
    "rate_generation_offpeak": {
        "name": "Generation Off Peak Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
    },
    "rate_capacity": {
        "name": "Capacity Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
    },
    "rate_network": {
        "name": "Network Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
    },
    "rate_nem_peak": {
        "name": "NEM Peak Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
    },
    "rate_nem_offpeak": {
        "name": "NEM Offpeak Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
    },
    "rate_ict": {
        "name": "ICT Rate",
        "unit": "RM/kWh",
        "state_class": "measurement",
    },
}

ALL_SENSOR_TYPES = {**BASE_SENSOR_TYPES, **TOU_SENSOR_TYPES}

# Calendarific API
CALENDARIFIC_BASE_URL = "https://calendarific.com/api/v2"
CALENDARIFIC_HOLIDAYS_ENDPOINT = "/holidays"
