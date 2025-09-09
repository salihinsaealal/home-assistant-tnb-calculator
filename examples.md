# TNB Calculator - Configuration Examples

Here are some example configurations for different setups.

## Basic Non-ToU Setup

If you have a simple electricity meter without solar:

```yaml
# In configuration.yaml (if using YAML mode)
tnb_calculator:
  import_entity: sensor.electricity_meter_total
```

## Solar/Net Metering Setup

If you have solar panels with net metering:

```yaml
# In configuration.yaml (if using YAML mode)
tnb_calculator:
  import_entity: sensor.electricity_import_total
  export_entity: sensor.electricity_export_total
```

## ToU Setup with Holiday Detection

For Time of Use customers:

```yaml
# In configuration.yaml (if using YAML mode)
tnb_calculator:
  import_entity: sensor.electricity_import_total
  export_entity: sensor.electricity_export_total
  tou_enabled: true
  calendarific_api_key: "your_api_key_here"
  country: "MY"
  year: 2024
```

## Dashboard Card Examples

### Simple Cost Display
```yaml
type: entity
entity: sensor.tnb_calculator_total_cost
name: Monthly Electricity Bill
```

### Detailed Energy Usage
```yaml
type: entities
title: Electricity Usage
entities:
  - entity: sensor.tnb_calculator_total_cost
    name: Total Cost
  - entity: sensor.tnb_calculator_import_energy
    name: Imported
  - entity: sensor.tnb_calculator_export_energy
    name: Exported
  - entity: sensor.tnb_calculator_net_energy
    name: Net Usage
```

### Monthly Progress
```yaml
type: gauge
entity: sensor.tnb_calculator_total_cost
min: 0
max: 200
title: Electricity Bill Progress
```

## Automation Examples

### High Bill Alert
```yaml
alias: High Electricity Bill Alert
trigger:
  platform: numeric_state
  entity_id: sensor.tnb_calculator_total_cost
  above: 150
action:
  service: notify.notify
  data:
    message: "Electricity bill is RM{{ states('sensor.tnb_calculator_total_cost') }} this month"
```

### Monthly Bill Summary
```yaml
alias: Monthly Electricity Summary
trigger:
  platform: time
  at: "23:59:59"
condition:
  condition: template
  value_template: "{{ now().day == 1 }}"
action:
  service: notify.notify
  data:
    message: >
      Last month's electricity bill: RM{{ states('sensor.tnb_calculator_total_cost') }}
      Total usage: {{ states('sensor.tnb_calculator_import_energy') }} kWh
```

## Sensor Configuration Examples

### Energy Meter Setup
Make sure your energy sensors are properly configured:

```yaml
# Example energy sensor
sensor:
  - platform: template
    sensors:
      electricity_import_total:
        friendly_name: "Electricity Import Total"
        unit_of_measurement: "kWh"
        value_template: "{{ states('sensor.your_energy_meter') }}"
        device_class: energy
```

### Utility Meter for Monthly Tracking
```yaml
utility_meter:
  electricity_monthly:
    source: sensor.electricity_import_total
    cycle: monthly
```

## API Key Setup

To get a Calendarific API key:
1. Go to https://calendarific.com
2. Sign up for a free account
3. Get your API key from the dashboard
4. Enter it in the TNB Calculator configuration

The free tier allows 1000 API calls per month, which is enough for daily holiday checks.
