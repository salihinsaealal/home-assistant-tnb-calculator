# TNB Calculator for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/salihinsaealal/home-assistant-tnb-calculator.svg)](https://github.com/salihinsaealal/home-assistant-tnb-calculator/releases)
[![License](https://img.shields.io/github/license/salihinsaealal/home-assistant-tnb-calculator.svg)](LICENSE)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=salihinsaealal&repository=home-assistant-tnb-calculator&category=integration)

A Home Assistant integration to calculate your TNB (by Cikgu Saleh) electricity costs in Malaysia. Supports both Time of Use (ToU) and non-ToU tariffs with accurate monthly billing calculations.

## ⭐ What's New in v3.4.0

- **📅 Daily Usage Tracking**: Monitor today's consumption and costs in real-time
- **🤖 Automation Helpers**: Binary sensors for peak period, high usage alerts, holidays
- **📊 11 New Sensors**: Today's import/export, costs, tier status, and more
- **🔮 Smart Predictions**: Hybrid cost forecasting with historical learning (from v3.3.0)
- **🎯 TNB Compliance**: Exact 15-holiday schedule matching TNB tariff
- **✅ Verified Accuracy**: All calculations match TNB templates exactly

## Features

- **Automatic ToU Detection**: Simply provide your Calendarific API key to enable Time of Use calculations
- **Peak/Off-Peak Splitting**: Integration automatically splits your import energy into peak (2PM-10PM weekdays) and off-peak (10PM-2PM + weekends + holidays) based on TNB schedule
- **Detailed Cost Breakdown**: Get individual sensors for all charges, rebates, and rates for easy bill verification
- **Monthly Reset**: Automatically resets on the 1st of each month to match TNB billing cycle
- **Holiday Detection**: Uses Calendarific API to identify Malaysian public holidays for accurate off-peak rates
- **Persistent Storage**: Monthly data survives Home Assistant restarts, integration updates, and delete/re-add operations
- **Smart Meter Reset Handling**: Automatically detects and handles daily/monthly meter resets
- **Verified Accuracy**: Calculations match TNB tariff templates exactly for both ToU and non-ToU
## Installation

### Method 1: HACS (Recommended)

1. Make sure HACS is installed in your Home Assistant
2. Go to HACS > Integrations
3. Click the 3 dots menu and select "Custom repositories"
4. Add this repository URL and select "Integration" as category
5. Search for "TNB Calculator" and install it
6. Restart Home Assistant

### Method 2: Manual Installation

1. Download the `custom_components/tnb_calculator/` folder from this repository
2. Copy it to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "TNB Calculator"
4. Follow the setup steps:

### Setup Process:
1. Select your **import energy sensor** (required)
2. Select your **export energy sensor** (optional, for solar users)
3. **Optional**: Enter your Calendarific API key to enable ToU calculations
   - Get a free API key from [Calendarific.com](https://calendarific.com)
   - Without API key: Uses standard non-ToU tariff
   - With API key: Automatically enables ToU with peak/off-peak splitting
4. Finish setup

## Requirements

### Required:
- Import energy sensor (kWh) - tracks your total electricity consumption
- Export energy sensor (kWh) - optional, for solar users

### Optional (for ToU):
- Calendarific API key (free from calendarific.com)
- Internet connection for holiday detection

**Note**: The integration automatically handles peak/off-peak splitting internally when ToU is enabled. You don't need separate peak/off-peak sensors.

## Sensor Entities

After setup, these sensors will be created:

- **Total Cost**: Your monthly TNB bill in RM
- **Peak Cost**: Peak period charges (ToU only)
- **Off Peak Cost**: Off-peak period charges (ToU only)
- **Import Energy**: Monthly electricity imported in kWh
- **Import Peak Energy**: Monthly peak-period import in kWh (ToU only)
- **Import Off Peak Energy**: Monthly off-peak import in kWh (ToU only) 
- **Export Energy**: Monthly electricity exported in kWh
- **Net Energy**: Net consumption (Import - Export) in kWh

### Detailed Cost Sensors (ToU only):
- **Generation Charge Peak/Off Peak**: Energy generation costs
- **AFA Charge**: Additional facility charge
- **Capacity Charge**: Grid capacity costs
- **Network Charge**: Transmission and distribution costs
- **Retailing Charge**: Retail service charge
- **ICT Adjustment**: Information and communication technology adjustment
- **Service Tax**: Government service tax (8%)
- **KWTBB Charge**: Kumpulan Wang Tenaga Boleh Baharu charge
- **NEM Rebates**: Net energy metering rebates for solar export
- **Insentif Rebate**: Incentive leveling rebate
- **Rate Sensors**: Current tariff rates for all components

## How It Works

### Monthly Calculation
- The integration tracks your energy usage from the 1st of each month
- Calculations reset automatically on the 1st of every month
- This matches TNB's billing cycle
- Peak/off-peak splitting is handled automatically by the integration based on time and holidays

### Cost Calculation
- Uses official TNB tariff rates for Malaysia
- Includes all charges: generation, capacity, network, service tax
- Handles tiered pricing (first 600 kWh vs excess)
- Calculates export credits for solar users
- ToU mode automatically splits import energy and applies appropriate rates and NEM rebates

### Holiday Detection (ToU only)
- Uses Calendarific API to check Malaysian holidays
- **Matches TNB's official 15-holiday list exactly**:
  - Hari Tahun Baharu, Chinese New Year (2 days), Hari Raya Aidilfitri (2 days)
  - Hari Pekerja, Wesak, Yang di-Pertuan Agong's Birthday, Hari Raya Haji (1 day)
  - Awal Muharram, Hari Kemerdekaan, Hari Malaysia, Maulidur Rasul, Deepavali, Krismas
- Automatically applies off-peak rates on holidays
- Islamic dates dynamically updated annually from Calendarific API

## Usage Examples

### Basic Setup
After installation, your sensors will show:
- Current month's electricity costs
- Remaining days in billing cycle
- Holiday status (ToU users)

### Dashboard Cards
You can add these sensors to your dashboard:

```yaml
type: entities
entities:
  - entity: sensor.tnb_calculator_total_cost
  - entity: sensor.tnb_calculator_import_energy
  - entity: sensor.tnb_calculator_net_energy
```

### Automations
Create automations based on your electricity usage:

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.tnb_calculator_total_cost
    above: 150
action:
  - service: notify.mobile_app
    data:
      message: "Electricity bill is getting high this month"
```

## Troubleshooting

### Sensor Shows Zero
- Check if your energy sensors are working
- Make sure the sensor entities exist in Home Assistant
- Verify the sensor is updating with new values

### Wrong Calculations
- Double-check your tariff type (ToU vs non-ToU)
- For ToU users, verify your Calendarific API key is working
- Check if your energy sensors report in kWh

### Sudden Spikes or Meter Resets
The integration includes automatic spike detection to prevent data corruption from:
- **Sensor glitches**: Unrealistic sudden increases are filtered out
- **Meter resets**: Automatically detected and handled
- **Threshold**: Changes exceeding 10 kWh per 5-minute interval are ignored
- **Logging**: Check Home Assistant logs for warnings about detected spikes

If you see warnings in the logs about spike detection, it means the integration protected your data from corruption. The baseline will be restored when your sensor returns to normal values.

### Holiday Detection Not Working
- Check your internet connection
- Verify your Calendarific API key is valid
- Make sure the API has quota remaining

### Integration Won't Load
- Check Home Assistant logs for errors
- Make sure all required files are in the custom_components folder
- Try restarting Home Assistant

## Support

If you have issues:
1. Check the troubleshooting section above
2. Look at Home Assistant logs for error messages
3. Make sure your energy sensors are configured correctly

## License

This integration is open source. Feel free to modify and share.

## Version History

- v1.0.0: Initial release with non-ToU and ToU support
