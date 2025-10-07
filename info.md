<div align="center">

<img src="https://raw.githubusercontent.com/salihinsaealal/home-assistant-tnb-calculator/master/icon.png" alt="TNB Calculator" width="120"/>

# TNB Calculator

[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-donate-ff813f.svg)](https://buymeacoffee.com/salihin)

**Calculate your TNB electricity costs in Malaysia**

</div>

A Home Assistant integration to calculate your TNB (Tenaga Nasional Berhad) electricity costs in Malaysia. Supports both Time of Use (ToU) and non-ToU tariffs with accurate monthly billing calculations.

## Features

- **Automatic ToU Detection**: Simply provide your Calendarific API key to enable Time of Use calculations
- **Peak/Off-Peak Splitting**: Integration automatically splits your import energy into peak (2PM-10PM weekdays) and off-peak (10PM-2PM + weekends + holidays) based on TNB schedule
- **Monthly Reset**: Automatically resets on the 1st of each month to match TNB billing cycle
- **Holiday Detection**: Uses Calendarific API to identify Malaysian public holidays for accurate off-peak rates
- **Persistent Storage**: Monthly data survives Home Assistant restarts, integration updates, and delete/re-add operations
- **Smart Meter Reset Handling**: Automatically detects and handles daily/monthly meter resets
- **Verified Accuracy**: Calculations match TNB tariff templates exactly for both ToU and non-ToU

## What's New in v3.7.3b0 (Beta)

- **⚙️ Optional Inputs Fixed**: Config flow now accepts blank export sensors and Calendarific API keys without blocking setup.
- **📊 Improved Predictions**: Direct cost averaging for accurate forecasts. Example: RM 3.00 over 4 days = RM 0.75/day × 30 = RM 22.50 ± 5%.
- **🔍 New Diagnostic Sensors**: `Prediction Method` and `Configuration Scenario` for better visibility.
- **🧼 Reset & Dashboard (Carry-over)**: Reset service refinements and Bubble dashboard template remain included.
- **✅ Beta Tag**: Marked as beta for community testing before stable release.

### Dashboard Usage
1. Install Bubble Card and ApexCharts Card (through HACS or manual resources) and add them under *Settings → Dashboards → Resources*.
2. Copy `dashboards/tnb_calculator_dashboard.yaml` into your dashboard configuration.
3. Either create a dedicated dashboard with the file content or merge its `views:` block with an existing dashboard.
4. Adjust entity IDs only if you renamed the default sensors.

## Configuration

1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "TNB Calculator"
4. Follow the setup steps:
   - Select your **import energy sensor** (required)
   - Select your **export energy sensor** (optional, for solar users)
   - **Optional**: Enter your Calendarific API key to enable ToU calculations
   - Get a free API key from [Calendarific.com](https://calendarific.com)

## Requirements

### Required:
- Import energy sensor (kWh) - tracks your total electricity consumption

### Optional:
- Export energy sensor (kWh) - for solar users
- Calendarific API key (free) - for Time of Use calculations

## Sensor Entities

After setup, these sensors will be created:

### Main Sensors
- **Total Cost (ToU/Non-ToU)**: Your monthly TNB bill
- **Import/Export Energy**: Monthly electricity flow in kWh
- **Net Energy**: Net consumption (Import - Export)
- **Predicted Monthly Cost**: Smart forecast with ±5% tolerance
- **Today Import/Export/Cost**: Real-time daily tracking

### Status & Automation
- **Period Status**: Peak/Off-Peak indicator
- **Usage Tier**: Billing tier (Below 600 kWh, 600-1500 kWh, Above 1500 kWh)
- **Peak Period/Holiday Today**: Binary sensors for automations

### Diagnostic Sensors
- **Prediction Method**: Shows Cost Trend or Hybrid algorithm
- **Configuration Scenario**: Your setup type (e.g., "Import + Export (ToU)")
- **Storage Health**: Data persistence status
- **Validation Status**: Configuration health check

### Detailed Cost Breakdown (ToU only)
- Generation Charge Peak/Off Peak, Capacity, Network, Service Tax
- KWTBB Charge, NEM Rebates, Rate Sensors

## Support

For issues or questions:
1. Check the [troubleshooting guide](https://github.com/salihinsaealal/home-assistant-tnb-calculator/blob/main/troubleshooting.md)
2. Review Home Assistant logs for error messages
3. [Open an issue](https://github.com/salihinsaealal/home-assistant-tnb-calculator/issues) on GitHub
