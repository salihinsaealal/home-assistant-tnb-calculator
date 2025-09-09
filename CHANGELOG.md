# Changelog

All notable changes to TNB Calculator will be documented in this file.

## [1.0.0] - 2024-09-XX

### Added
- Initial release of TNB Calculator integration
- Support for non-ToU electricity tariff calculations
- Support for ToU (Time of Use) tariff with holiday detection
- Monthly billing cycle with automatic reset on 1st of each month
- Import and export energy tracking for solar users
- Calendarific API integration for Malaysian holiday detection
- Multiple sensor entities for detailed cost breakdown
- HACS integration support

### Features
- Real-time TNB cost calculation using official Malaysian rates
- Automatic tier calculation (first 600 kWh vs excess)
- Service tax and development charge calculations
- Export credit calculations for net metering
- Holiday detection for ToU off-peak rates

### Configuration
- Easy setup wizard in Home Assistant
- Entity selection from existing sensors
- Optional ToU configuration with API key validation
- Automatic sensor discovery

## [Unreleased]

### Planned
- Additional tariff support
- Historical data storage
- Cost prediction features
- Advanced reporting
