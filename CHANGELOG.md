# Changelog

All notable changes to TNB Calculator will be documented in this file.

## [3.3.0] - 2025-10-01 (BETA)

### Fixed
- **Holiday Compliance**: Fixed holiday detection to match TNB's official 15-holiday list exactly
  - ✅ Added New Year's Day (Jan 1) - TNB official holiday that Calendarific was missing
  - ✅ Removed Hari Raya Haji Day 2 - TNB only recognizes 1 day (not 2)
  - ✅ Result: Exactly 15 holidays matching TNB's tariff schedule
  - Dynamic Islamic dates still fetched from Calendarific API annually

**Note**: This is a beta release. Stable v3.2.1 will be released after testing.

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
