# TNB Calculator - Troubleshooting Guide

This guide helps you fix common problems with the TNB Calculator integration.

## Installation Problems

### Integration Not Showing Up
- Make sure you restarted Home Assistant after installation
- Check if the files are in the correct folder: `custom_components/tnb_calculator/`
- Look at Home Assistant logs for error messages

### HACS Installation Failed
- Check your internet connection
- Try clearing HACS cache
- Make sure the repository URL is correct

## Configuration Issues

### Can't Find Energy Sensors
- Go to Developer Tools > States in Home Assistant
- Look for sensors with device_class: energy
- Make sure your energy meter is properly configured
- Check if the sensor is updating with new values

### Setup Wizard Won't Complete
- Make sure you selected a valid energy sensor
- For ToU users, check your Calendarific API key
- Try restarting the setup process

## Sensor Problems

### Sensors Show "Unknown" or "Unavailable"
- Check if your energy sensors are working
- Make sure Home Assistant can read the sensor values
- Try restarting Home Assistant

### Values Not Updating
- Check if your energy meter is sending data
- Verify the sensor entity IDs in the configuration
- Look at the sensor's last_update time

### Wrong Cost Calculations
- Verify you selected the correct tariff type (ToU vs non-ToU)
- Check if your energy values are in kWh
- Make sure the billing cycle is correct

## ToU Specific Issues

### Holiday Detection Not Working
- Check your internet connection
- Verify your Calendarific API key is valid
- Make sure you have API quota remaining
- Check the integration logs for API errors

### Wrong Peak/Off-Peak Rates
- Make sure ToU is enabled in configuration
- Check if holiday detection is working
- Verify your energy meter timestamps are correct

## API Key Problems

### Invalid API Key Error
- Get a new API key from Calendarific website
- Make sure you copied the key correctly
- Check for extra spaces in the key

### API Quota Exceeded
- Free tier allows 1000 calls per month
- Upgrade to paid plan if needed
- The integration checks holidays once per day

## Performance Issues

### Slow Updates
- The integration updates every 5 minutes by default
- Check your Home Assistant performance
- Make sure your energy sensors update quickly

### High CPU Usage
- Check if you have many energy sensors
- Try reducing the update interval
- Make sure Calendarific API is responding quickly

## Logs and Debugging

### Check Home Assistant Logs
Go to Settings > System > Logs and look for:
- "TNB Calculator" messages
- Error messages related to the integration
- API call failures

### Debug Mode
Enable debug logging by adding this to configuration.yaml:
```yaml
logger:
  default: info
  logs:
    custom_components.tnb_calculator: debug
```

### Common Log Messages
- "Error updating TNB data" - Check your energy sensors
- "Failed to fetch holiday data" - Check API key and internet
- "Invalid API key" - Get a new key from Calendarific

## Getting Help

If you can't fix the problem:
1. Check this troubleshooting guide
2. Look at Home Assistant community forums
3. Check the GitHub repository for known issues
4. Provide error logs when asking for help

## Reset and Reinstall

If nothing works:
1. Remove the integration from Home Assistant
2. Delete the custom_components/tnb_calculator folder
3. Restart Home Assistant
4. Reinstall the integration
5. Try the setup again
