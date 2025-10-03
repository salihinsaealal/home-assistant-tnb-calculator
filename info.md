# TNB Calculator for Home<div align="center">

<img src="https://raw.githubusercontent.com/salihinsaealal/home-assistant-tnb-calculator/master/energyMonitoringicon.png" alt="TNB Calculator" width="120"/>

# TNB Calculator

**Calculate your TNB electricity costs in Malaysia**

</div> Berhad) electricity costs in Malaysia. Supports both Time of Use (ToU) and non-ToU tariffs with accurate monthly billing calculations.

## Features

- **Automatic ToU Detection**: Simply provide your Calendarific API key to enable Time of Use calculations
- **Peak/Off-Peak Splitting**: Integration automatically splits your import energy into peak (2PM-10PM weekdays) and off-peak (10PM-2PM + weekends + holidays) based on TNB schedule
- **Monthly Reset**: Automatically resets on the 1st of each month to match TNB billing cycle
- **Holiday Detection**: Uses Calendarific API to identify Malaysian public holidays for accurate off-peak rates
- **Persistent Storage**: Monthly data survives Home Assistant restarts, integration updates, and delete/re-add operations
- **Smart Meter Reset Handling**: Automatically detects and handles daily/monthly meter resets
- **Verified Accuracy**: Calculations match TNB tariff templates exactly for both ToU and non-ToU

## What's New in v3.3.0

- **🔮 Hybrid Cost Prediction**: Smart bill forecasting that learns from your usage patterns
- **📊 8 New Sensors**: Daily averages, projected costs, confidence indicators
- **🎯 TNB Holiday Compliance**: Fixed to match official 15-holiday schedule
- **📈 Historical Learning**: Gets smarter each month (stores last 12 months)
- **✅ Verified Accuracy**: Calculations match TNB tariff templates exactly

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

- **Total Cost**: Your monthly TNB bill in RM
- **Peak Cost**: Peak period charges (ToU only)
- **Off Peak Cost**: Off-peak period charges (ToU only)
- **Import Energy**: Monthly electricity imported in kWh
- **Import Peak Energy**: Monthly peak-period import in kWh (ToU only)
- **Import Off Peak Energy**: Monthly off-peak import in kWh (ToU only)
- **Export Energy**: Monthly electricity exported in kWh
- **Net Energy**: Net consumption (Import - Export) in kWh

### Detailed Cost Sensors (ToU only):
- Generation Charge Peak/Off Peak
- AFA Charge, Capacity Charge, Network Charge
- Retailing Charge, ICT Adjustment, Service Tax
- KWTBB Charge, NEM Rebates, Insentif Rebate
- Rate Sensors for all components

## Support

For issues or questions:
1. Check the [troubleshooting guide](https://github.com/salihinsaealal/home-assistant-tnb-calculator/blob/main/troubleshooting.md)
2. Review Home Assistant logs for error messages
3. [Open an issue](https://github.com/salihinsaealal/home-assistant-tnb-calculator/issues) on GitHub
