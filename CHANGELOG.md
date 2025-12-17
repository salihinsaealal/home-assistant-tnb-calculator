# Changelog

All notable changes to TNB Calculator will be documented in this file.

## [4.4.2] - 2025-12-17

### Changed
- **AFA Optimization: Marginal Rate Approach**
  - `ideal_import_kwh` now recommends a **practical target** (550–600 kWh range) based on lowest marginal cost.
  - Target is always **>= current import** — no more impractical "0 kWh ideal" suggestions.
  - Search uses 5 kWh steps for efficiency (11 candidates max).

### Added
- **Rate-Based Labels** for intuitive decision making:
  - `saves_money` — Using more reduces your bill (AFA weird zone).
  - `super_value` — Extra kWh costs ≤25% of your average rate.
  - `value` — Extra kWh costs ≤60% of your average rate.
  - `normal` — Extra kWh costs around your average rate.
  - `expensive` — Extra kWh costs more than your average rate.

- **Rich Attributes on Optimization Sensors**
  - Both **ToU** and **non-ToU** metrics exposed via attributes.
  - New attributes: `avg_rate_now`, `avg_rate_target`, `marginal_rate_to_target`, `primary_label`, `primary_model`.
  - `afa_explanation` shows rate-based messaging with clear RM/kWh figures.

### Improved
- **Proportional ToU Distribution**: When simulating future kWh, delta is distributed proportionally to current peak/offpeak ratio.
- **Edge Case Handling**: Robust handling for import >= 600, import <= 0, and negative average rates (solar users).
- **Debug Logging**: Added debug-level logging for AFA optimization validation.

### Backward Compatible
- Existing sensors and automations continue to work unchanged.
- Binary sensors (`afa_weird_zone`, `afa_value_zone`) still function based on the new labels.

## [4.4.1] - 2025-12-13

### Added
- **AFA Optimization & Sweet-Spot Sensors**
  - `sensor.tnb_calculator_ideal_import_kwh` – ideal monthly import (gross kWh) that minimises total bill.
  - `sensor.tnb_calculator_savings_if_ideal_kwh` – potential MYR savings if usage moves towards ideal import.
  - `sensor.tnb_calculator_afa_optimization_savings` – compares current bill vs hypothetical 600 kWh bill.
  - `binary_sensor.tnb_calculator_afa_weird_zone` – ON when more usage towards 600 kWh actually lowers the bill.
  - `binary_sensor.tnb_calculator_afa_value_zone` – ON when extra kWh up to 600 are very cheap per kWh (good value).
  - `sensor.tnb_calculator_afa_explanation` – short zone state with full explanation in attributes.

### Improved
- Updated the prebuilt dashboard with an **AFA Optimization** section.
- README updated with automation examples and cleaner release notes formatting.

## [4.4.0b2] - 2025-12-11 (Beta)

### Improved
- **AFA Explanation Sensor UX**
  - Sensor state now shows a short zone label (`normal`, `weird`, `value`, `above_threshold`).
  - Full human-readable explanation moved into an `explanation` attribute.
  - Keeps the device sensor list clean while retaining detailed guidance for dashboards.

- **Dashboard: AFA Optimization Section**
  - Added a dedicated card in `dashboards/tnb_calculator_dashboard.yaml` for:
    - `sensor.tnb_calculator_ideal_import_kwh`
    - `sensor.tnb_calculator_savings_if_ideal_kwh`
    - `sensor.tnb_calculator_afa_optimization_savings`
    - `sensor.tnb_calculator_afa_explanation`
    - `binary_sensor.tnb_calculator_afa_weird_zone`
    - `binary_sensor.tnb_calculator_afa_value_zone`

- **Documentation & Automations**
  - README now documents the AFA optimization sensors and adds example automations for:
    - High bill alert
    - AFA weird zone alert
    - AFA value zone alert
    - Monthly summary including AFA zone.

## [4.4.0b1] - 2025-12-11 (Beta)

### Added
- **AFA Optimization & Sweet-Spot Sensors**
  - `sensor.tnb_calculator_ideal_import_kwh` – ideal monthly import (gross kWh) that minimises total bill.
  - `sensor.tnb_calculator_savings_if_ideal_kwh` – potential MYR savings if usage moves towards ideal import.
  - `sensor.tnb_calculator_afa_optimization_savings` – compares current bill vs hypothetical 600 kWh bill.
  - `binary_sensor.tnb_calculator_afa_weird_zone` – ON when more usage towards 600 kWh actually lowers the bill.
  - `binary_sensor.tnb_calculator_afa_value_zone` – ON when extra kWh up to 600 are very cheap per kWh (good value).
  - `sensor.tnb_calculator_afa_explanation` – human-readable explanation of the current AFA situation (normal/weird/value/above 600 kWh).

### Notes
- All new sensors are **read-only optimizations** based on existing monthly import/export and tariff data.
- They do not alter calculations for existing sensors; they only provide guidance for optimising usage around the 600 kWh AFA threshold.

## [4.0.1] - 2025-10-09

### Fixed
- **Service UI Default**: `adjust_import_energy_values` distribution now correctly defaults to "Auto" instead of "Proportional"

---

## [4.0.0] - 2025-10-09

### 🎉 Major Release - Configuration & Calibration Overhaul

This major version brings significant improvements to configuration management, calibration workflows, and billing cycle customization.

### Added
- **🔄 Dynamic Configuration Updates**: API key and billing start day changes now apply immediately without requiring integration deletion/re-add
  - Options flow properly merges with config entry data
  - Coordinator refreshes configuration on every update cycle
  - ToU mode activates instantly when API key is added via reconfigure
- **📅 Billing Start Day Status Sensor**: New `sensor.tnb_calculator_billing_start_day_status` displays active billing day with pending changes
  - Shows format: `"1 (→ 4 next cycle)"` when a change is staged
  - Exposes `billing_start_day_active`, `billing_start_day_configured`, and `billing_start_day_pending` attributes
  - Pending changes activate at the next billing cycle boundary
- **⚡ Improved Calibration Services**: Enhanced user experience for energy value adjustments
  - Distribution options reordered: Auto → Peak Only → Off-Peak Only → Proportional → Manual
  - Default distribution changed to "Auto" (detects based on current time)
  - Simplified service descriptions with clear delay information
  - All services now use `async_refresh()` for consistency

### Improved
- **🔧 Service Registration**: Fixed `async_request_refresh()` → `async_refresh()` in reset_storage service
- **📊 Calibration Workflow**: 
  - Values save to storage immediately
  - Sensor display updates on next coordinator refresh (~5 minutes)
  - Users informed: "Values update immediately in storage but sensor display has a delay. For instant sensor refresh, reload the integration."
- **🎯 Configuration Persistence**: Billing start day and API key changes persist across integration reloads
- **📝 Service UI Polish**: 
  - Cleaner field descriptions
  - "Proportional" now labeled as "split by current peak/off-peak ratio"
  - Removed verbose examples from descriptions

### Fixed
- **🐛 Service UI Not Showing**: Corrected method call preventing service registration from completing
- **🔄 ToU Mode Not Updating**: Fixed coordinator not detecting API key additions after initial setup
- **📅 Billing Day Visibility**: Pending billing start day changes now surface in both number entity attributes and dedicated status sensor

### Technical Changes
- Merged `entry.data` and `entry.options` in `async_setup_entry()` for unified configuration
- Added `async_reload_entry()` update listener for automatic reload on options changes
- Coordinator now updates `_import_entity`, `_export_entity`, `_api_key`, and `_billing_start_day` on every refresh
- Billing number entity displays active day while exposing configured/pending values in attributes
- New `TNBBillingStartDayStatusSensor` class for formatted billing day status display

### Breaking Changes
- None - All changes are backward compatible

---

## [3.7.3b1] - 2025-10-07 (Beta)

### Added
- **Prediction Method Sensor**: New diagnostic sensor showing which prediction algorithm is active (Cost Trend or Hybrid).
- **Configuration Scenario Sensor**: New diagnostic sensor displaying setup type (Import Only, Import+Export, ToU, Non-ToU).

### Improved
- **Prediction Accuracy**: Switched from kWh projection to direct cost averaging for more realistic monthly forecasts.
  - Formula: `(current_cost / days_elapsed) × days_in_month ± 5%`
  - Example: RM 3.00 over 4 days = RM 0.75/day × 30 = RM 22.50 ± RM 1.13
  - Eliminates inflated predictions on early days of the month.
- **Prediction Attributes**: Added `prediction_tolerance`, `prediction_range_min`, and `prediction_range_max` to show confidence bounds.

### Fixed
- **Optional Config Inputs**: Config flow now properly accepts blank export sensors and Calendarific API keys without validation errors.

## [3.7.2] - 2025-10-04

### Fixed
- Updated `hacs.json` metadata and version strings to align with HACS default-store requirements.

## [3.7.1] - 2025-10-03

### Fixed
- Restored `CONF_YEAR` constant to prevent setup failures on recent Home Assistant versions.

## [3.7.0] - 2025-10-03

### Added
- **Bubble Dashboard Template**: New `dashboards/tnb_calculator_dashboard.yaml` featuring Bubble Card quick metrics and ApexCharts graphs.

### Improved
- **Documentation**: README and info cards now explain how to import the dashboard as a dedicated view or merge it into existing dashboards.

## [3.6.2] - 2025-10-03

### Added
- **Reset Service**: `tnb_calculator.reset_storage` clears cached totals, historical months, and holidays after typing `RESET` for confirmation.

## [3.6.1] - 2025-10-03

### Added
- **Holiday Diagnostics**: `sensor.tnb_cached_holidays_count` now exposes `cached_holidays` and `cached_holidays_last_fetch` attributes listing every cached date for quick cross-checking.

## [3.6.0] - 2025-10-03

### Added
- **Validation Status Sensor**: New diagnostic sensor reporting configuration issues detected at runtime.

### Improved
- **Config Flow Guardrails**: Import/export entities now validated for device class, state class, units, and numeric state inputs before setup.
- **Calendarific API Checks**: Setup and options flows provide specific errors for invalid keys, rate limits, timeouts, or connectivity issues.
- **Runtime Diagnostics**: Coordinator logs validation warnings and exposes them via the `validation_status` sensor.

### Fixed
- **Graceful Sensor Handling**: Coordinator no longer silently zeroes bad readings— issues are flagged for visibility.

## [3.5.1] - 2025-10-03

### Fixed
- **Diagnostic Sensors**: Resolved Home Assistant entity registry error caused by using string `entity_category` values. Diagnostic sensors are now registered using `EntityCategory.DIAGNOSTIC` and appear correctly after reload.
- **Version Metadata**: Bumped integration and device `sw_version` to 3.5.1 for accurate reporting.

## [3.4.2] - 2025-10-03

### Fixed
- **Critical Bug**: Fixed "cannot access local variable 'monthly_import'" error
  - Moved monthly variable definitions BEFORE daily calculations that use them
  - Daily tracking now works correctly without crashes
  - Error occurred when daily data tried to use monthly_import before it was defined

## [3.4.1] - 2025-10-03

### Fixed
- **Manifest Validation**: Removed invalid `homeassistant`, `ssdp`, and `zeroconf` keys from manifest.json
  - These keys are not allowed in HACS custom integrations
  - Fixes Hassfest validation errors

## [3.4.0] - 2025-10-03

### Added
- **📅 Daily Usage Tracking**: Track today's consumption and costs
  - `sensor.tnb_today_import_kwh` - Today's total import
  - `sensor.tnb_today_export_kwh` - Today's total export  
  - `sensor.tnb_today_net_kwh` - Today's net usage
  - `sensor.tnb_today_cost_tou` - Today's cost (ToU)
  - `sensor.tnb_today_cost_non_tou` - Today's cost (Non-ToU)
  - `sensor.tnb_today_import_peak_kwh` - Today's peak import (diagnostic)
  - `sensor.tnb_today_import_offpeak_kwh` - Today's off-peak import (diagnostic)
  
- **🤖 Automation Helpers**: Binary sensors for smart automations
  - `sensor.tnb_peak_period` - Currently in peak hours (on/off)
  - `sensor.tnb_high_usage_alert` - Approaching 600 kWh tier (on/off)
  - `sensor.tnb_holiday_today` - Today is a public holiday (on/off)
  
- **📊 Status Sensors**:
  - `sensor.tnb_tier_status` - Current usage tier ("Below 600 kWh", "600-1500 kWh", "Above 1500 kWh")

### Improved
- **Automatic Daily Reset**: Daily counters reset at midnight automatically
- **Smart Peak/Off-Peak Estimation**: Daily peak/off-peak split estimated from monthly patterns
- **Persistent Daily Data**: Today's usage survives restarts

### Technical
- Added `_daily_data` storage structure
- Added `_day_changed()` and `_create_day_bucket()` methods
- Daily data stored alongside monthly data in same storage file
- Backward compatible with v3.3.0 storage format

## [3.3.0] - 2025-10-01 ⭐ **STABLE RELEASE**

### Added
- **🔮 Hybrid Cost Prediction System**: Smart end-of-month bill prediction (from v3.2.0)
  - Method 2 (Current Trend) + Method 3 (Historical Average)
  - 8 new prediction sensors with automatic learning
  - Tier-aware calculations (600 kWh, 1500 kWh thresholds)
  - Confidence indicators (High/Medium/Low)

### Fixed
- **Holiday Compliance**: Fixed holiday detection to match TNB's official 15-holiday list exactly
  - ✅ Added New Year's Day (Jan 1) - TNB official holiday that Calendarific was missing
  - ✅ Removed Hari Raya Haji Day 2 - TNB only recognizes 1 day (not 2)
  - ✅ Result: Exactly 15 holidays matching TNB's tariff schedule
  - Dynamic Islamic dates still fetched from Calendarific API annually

### Technical
- Historical data storage (last 12 months)
- Enhanced month-end processing
- Automatic data migration from v3.1.x

## [3.2.0] - 2025-10-01

### Added
- **🔮 Hybrid Cost Prediction System**: Smart end-of-month bill prediction
  - **Method 2 (Current Trend)**: Projects based on this month's usage pattern with tier-aware calculations
  - **Method 3 (Historical Average)**: Learns from past 3 months of actual usage
  - **Hybrid Intelligence**: Automatically weights predictions based on data availability
    - Early month (days 1-7): 70% history, 30% trend
    - Mid month (days 8-20): 60% trend, 40% history  
    - Late month (days 21+): 80% trend, 20% history
  - **Prediction Confidence**: "High" (3+ months data), "Medium" (1-2 months), "Low" (no history)
- **New Prediction Sensors** (8 total):
  - `sensor.tnb_predicted_monthly_cost` - Smart hybrid prediction (main)
  - `sensor.tnb_predicted_monthly_kwh` - Projected total consumption
  - `sensor.tnb_predicted_from_trend` - Prediction from current month pattern
  - `sensor.tnb_predicted_from_history` - Prediction from historical average
  - `sensor.tnb_prediction_confidence` - Confidence level indicator
  - `sensor.tnb_daily_average_cost` - Average daily cost
  - `sensor.tnb_daily_average_kwh` - Average daily consumption
  - `sensor.tnb_days_remaining` - Days until monthly reset
- **Historical Data Storage**: Automatically saves last 12 months of usage data
  - Stores: total kWh, cost, peak/offpeak split, export
  - Saved at end of each month before reset
  - Used for trend analysis and improved predictions

### Improved
- **Smarter Predictions**: Accounts for TNB tariff tier changes (600 kWh, 1500 kWh thresholds)
- **Automatic Learning**: Gets more accurate each month as historical data builds up
- **Peak/Off-Peak Aware**: Maintains your actual usage patterns in projections

### Technical
- Added `calendar` module import for month calculations
- Added `_historical_months` storage dictionary
- Added `_last_calculated_cost` tracking for historical data
- Enhanced `_month_changed()` to save historical data before reset
- New `_calculate_predictions()` method with hybrid algorithm
- Storage format v3: includes `historical_months` field

## [3.1.4] - 2025-10-01

### Summary
This release finalizes all critical fixes and improvements from v3.1.0-3.1.3.
All ToU calculation bugs fixed, data persistence improved, and migration logic enhanced.

### Verified
- ✅ ToU calculation matches reference Excel template exactly
- ✅ Non-ToU calculation matches reference template exactly
- ✅ Storage migration works correctly from v3.0.x to v3.1.x
- ✅ Data persists across restarts, updates, and delete/re-add
- ✅ Holiday caching with daily refresh working properly
- ✅ No ConfigEntryNotReady warnings

## [3.1.3] - 2025-10-01

### Fixed
- **Storage Migration**: Fixed migration from v3.0.x to v3.1.x storage format
  - Old format stored monthly data directly, new format wraps it with holiday cache
  - Migration now detects and converts old format automatically
  - Preserves all existing monthly data during upgrade
- **KeyError on 'month'**: Fixed crash when loading invalid or empty storage data
  - Validates monthly_data has required 'month' and 'year' keys before loading
  - Creates new bucket if storage data is invalid

### Technical
- Enhanced `_load_monthly_data()` to handle both old and new storage formats
- Added validation checks before setting `_monthly_data`

## [3.1.2] - 2025-10-01

### Fixed
- **ConfigEntryNotReady Exception**: Moved entity validation to `__init__.py` before platform forwarding
  - Prevents warning: "raises exception ConfigEntryNotReady in forwarded platform sensor"
  - Proper retry mechanism when entities are not yet available
  - Cleaner error handling and logging

### Technical
- Entity validation now happens in `async_setup_entry` in `__init__.py`
- Removed redundant exception handling from `sensor.py`

## [3.1.0] - 2025-10-01

### Fixed
- **ToU Cost Calculation**: Fixed bug where ToU cost was incorrectly lower than non-ToU during peak hours
  - Export energy allocation now properly capped at actual export total
  - Prevents phantom export rebates when export_total is zero
- **Meter Reset Handling**: Enhanced delta calculation to properly handle daily/monthly meter resets

### Improved
- **Holiday Caching**: Implemented robust daily API refresh with persistent storage
  - Fetches entire year of holidays once per day (uses only ~3% of free API quota)
  - Holiday cache now persists across Home Assistant restarts
  - Graceful fallback to cached data if API is unavailable
- **Data Persistence**: Changed storage identifier to use import entity instead of entry_id
  - Data now survives integration delete/re-add operations
  - Automatic migration from old storage format for existing users
  - More reliable data preservation across configuration changes

### Technical
- Storage format updated to include holiday cache and fetch timestamp
- Added automatic migration logic for seamless upgrades
- Improved logging for holiday fetch operations and data migration

## [2.0.0] - 2024-09-30

### Major Changes
- **Simplified Configuration**: Now only requires import/export entities and optional Calendarific API key
- **Automatic ToU Detection**: ToU mode is automatically enabled when API key is provided
- **InternalPeak/Off-Peak Splitting**: Integration now handles peak/off-peak splitting internally based on TNB schedule and holidays
- **Enhanced Sensor Coverage**: Added 20+ detailed cost breakdown sensors for ToU mode

### Added
- Automatic peak/off-peak energy splitting based on TNB ToU schedule (2PM-10PM weekdays)
- Holiday-aware off-peak detection using Calendarific API
- Detailed cost breakdown sensors: generation charges, AFA, capacity, network, retailing, ICT, service tax, KWTBB
- NEM rebate sensors: peak, off-peak, capacity, network rebates
- Rate sensors showing current tariff rates for all components
- Insentif leveling rebate calculations
- HACS compliance badges and improved documentation

### Changed
- **BREAKING**: Removed separate ToU entity configuration requirements
- **BREAKING**: Removed manual ToU enable/disable option
- Simplified setup process to just import/export + optional API key
- Updated UI strings and configuration flow
- Enhanced error handling and validation

### Technical Improvements
- Refactored sensor architecture to support dynamic sensor creation
- Improved monthly reset logic with better delta calculations
- Enhanced holiday caching for better API efficiency
- Better handling of meter resets and edge cases
- Comprehensive cost calculation following TNB tariff template

### Migration Notes
- Existing installations will need reconfiguration due to breaking changes
- Remove old ToU-specific entity configurations
- Simply provide Calendarific API key to enable ToU mode

## [1.0.0] - 2024-09-25

### Added
- Initial release of TNB Calculator integration
- Support for both ToU and non-ToU tariff calculations
- Monthly billing cycle with automatic reset on 1st of each month
- Calendarific API integration for Malaysian holiday detection
- Comprehensive cost breakdown with multiple sensor entities
- Export energy credit calculations for solar users
- Configurable through Home Assistant UI
- HACS compatibility for easy installation

## [Unreleased]

### Planned
- Additional tariff support
- Cost prediction features
- Advanced reporting
