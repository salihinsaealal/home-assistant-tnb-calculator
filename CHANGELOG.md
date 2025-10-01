# Changelog

All notable changes to TNB Calculator will be documented in this file.

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
