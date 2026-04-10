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

## What's New in v4.4.7

### AFA optimization sensor fix

- Fixed `ideal_import_kwh_tou` and `ideal_import_kwh_non_tou` sensors showing as unavailable when the optimization calculation takes the early-return fallback path (PR #4, @zubir2k).

## What's New in v4.4.5

### Solar / NEM billing accuracy and monthly bill history

- NEM export credits capped at import base charges (no negative bills).
- New sensor: `sensor.tnb_calculator_nem_excess_kwh` (excess NEM credit carried forward).
- New sensor: `sensor.tnb_calculator_monthly_bill` with last-12-month history in attributes.
- New service: `tnb_calculator.calibrate_monthly_cost` for actual bill storage.
- Accurate daily peak/off-peak tracking with delta-based, boundary-aware splitting.

### Dashboard Usage
1. Install Bubble Card and ApexCharts Card (through HACS or manual resources) and add them under Settings -> Dashboards -> Resources.
2. Copy `dashboards/tnb_calculator_dashboard.yaml` into your dashboard configuration.
3. Either create a dedicated dashboard with the file content or merge its `views:` block with an existing dashboard.
4. Adjust entity IDs only if you renamed the default sensors.

## Optional: Automatic AFA Rate Updates

You can keep the Additional Fuel Adjustment (AFA) rate in sync with TNB's website using:

- **External scraper service** (FastAPI + Playwright) in `tnb-afa-scraper/`
- **Automation blueprint** in `blueprints/automation/tnb_calculator/auto_update_afa_rate.yaml`

### External scraper (tnb-afa-scraper)

Run the scraper on a small Linux server (e.g. N150 Ubuntu) with Docker Compose. It exposes:

```http
GET /afa/simple
```

Example response:

```json
{
  "afa_rate": 0.0891,
  "afa_rate_raw": -0.0891,
  "effective_date": "2025-11-01",
  "last_scraped": "2025-11-28T10:18:14.908641"
}
```

Use the `afa_rate` field (can be negative for rebates) with the `tnb_calculator.fetch_afa_rate` service.

### Automation blueprint

1. Copy the blueprint file to your Home Assistant config:

 ```text
   /config/blueprints/automation/tnb_calculator/auto_update_afa_rate.yaml
   ```

2. In Home Assistant, go to Settings -> Automations & Scenes -> Blueprints.
3. Select "TNB Calculator - Auto Update AFA Rate" and choose Create automation from blueprint.
4. Configure:
 - **Scraper API URL**: `http://<N150-IP>:8001/afa/simple`
 - **Time of day**: e.g. `00:10:00`
 - **Day of month**: e.g. `1`

The automation will call `tnb_calculator.fetch_afa_rate` monthly with the scraper URL and update the AFA rate automatically.

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
- **Predicted Monthly Cost**: Smart forecast with 5% tolerance
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
