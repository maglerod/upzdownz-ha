# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-04-23

### Added
- Battery Alerts: new toggle — **Report all batteries** — when enabled, all battery devices are reported regardless of level. Each row now also includes a `below_threshold` boolean field so you can filter in UpzDownz widgets.

## [1.0.0] - 2026-04-23

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
