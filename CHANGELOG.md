# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-04-23

### Added
- Initial release
- Config flow with API key validation
- Six data source types: Sensors, Battery Alerts, Unavailable Entities, Calendar Events, Weather, Custom
- Searchable entity picker with automatic field name suggestions
- Configurable sync intervals (1 minute to 1 hour)
- Diagnostic sensor per data source showing sync status, last sync timestamp and total rows sent
- Persistent notifications in Home Assistant for authentication errors, row limit alerts and connection failures
- Options flow for adding and removing data sources without reinstalling
- Full error handling — integration never blocks Home Assistant from loading
