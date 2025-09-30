# Changelog

All notable changes to TNB Calculator will be documented in this file.

## [2.0.0] - 2024-09-30

### Major Changes
- **Simplified Configuration**: Now only requires import/export entities and optional Calendarific API key
- **Automatic ToU Detection**: ToU mode is automatically enabled when API key is provided
- **InternalPeak/Off-Peak Splitting**: Integration now handles peak/off-peak splitting internally based on TNB schedule and holidays
- **Enhanced Sensor Coverage**: Added 20+ detailed cost breakdown sensors for ToU mode

### Added
- Automatic peak/off-peak energy splitting based on TNB ToU schedule (8AM-10PM weekdays)
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
