# TNB Calculator for Home Assistant

This is a Home Assistant integration that calculates TNB (Tenaga Nasional Berhad) electricity costs. It works with both regular and Time of Use (ToU) electricity tariffs in Malaysia.

## Features

- Calculate monthly TNB electricity bills
- Support for both non-ToU and ToU customers
- Automatic holiday detection for ToU off-peak rates
- Monthly billing cycle that resets on the 1st of each month
- Support for import and export energy (solar/net metering)
- Real-time cost updates

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

### For Non-ToU Users:
- Select your import energy sensor
- Select your export energy sensor (optional, for solar users)
- Leave ToU disabled
- Finish setup

### For ToU Users:
- Select your import energy sensor
- Select your export energy sensor (optional)
- Enable "Time of Use" option
- Enter your Calendarific API key (get one from https://calendarific.com)
- Finish setup

## Requirements

### For Non-ToU Users:
- Energy sensor that tracks your electricity consumption

### For ToU Users:
- Energy sensor for consumption
- Calendarific API key for holiday detection
- Internet connection for API calls

## Sensor Entities

After setup, these sensors will be created:

- **Total Cost**: Your monthly TNB bill in RM
- **Peak Cost**: Peak period charges (ToU only)
- **Off Peak Cost**: Off-peak period charges (ToU only)
- **Import Energy**: Monthly electricity imported in kWh
- **Export Energy**: Monthly electricity exported in kWh
- **Net Energy**: Net consumption (Import - Export) in kWh

## How It Works

### Monthly Calculation
- The integration tracks your energy usage from the 1st of each month
- Calculations reset automatically on the 1st of every month
- This matches TNB's billing cycle

### Cost Calculation
- Uses official TNB tariff rates for Malaysia
- Includes all charges: generation, capacity, network, service tax
- Handles tiered pricing (first 600 kWh vs excess)
- Calculates export credits for solar users

### Holiday Detection (ToU only)
- Uses Calendarific API to check Malaysian holidays
- Automatically applies off-peak rates on holidays
- Reduces your electricity bill on public holidays

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
