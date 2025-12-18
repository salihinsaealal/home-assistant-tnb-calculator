<div align="center">

<img src="icon.png" alt="TNB Calculator" width="200"/>

# TNB Calculator for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/salihinsaealal/home-assistant-tnb-calculator.svg)](https://github.com/salihinsaealal/home-assistant-tnb-calculator/releases)
[![License](https://img.shields.io/github/license/salihinsaealal/home-assistant-tnb-calculator.svg)](LICENSE)
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-donate-ff813f.svg)](https://buymeacoffee.com/salihin)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=salihinsaealal&repository=home-assistant-tnb-calculator&category=integration)

**Calculate your TNB (Tenaga Nasional Berhad) electricity costs in Malaysia**

Supports both Time of Use (ToU) and non-ToU tariffs with accurate monthly billing calculations

</div>

---

## ⭐ What's New in v4.4.4

### ⚡ Accurate Daily Peak/Off-Peak Tracking

The daily ToU sensors now show **actual usage timing**, not estimates:

- **True Delta-Based Daily Split**
  - `sensor.tnb_calculator_today_import_peak_kwh` — Today's import during peak hours
  - `sensor.tnb_calculator_today_import_offpeak_kwh` — Today's import during off-peak hours
  - **Always true:** `today_import_peak_kwh + today_import_offpeak_kwh == today_import_kwh` (within rounding)

- **Boundary-Aware Splitting**
  - Correctly handles 2PM and 10PM boundary crossings within update intervals
  - Properly splits energy when an update spans peak/off-peak transition
  - Weekends and holidays are fully off-peak

- **More Accurate `Today Cost (ToU)`**
  - Now uses the corrected daily peak/off-peak split for cost calculation

### What Changed
- Daily sensors now accumulate from deltas (like monthly), not from ratio estimates
- `_split_delta_by_period()` helper ensures accurate time-based allocation
- Monthly calculations remain unchanged

<details>
  <summary><strong>v4.4.3 release notes</strong></summary>

### 🎯 Separate ToU & Non-ToU Recommendations + Smart Stay Put

Major improvements to the AFA optimization sensors:

- **Separate Entities for ToU and Non-ToU**
  - `sensor.tnb_calculator_ideal_import_kwh_tou` — ToU-specific recommendation
  - `sensor.tnb_calculator_ideal_import_kwh_non_tou` — Non-ToU recommendation
  - Each model computes its own target independently — no more forced agreement.

- **Option B Gating: Only Recommend When It's Value**
  - Only recommends increasing usage if label is `saves_money`, `super_value`, or `value`.
  - If extra kWh isn't worth it (`normal`/`expensive`), the sensor stays at your current usage.

- **New `stay_put` Zone**
  - When you're near the 550–600 kWh band but extra kWh isn't good value, zone becomes `stay_put`.
  - Clear messaging: "No value in adding kWh."

- **Normalized Attribute Keys**
  - Unit-suffixed keys: `*_myr`, `*_kwh`, `*_myr_per_kwh`
  - Rates now use 3 decimal places for precision.
  - Backward-compatible aliases retained.

</details>

<details>
  <summary><strong>v4.4.2 release notes</strong></summary>

### 🎯 Smarter AFA Optimization with Marginal Rate Analysis

The AFA optimization sensors now use a **practical, rate-based approach** to help you make informed decisions:

- **Recommended Target Import** (not theoretical minimum)
  - `sensor.tnb_calculator_ideal_import_kwh`
    - Now shows a **practical target** in the 550–600 kWh range based on **lowest marginal cost**.
    - Target is always **>= your current import** (no impractical "use 0 kWh" suggestions).
    - Attributes include: `avg_rate_now`, `avg_rate_target`, `marginal_rate_to_target`, and both ToU/non-ToU metrics.

- **Rich Attributes on All Optimization Sensors**
  - Both **ToU** and **non-ToU** metrics exposed for comparison.
  - `afa_explanation` now shows rate-based messaging with clear RM/kWh figures.

</details>

<details>
  <summary><strong>Older release notes</strong></summary>

## ⭐ What's New in v4.3.5

### 🔁 Weekly Auto-Fetch & AFA API URL

- **Weekly AFA-only auto-refresh**:
  - When AFA source is `api` and the full-tariff auto-fetch switch is **OFF**, the integration re-fetches the AFA rate at most **once per week**.
  - URL priority:
    1. Integration option `tariff_api_url` (configured in the UI).
    2. Last-used URL stored in `_tariff_overrides["api_url"]`.
    3. Default fallback: `https://tnb.cikgusaleh.work/afa/simple`.
  - Failures are logged but the previous AFA rate is kept.
- **Weekly full-tariff auto-refresh** (recap):
  - When `switch.tnb_calculator_auto_fetch_tariffs` is ON, tariffs from `/complete` are refreshed at most once per week.
  - When OFF, integration uses hardcoded tariffs.
- **New AFA API URL entity**:
  - Entity: `text.tnb_calculator_afa_api_url`.
  - Lets you view/edit the AFA API URL directly in Home Assistant.
  - Attributes show `current_url`, `default_url`, and `effective_url`.

### 🧾 State-Only Energy Entity Support

- Import/export energy entities **no longer need an entity registry entry**.
- If an energy sensor only exists in `hass.states` (no `unique_id`), the config flow uses a **relaxed validation path** based on state attributes (domain, unit, numeric value).
- Existing users with registry-based entities are unaffected; this change only enables additional setups that previously failed validation.

## ⭐ What's New in v4.3.2

### 🧮 Dynamic Tariffs from Scraper (Complete API)

- **Full tariff table from API**: Integration can now consume the `/complete` endpoint from the external scraper (`https://tnb.cikgusaleh.work/complete`) and store:
  - AFA (current + periods)
  - ToU generation (peak/off-peak, tiers)
  - Non-ToU generation
  - Capacity & Network charges
  - Retailing charge
  - ICT tiers (16 levels)
- **Stored tariffs wired into calculations**:
  - `_calculate_tou_costs` and `_calculate_non_tou_costs` now use stored tariffs when available.
  - If no API data is present, integration safely falls back to the original hardcoded tariffs.

### 🔘 Auto Fetch Tariffs Switch (Experimental)

- New switch entity: `switch.tnb_calculator_auto_fetch_tariffs`.
- **OFF (default)**: Uses hardcoded tariff values (exactly like older versions).
- **ON**:
  - Fetches all tariffs from the scraper `/complete` endpoint.
  - Stores them in persistent storage.
  - All cost calculations use live TNB tariffs from the API.
- Turning **OFF** again:
  - Resets **all** tariff overrides (including AFA) back to hardcoded defaults.
  - Ensures a clean, known-good baseline if anything looks wrong.

### 💱 Proper Currency Handling (MYR)

- All cost sensors now use:
  - `unit_of_measurement: "MYR"`
  - `device_class: "monetary"`
- All rate sensors use `MYR/kWh` instead of `RM/kWh`.
- This matches ISO-4217 and allows Home Assistant to correctly detect monetary sensors.

### 🔄 Refined AFA Services

- `set_tariff_rates` / `fetch_tariff_rates` have been split and clarified into:
  - `set_afa_rate`: manual AFA override (positive `MYR/kWh`).
  - `fetch_afa_rate`: fetch AFA only from `/afa/simple`.
  - `fetch_all_rates`: fetch full tariff table from `/complete`.
- Reset service updated to `reset_tariff_rates` to reset **all** tariffs (not just AFA).

## ⭐ What's New in v4.1.1

### 🔄 Dynamic AFA Rate Management (API & Scraper Ready)

- **Configurable AFA Rate**: AFA (Additional Fuel Adjustment) rate is configurable via services and stored in persistent storage.
- **Multiple Sources**: AFA rate can come from:
  - **Default** hard-coded tariff
  - **Manual override** via `set_tariff_rates` service (superseded by `set_afa_rate` in v4.3.x)
  - **Remote API** via `fetch_tariff_rates` service (superseded by `fetch_afa_rate` / `fetch_all_rates`)
  - **Webhook** updates (future integrations)
- **Diagnostic Sensors**: Sensors expose the current AFA rate, source, and last updated time for easier monitoring.
- **External Scraper Support**: Optional `tnb-afa-scraper` (FastAPI + Playwright) service to automatically scrape TNB's AFA table and return a ready-to-use `afa_rate`.
- **Automation Blueprint**: Bundle includes an automation blueprint to call the AFA fetch service monthly using the scraper URL.
- **Positive AFA Rate Handling**: Scraper normalizes TNB's negative rebate values to a positive `afa_rate` so existing cost calculations remain correct.

## ⭐ What's New in v4.0.0

### 🎉 Major Release - Configuration & Calibration Overhaul

- **🔄 Dynamic Configuration Updates**: API key and billing start day changes apply instantly without deleting/re-adding integration
  - Add Calendarific API key via Configure → ToU mode activates immediately
  - Change billing start day → updates at next cycle with clear pending indicator
- **📅 Billing Start Day Status**: New sensor shows `"1 (→ 4 next cycle)"` when changes are pending
- **⚡ Improved Calibration Services**: 
  - Distribution options reordered: **Auto** (default) → Peak → Off-Peak → Proportional → Manual
  - Clear delay information: "Values update immediately in storage but sensor display has a delay"
  - Simplified UI with cleaner descriptions
- **🔧 Service Fixes**: All calibration services now work correctly with proper refresh handling
- **📊 Better UX**: Pending configuration changes visible in sensor attributes and status displays

</details>

## Features

- **Automatic ToU Detection**: Simply provide your Calendarific API key to enable Time of Use calculations
- **Peak/Off-Peak Splitting**: Integration automatically splits your import energy into peak (2PM-10PM weekdays) and off-peak (10PM-2PM + weekends + holidays) based on TNB schedule
- **Monthly Reset**: Automatically resets on the 1st of each month to match TNB billing cycle
- **Holiday Detection**: Uses Calendarific API to identify Malaysian public holidays for accurate off-peak rates
- **Persistent Storage**: Monthly data survives Home Assistant restarts, integration updates, and delete/re-add operations
- **Smart Meter Reset Handling**: Automatically detects and handles daily/monthly meter resets
- **Verified Accuracy**: Calculations match TNB tariff templates exactly for both ToU and non-ToU

## Services

### Bill Comparison

Compare the calculated bill with your actual TNB invoice and receive a persistent notification summarizing the difference.

```yaml
service: tnb_calculator.compare_with_bill
data:
  actual_bill: 156.50  # MYR amount from your bill
  month: 10            # Optional: billing month (1-12)
  year: 2025           # Optional: billing year
```
- The integration logs the comparison and posts a notification showing the calculated cost, actual bill, absolute difference, and percentage variance.
- If the difference exceeds ±5%, the notification highlights it so you can investigate.

### Energy Calibration Services

Fine-tune your energy readings to match your actual TNB meter or bill.

#### Set Import Energy Values
Set exact import energy values for calibration:

```yaml
service: tnb_calculator.set_import_energy_values
data:
  import_total: 1500.5  # Target total import in kWh
  distribution: "auto"  # How to split between peak/off-peak
```

**Distribution Options:**
- **Auto** (default): Detects based on current time
- **Peak Only**: Change affects peak period only
- **Off-Peak Only**: Change affects off-peak period only
- **Proportional**: Split by current peak/off-peak ratio
- **Manual**: Specify exact peak/off-peak values

#### Adjust Import Energy Values
Apply offset adjustments (add/subtract) to current values:

```yaml
service: tnb_calculator.adjust_import_energy_values
data:
  import_adjustment: 20.5  # Amount to add (+) or subtract (-)
  distribution: "auto"
```

#### Set/Adjust Export Energy Values
Similar services available for export energy (solar users):
- `tnb_calculator.set_export_energy_values`
- `tnb_calculator.adjust_export_energy_values`

**⏱️ Note on Calibration Delays:**
- Values update **immediately in storage**
- Sensor display updates on next coordinator refresh (~5 minutes)
- For **instant sensor refresh**, reload the integration via Settings → Devices & Services → TNB Calculator → Reload

### Reset Storage

Clear all cached data (energy totals, historical months, holidays):

```yaml
service: tnb_calculator.reset_storage
data:
  confirm: "RESET"  # Type exactly "RESET" to confirm
```

## Installation

### Method 1: HACS (Recommended)

1. Make sure HACS is installed in your Home Assistant
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

### Main Sensors
- **Total Cost (ToU)**: Your monthly TNB bill with Time of Use rates
- **Total Cost (Non-ToU)**: Your monthly bill with flat tariff
- **Import Energy**: Monthly electricity imported in kWh
- **Export Energy**: Monthly electricity exported in kWh
- **Net Energy**: Net consumption (Import - Export) in kWh
- **Predicted Monthly Cost**: Smart forecast of end-of-month bill
- **Predicted Monthly Import**: Projected total kWh consumption

### Time of Use Sensors (when API key provided)
- **Import Peak Energy**: Monthly peak-period import (2PM-10PM weekdays)
- **Import Off Peak Energy**: Monthly off-peak import (nights, weekends, holidays)
- **Peak Cost**: Peak period charges
- **Off Peak Cost**: Off-peak period charges

### Daily Tracking
- **Today Import/Export**: Real-time daily consumption
- **Today Cost (ToU/Non-ToU)**: Today's accumulated charges

### Status & Automation Helpers
- **Period Status**: Current time period (Peak/Off-Peak)
- **Day Status**: Weekday/Weekend/Holiday
- **Usage Tier**: Current billing tier (Below 600 kWh, 600-1500 kWh, Above 1500 kWh)
- **Peak Period**: Binary sensor for automations (on during peak hours)
- **High Usage Alert**: Binary sensor (on when approaching 600 kWh tier)
- **Holiday Today**: Binary sensor (on during public holidays)

### Diagnostic Sensors
- **Prediction Method**: Shows active prediction algorithm (Cost Trend or Hybrid)
- **Configuration Scenario**: Your setup type (e.g., "Import + Export (ToU)")
- **Storage Health**: Data persistence status
- **Validation Status**: Configuration health check
- **Cached Holidays**: Number of holidays stored
- **Integration Uptime**: Hours since integration started

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

### Monthly Calculation & Custom Billing Cycles
- **Custom Billing Start Day**: Set your TNB billing cycle start date (1-31) via the Billing Start Day number entity
  - Changes take effect at the next billing cycle boundary
  - Pending changes shown in `sensor.tnb_calculator_billing_start_day_status` (e.g., `"1 (→ 4 next cycle)"`)
  - Attributes expose `billing_start_day_active`, `billing_start_day_configured`, and `billing_start_day_pending`
- Calculations reset automatically based on your configured billing start day
- Peak/off-peak splitting is handled automatically by the integration based on time and holidays

### Cost Calculation
- Uses official TNB tariff rates for Malaysia
- Includes all charges: generation, capacity, network, service tax
- Handles tiered pricing (first 600 kWh vs excess)
- Calculates export credits for solar users
- ToU mode automatically splits import energy and applies appropriate rates and NEM rebates

### Smart Predictions
- **Cost Trend Method**: Direct cost averaging - `(current_cost / days_elapsed) × days_in_month`
  - Example: MYR 3.00 over 4 days = MYR 0.75/day × 30 = MYR 22.50 ± 5%
  - More accurate than kWh projection, especially early in the month
- **Hybrid Method**: Weighted combination of cost trend + historical average (when 2+ months of data available)
  - Early month (days 1-7): 30% trend, 70% history
  - Mid month (days 8-20): 60% trend, 40% history
  - Late month (days 21+): 80% trend, 20% history
- **Confidence Levels**: High (3+ months), Medium (1-2 months), Low (no history)

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

## Pre-built Dashboard (Bubble Card + ApexCharts)
- **Location:** `dashboards/tnb_calculator_dashboard.yaml`
- **Dependencies:**
  - [Bubble Card](https://github.com/Clooos/Bubble-Card)
  - [ApexCharts Card](https://github.com/RomRider/apexcharts-card)

### Use as a dedicated dashboard
1. Make sure both custom cards are installed and added under *Settings → Dashboards → Resources*.
2. Copy `dashboards/tnb_calculator_dashboard.yaml` into your `config/www/` (or include it via your dashboard YAML).
3. In Home Assistant, create a new dashboard and paste the contents of the file. It renders monthly summaries, daily usage, diagnostics, and service buttons.

### Add as an extra view to an existing dashboard
1. Open your dashboard YAML.
2. Append the `views:` block from `dashboards/tnb_calculator_dashboard.yaml` (or merge its single view with your layout).
3. Update entity IDs if you renamed any sensors.

The layout uses Bubble Card for quick metrics and ApexCharts for energy/cost trends. Buttons at the bottom call `tnb_calculator.compare_with_bill` and `tnb_calculator.reset_storage`.

### Automations

#### High Bill Alert
```yaml
alias: High Electricity Bill Alert
trigger:
  - platform: numeric_state
    entity_id: sensor.tnb_calculator_total_cost_tou
    above: 150
action:
  - service: notify.mobile_app
    data:
      message: "Electricity bill is RM{{ states('sensor.tnb_calculator_total_cost_tou') }} this month"
```

#### AFA Weird Zone Alert (when more usage saves money)
```yaml
alias: AFA Weird Zone Alert
trigger:
  - platform: state
    entity_id: binary_sensor.tnb_calculator_afa_weird_zone
    to: "on"
action:
  - service: notify.mobile_app
    data:
      message: >
        AFA weird zone detected! Using more electricity up to 600 kWh could actually 
        lower your bill. Current: {{ states('sensor.tnb_calculator_import_energy') }} kWh.
        Consider shifting some usage to this month.
```

#### AFA Value Zone Alert (cheap extra kWh)
```yaml
alias: AFA Value Zone Alert
trigger:
  - platform: state
    entity_id: binary_sensor.tnb_calculator_afa_value_zone
    to: "on"
action:
  - service: notify.mobile_app
    data:
      message: >
        AFA value opportunity! Extra kWh up to 600 kWh are very cheap 
        ({{ state_attr('sensor.tnb_calculator_afa_explanation', 'avg_marginal_rate_myr_per_kwh') }} MYR/kWh).
        Consider running heavy appliances this month.
```

#### Monthly Bill Summary
```yaml
alias: Monthly Electricity Summary
trigger:
  - platform: time
    at: "23:59:59"
condition:
  - condition: template
    value_template: "{{ now().day == 1 }}"
action:
  - service: notify.notify
    data:
      message: >
        Last month's electricity bill: RM{{ states('sensor.tnb_calculator_total_cost_tou') }}
        Total usage: {{ states('sensor.tnb_calculator_import_energy') }} kWh
        AFA zone: {{ states('sensor.tnb_calculator_afa_explanation') }}
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

- v4.4.4: Accurate daily peak/off-peak tracking (delta-based, boundary-aware splitting)
- v4.4.3: Separate ToU/non-ToU recommendation entities, Option B gating, stay_put zone, normalized attribute keys
- v4.4.2: Smarter AFA optimization with marginal rate analysis (practical targets, rate-based labels)
- v4.4.1: AFA optimization sensors + dashboard + automation examples
- v4.4.0b2: AFA explanation state cleanup, dashboard section, and automation examples [beta]
- v4.4.0b1: AFA optimization sensors (ideal import, savings, weird/value zones, human-readable explanation) [beta]
- v4.3.5: State-only energy entity support in config flow (fallback when entity registry entry is missing)
- v4.3.4: Weekly AFA-only and full-tariff auto-fetch improvements, configurable AFA API URL entity
- v4.3.2: Dynamic full-tariff loading from scraper `/complete`, auto-fetch switch, and MYR currency standardisation
- v4.1.1: Dynamic AFA rate management, external scraper support, and automation blueprint for automatic AFA updates
- v4.0.0: Configuration & calibration overhaul, billing start day helpers
- v1.0.0: Initial release with non-ToU and ToU support
