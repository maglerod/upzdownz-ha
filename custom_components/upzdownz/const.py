"""Constants for the UpzDownz integration."""

DOMAIN = "upzdownz"

API_BASE_URL = "https://ujpgoljgvddzlwqepcou.supabase.co/functions/v1/metric-ingest"

CONF_API_KEY = "api_key"
CONF_SOURCES = "sources"
CONF_SOURCE_ID = "source_id"
CONF_SOURCE_NAME = "source_name"
CONF_SOURCE_TYPE = "source_type"
CONF_ENTITIES = "entities"
CONF_INTERVAL = "interval"
CONF_THRESHOLD = "threshold"
CONF_DOMAINS_INCLUDE = "domains_include"
CONF_DOMAINS_EXCLUDE = "domains_exclude"
CONF_CALENDAR_ENTITIES = "calendar_entities"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_FIELD_MAPPINGS = "field_mappings"
CONF_LIGHTS_MODE = "lights_mode"
CONF_BATTERY_REPORT_ALL = "battery_report_all"

# Source types
SOURCE_TYPE_SENSORS     = "sensors"
SOURCE_TYPE_BATTERY     = "battery"
SOURCE_TYPE_UNAVAILABLE = "unavailable"
SOURCE_TYPE_CALENDAR    = "calendar"
SOURCE_TYPE_WEATHER     = "weather"
SOURCE_TYPE_LIGHTS      = "lights"
SOURCE_TYPE_CUSTOM      = "custom"

SOURCE_TYPE_LABELS = {
    SOURCE_TYPE_SENSORS:     "Sensors (selected entities)",
    SOURCE_TYPE_BATTERY:     "Battery Alerts (automatic)",
    SOURCE_TYPE_UNAVAILABLE: "Unavailable Entities (automatic)",
    SOURCE_TYPE_CALENDAR:    "Calendar Events",
    SOURCE_TYPE_WEATHER:     "Weather",
    SOURCE_TYPE_LIGHTS:      "Light Status (automatic)",
    SOURCE_TYPE_CUSTOM:      "Custom Data Source",
}

# Lights collection modes
LIGHTS_MODE_PER_LIGHT = "per_light"
LIGHTS_MODE_SUMMARY   = "summary"

# Default intervals in seconds
INTERVAL_OPTIONS = {
    60:   "1 minute",
    300:  "5 minutes",
    900:  "15 minutes",
    1800: "30 minutes",
    3600: "1 hour",
}
DEFAULT_INTERVAL = 300

# Battery threshold
DEFAULT_BATTERY_THRESHOLD = 20

# Domains excluded from "unavailable" source by default
DEFAULT_EXCLUDED_DOMAINS = [
    "group", "scene", "automation", "script", "zone",
    "input_boolean", "input_number", "input_select", "input_text",
]

# Schema field types
SCHEMA_TYPE_STRING  = "string"
SCHEMA_TYPE_DECIMAL = "decimal"
SCHEMA_TYPE_INTEGER = "integer"
SCHEMA_TYPE_BOOLEAN = "boolean"

# Status values
STATUS_OK      = "ok"
STATUS_ERROR   = "error"
STATUS_NO_DATA = "no_data"

# Sensor attributes
ATTR_LAST_SYNC   = "last_sync"
ATTR_ROWS_SENT   = "rows_sent"
ATTR_SOURCE_ID   = "source_id"
ATTR_SOURCE_TYPE = "source_type"

# HA version requirement for weather/calendar services
HA_MIN_VERSION_WEATHER = "2023.9"
