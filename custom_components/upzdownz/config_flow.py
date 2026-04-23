"""Config flow for UpzDownz integration."""
from __future__ import annotations

import logging
import traceback
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import UpzDownzApiClient, UpzDownzApiError, UpzDownzAuthError, UpzDownzRateLimitError
from .const import (
    CONF_API_KEY, CONF_SOURCES, CONF_SOURCE_ID, CONF_SOURCE_NAME, CONF_SOURCE_TYPE,
    CONF_ENTITIES, CONF_INTERVAL, CONF_THRESHOLD, CONF_DOMAINS_EXCLUDE,
    CONF_CALENDAR_ENTITIES, CONF_WEATHER_ENTITY, CONF_BATTERY_REPORT_ALL, CONF_LIGHTS_MODE,
    DEFAULT_BATTERY_THRESHOLD, DEFAULT_EXCLUDED_DOMAINS, DEFAULT_INTERVAL,
    DOMAIN, SOURCE_TYPE_SENSORS, SOURCE_TYPE_BATTERY, SOURCE_TYPE_UNAVAILABLE,
    SOURCE_TYPE_CALENDAR, SOURCE_TYPE_WEATHER, SOURCE_TYPE_LIGHTS, SOURCE_TYPE_CUSTOM,
    SOURCE_TYPE_LABELS, LIGHTS_MODE_PER_LIGHT, LIGHTS_MODE_SUMMARY,
    SCHEMA_TYPE_DECIMAL, SCHEMA_TYPE_STRING, SCHEMA_TYPE_BOOLEAN, SCHEMA_TYPE_INTEGER,
)

_LOGGER = logging.getLogger(__name__)

CONF_ENTITY_IDS = "entity_ids"

INTERVAL_OPTIONS = [
    {"value": "60",   "label": "1 minute"},
    {"value": "300",  "label": "5 minutes"},
    {"value": "900",  "label": "15 minutes"},
    {"value": "1800", "label": "30 minutes"},
    {"value": "3600", "label": "1 hour"},
]

# ── Fixed API schemas ─────────────────────────────────────────────────────────

BATTERY_API_SCHEMA = [
    {"name": "entity_id",       "type": SCHEMA_TYPE_STRING},
    {"name": "friendly_name",   "type": SCHEMA_TYPE_STRING},
    {"name": "battery_level",   "type": SCHEMA_TYPE_DECIMAL},
    {"name": "below_threshold", "type": SCHEMA_TYPE_BOOLEAN},
    {"name": "recorded_at",     "type": SCHEMA_TYPE_STRING},
]
UNAVAILABLE_API_SCHEMA = [
    {"name": "entity_id",     "type": SCHEMA_TYPE_STRING},
    {"name": "domain",        "type": SCHEMA_TYPE_STRING},
    {"name": "friendly_name", "type": SCHEMA_TYPE_STRING},
    {"name": "last_changed",  "type": SCHEMA_TYPE_STRING},
    {"name": "recorded_at",   "type": SCHEMA_TYPE_STRING},
]
CALENDAR_API_SCHEMA = [
    {"name": "calendar",    "type": SCHEMA_TYPE_STRING},
    {"name": "summary",     "type": SCHEMA_TYPE_STRING},
    {"name": "start",       "type": SCHEMA_TYPE_STRING},
    {"name": "end",         "type": SCHEMA_TYPE_STRING},
    {"name": "all_day",     "type": SCHEMA_TYPE_BOOLEAN},
    {"name": "recorded_at", "type": SCHEMA_TYPE_STRING},
]
WEATHER_API_SCHEMA = [
    {"name": "condition",     "type": SCHEMA_TYPE_STRING},
    {"name": "temperature",   "type": SCHEMA_TYPE_DECIMAL},
    {"name": "humidity",      "type": SCHEMA_TYPE_DECIMAL},
    {"name": "wind_speed",    "type": SCHEMA_TYPE_DECIMAL},
    {"name": "wind_bearing",  "type": SCHEMA_TYPE_DECIMAL},
    {"name": "pressure",      "type": SCHEMA_TYPE_DECIMAL},
    {"name": "feels_like",    "type": SCHEMA_TYPE_DECIMAL},
    {"name": "forecast",      "type": SCHEMA_TYPE_STRING},
    {"name": "recorded_at",   "type": SCHEMA_TYPE_STRING},
]
LIGHTS_PER_LIGHT_API_SCHEMA = [
    {"name": "entity_id",     "type": SCHEMA_TYPE_STRING},
    {"name": "friendly_name", "type": SCHEMA_TYPE_STRING},
    {"name": "state",         "type": SCHEMA_TYPE_STRING},
    {"name": "brightness",    "type": SCHEMA_TYPE_INTEGER},
    {"name": "area",          "type": SCHEMA_TYPE_STRING},
    {"name": "recorded_at",   "type": SCHEMA_TYPE_STRING},
]
LIGHTS_SUMMARY_API_SCHEMA = [
    {"name": "lights_on",    "type": SCHEMA_TYPE_INTEGER},
    {"name": "lights_total", "type": SCHEMA_TYPE_INTEGER},
    {"name": "recorded_at",  "type": SCHEMA_TYPE_STRING},
]
UNAVAILABLE_API_SCHEMA = [
    {"name": "entity_id",     "type": SCHEMA_TYPE_STRING},
    {"name": "friendly_name", "type": SCHEMA_TYPE_STRING},
    {"name": "domain",        "type": SCHEMA_TYPE_STRING},
    {"name": "state",         "type": SCHEMA_TYPE_STRING},
    {"name": "last_changed",  "type": SCHEMA_TYPE_STRING},
    {"name": "recorded_at",   "type": SCHEMA_TYPE_STRING},
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _entity_id_to_field_name(entity_id: str) -> str:
    parts = entity_id.split(".", 1)
    name = parts[1] if len(parts) == 2 else parts[0]
    return name.replace("-", "_").replace(" ", "_").lower()

def _parse_domain_list(raw: str) -> list[str]:
    return [d.strip() for d in raw.split(",") if d.strip()]

def _infer_api_schema(hass, entities: dict[str, str]) -> list[dict]:
    schema: list[dict] = [{"name": "recorded_at", "type": SCHEMA_TYPE_STRING}]
    for entity_id, field_name in entities.items():
        state = hass.states.get(entity_id)
        field_type = SCHEMA_TYPE_STRING
        if state:
            try:
                float(state.state)
                field_type = SCHEMA_TYPE_DECIMAL
            except (ValueError, TypeError):
                if state.state in ("true", "false", "on", "off"):
                    field_type = SCHEMA_TYPE_BOOLEAN
        schema.append({"name": field_name, "type": field_type})
    return schema

def _api_schema_for(source_type: str, source_cfg: dict, hass=None) -> list[dict]:
    if source_type == SOURCE_TYPE_BATTERY:     return BATTERY_API_SCHEMA
    if source_type == SOURCE_TYPE_UNAVAILABLE: return UNAVAILABLE_API_SCHEMA
    if source_type == SOURCE_TYPE_CALENDAR:    return CALENDAR_API_SCHEMA
    if source_type == SOURCE_TYPE_WEATHER:     return WEATHER_API_SCHEMA
    if source_type == SOURCE_TYPE_LIGHTS:
        mode = source_cfg.get(CONF_LIGHTS_MODE, LIGHTS_MODE_PER_LIGHT)
        return LIGHTS_SUMMARY_API_SCHEMA if mode == LIGHTS_MODE_SUMMARY else LIGHTS_PER_LIGHT_API_SCHEMA
    entities = source_cfg.get(CONF_ENTITIES, {})
    if hass:
        return _infer_api_schema(hass, entities)
    return [{"name": "recorded_at", "type": SCHEMA_TYPE_STRING}] + [
        {"name": fn, "type": SCHEMA_TYPE_DECIMAL} for fn in entities.values()
    ]

# ── Form builders ─────────────────────────────────────────────────────────────

def _name_interval_fields(default_name="", default_interval=DEFAULT_INTERVAL):
    return {
        vol.Required(CONF_SOURCE_NAME, default=default_name):
            selector.selector({"text": {"type": "text"}}),
        vol.Required(CONF_INTERVAL, default=default_interval):
            selector.selector({"select": {"options": INTERVAL_OPTIONS, "mode": "dropdown"}}),
    }

def _battery_form():
    return vol.Schema({
        **_name_interval_fields("Battery Alerts", 1800),
        vol.Required(CONF_BATTERY_REPORT_ALL, default=False):
            selector.selector({"boolean": {}}),
        vol.Required(CONF_THRESHOLD, default=DEFAULT_BATTERY_THRESHOLD):
            selector.selector({"number": {"min": 5, "max": 50, "step": 1, "unit_of_measurement": "%", "mode": "slider"}}),
    })

def _unavailable_form():
    return vol.Schema({
        **_name_interval_fields("Unavailable Entities", 900),
        vol.Optional(CONF_DOMAINS_EXCLUDE, default=", ".join(DEFAULT_EXCLUDED_DOMAINS)):
            selector.selector({"text": {"type": "text"}}),
    })

def _calendar_form():
    return vol.Schema({
        **_name_interval_fields("Calendar Events", 3600),
        vol.Required(CONF_CALENDAR_ENTITIES):
            selector.selector({"entity": {"domain": "calendar", "multiple": True}}),
    })

def _weather_form():
    return vol.Schema({
        **_name_interval_fields("Weather", 3600),
        vol.Required(CONF_WEATHER_ENTITY):
            selector.selector({"entity": {"domain": "weather"}}),
    })

def _entity_pick_form():
    return vol.Schema({
        **_name_interval_fields(),
        vol.Required(CONF_ENTITY_IDS):
            selector.selector({"entity": {"multiple": True}}),
    })

def _field_names_form(entity_ids: list[str]):
    return vol.Schema({
        vol.Required(f"field_{eid}", default=_entity_id_to_field_name(eid)):
            selector.selector({"text": {"type": "text"}})
        for eid in entity_ids
    })

def _lights_form():
    return vol.Schema({
        **_name_interval_fields("Light Status", 300),
        vol.Required(CONF_LIGHTS_MODE, default=LIGHTS_MODE_PER_LIGHT):
            selector.selector({
                "select": {
                    "options": [
                        {"value": LIGHTS_MODE_PER_LIGHT, "label": "Per light — one row per lamp (supports room grouping)"},
                        {"value": LIGHTS_MODE_SUMMARY,   "label": "Summary only — total lights on vs total"},
                    ],
                    "mode": "list",
                }
            }),
    })

FORM_FOR_TYPE = {
    SOURCE_TYPE_BATTERY:     _battery_form,
    SOURCE_TYPE_UNAVAILABLE: _unavailable_form,
    SOURCE_TYPE_CALENDAR:    _calendar_form,
    SOURCE_TYPE_WEATHER:     _weather_form,
    SOURCE_TYPE_LIGHTS:      _lights_form,
}

# ── Config flow ───────────────────────────────────────────────────────────────

class UpzDownzConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._api_key = ""
        self._client = None
        self._pending_sources: list[dict] = []
        self._adding_type: str | None = None
        self._pending_name = ""
        self._pending_interval = DEFAULT_INTERVAL
        self._pending_entity_ids: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        from .options_flow import UpzDownzOptionsFlow
        return UpzDownzOptionsFlow(config_entry)

    # ── Step: user (API key) ──────────────────────────────────────────────────

    async def async_step_user(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz: async_step_user called, user_input=%s", user_input is not None)
        errors = {}
        try:
            if user_input is not None:
                api_key = user_input[CONF_API_KEY].strip()
                session = async_get_clientsession(self.hass)
                client = UpzDownzApiClient(api_key, session)
                try:
                    if await client.validate_key():
                        self._api_key = api_key
                        self._client = client
                        _LOGGER.debug("UpzDownz: API key valid, moving to pick_type")
                        return await self.async_step_pick_type()
                    errors["base"] = "invalid_auth"
                except UpzDownzApiError as err:
                    _LOGGER.error("UpzDownz: connect error in step_user: %s", err)
                    errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.error("UpzDownz: unexpected exception in async_step_user:\n%s", traceback.format_exc())
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): selector.selector({"text": {"type": "password"}})
            }),
            errors=errors,
        )

    # ── Step: pick_type ───────────────────────────────────────────────────────

    async def async_step_pick_type(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz: async_step_pick_type called, user_input=%s", user_input)
        errors = {}
        try:
            if user_input is not None:
                choice = user_input.get("action")
                _LOGGER.debug("UpzDownz: pick_type choice=%s", choice)
                if choice == "finish":
                    _LOGGER.debug("UpzDownz: finishing, sources=%s", self._pending_sources)
                    return self.async_create_entry(
                        title="UpzDownz",
                        data={CONF_API_KEY: self._api_key, CONF_SOURCES: self._pending_sources},
                    )
                if choice in SOURCE_TYPE_LABELS:
                    self._adding_type = choice
                    if choice in (SOURCE_TYPE_SENSORS, SOURCE_TYPE_CUSTOM):
                        return await self.async_step_pick_entities()
                    return await self.async_step_configure_source()
        except Exception:
            _LOGGER.error("UpzDownz: unexpected exception in async_step_pick_type:\n%s", traceback.format_exc())
            errors["base"] = "unknown"

        options = {t: f"Add: {label}" for t, label in SOURCE_TYPE_LABELS.items()}
        options["finish"] = "Done — save and finish"
        added = ", ".join(s[CONF_SOURCE_NAME] for s in self._pending_sources) or "None yet"

        return self.async_show_form(
            step_id="pick_type",
            data_schema=vol.Schema({
                vol.Required("action"): selector.selector({
                    "select": {"options": [{"value": k, "label": v} for k, v in options.items()], "mode": "list"}
                })
            }),
            errors=errors,
            description_placeholders={"pending_sources": added},
        )

    # ── Step: configure_source ────────────────────────────────────────────────

    async def async_step_configure_source(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz: async_step_configure_source called, type=%s, user_input=%s", self._adding_type, user_input is not None)
        errors = {}
        threshold_val = DEFAULT_BATTERY_THRESHOLD
        try:
            if user_input is not None:
                threshold_val = user_input.get(CONF_THRESHOLD, DEFAULT_BATTERY_THRESHOLD)
                source_cfg: dict[str, Any] = {
                    CONF_SOURCE_TYPE: self._adding_type,
                    CONF_SOURCE_NAME: user_input[CONF_SOURCE_NAME],
                    CONF_INTERVAL: int(user_input.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
                }
                if self._adding_type == SOURCE_TYPE_BATTERY:
                    source_cfg[CONF_THRESHOLD] = threshold_val
                    source_cfg[CONF_BATTERY_REPORT_ALL] = user_input.get(CONF_BATTERY_REPORT_ALL, False)
                elif self._adding_type == SOURCE_TYPE_UNAVAILABLE:
                    raw = user_input.get(CONF_DOMAINS_EXCLUDE, "")
                    source_cfg[CONF_DOMAINS_EXCLUDE] = _parse_domain_list(raw) or DEFAULT_EXCLUDED_DOMAINS
                elif self._adding_type == SOURCE_TYPE_CALENDAR:
                    source_cfg[CONF_CALENDAR_ENTITIES] = user_input.get(CONF_CALENDAR_ENTITIES, [])
                elif self._adding_type == SOURCE_TYPE_WEATHER:
                    source_cfg[CONF_WEATHER_ENTITY] = user_input.get(CONF_WEATHER_ENTITY, "")
                elif self._adding_type == SOURCE_TYPE_LIGHTS:
                    source_cfg[CONF_LIGHTS_MODE] = user_input.get(CONF_LIGHTS_MODE, LIGHTS_MODE_PER_LIGHT)
                try:
                    _LOGGER.debug("UpzDownz: creating source '%s' type=%s", source_cfg[CONF_SOURCE_NAME], self._adding_type)
                    created = await self._client.create_source(
                        source_cfg[CONF_SOURCE_NAME],
                        _api_schema_for(self._adding_type, source_cfg, self.hass)
                    )
                    source_cfg[CONF_SOURCE_ID] = created["id"]
                    self._pending_sources.append(source_cfg)
                    self._adding_type = None
                    return await self.async_step_pick_type()
                except UpzDownzRateLimitError:
                    errors["base"] = "row_limit"
                except UpzDownzAuthError:
                    errors["base"] = "invalid_auth"
                except UpzDownzApiError as err:
                    _LOGGER.error("UpzDownz: create_source API error: %s", err)
                    errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.error("UpzDownz: unexpected exception in async_step_configure_source:\n%s", traceback.format_exc())
            errors["base"] = "unknown"

        form_fn = FORM_FOR_TYPE.get(self._adding_type, _battery_form)
        return self.async_show_form(
            step_id="configure_source",
            data_schema=form_fn(),
            errors=errors,
            description_placeholders={
                "source_type": SOURCE_TYPE_LABELS.get(self._adding_type, self._adding_type or ""),
                "threshold": str(threshold_val),
            },
        )

    # ── Step: pick_entities ───────────────────────────────────────────────────

    async def async_step_pick_entities(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz: async_step_pick_entities called, user_input=%s", user_input is not None)
        errors = {}
        try:
            if user_input is not None:
                entity_ids = user_input.get(CONF_ENTITY_IDS, [])
                if not entity_ids:
                    errors[CONF_ENTITY_IDS] = "no_entities_selected"
                else:
                    self._pending_name = user_input[CONF_SOURCE_NAME]
                    self._pending_interval = int(user_input.get(CONF_INTERVAL, DEFAULT_INTERVAL))
                    self._pending_entity_ids = entity_ids
                    return await self.async_step_field_names()
        except Exception:
            _LOGGER.error("UpzDownz: unexpected exception in async_step_pick_entities:\n%s", traceback.format_exc())
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="pick_entities",
            data_schema=_entity_pick_form(),
            errors=errors,
            description_placeholders={"source_type": SOURCE_TYPE_LABELS.get(self._adding_type, "")},
        )

    # ── Step: field_names ─────────────────────────────────────────────────────

    async def async_step_field_names(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz: async_step_field_names called, entities=%s", self._pending_entity_ids)
        errors = {}
        entity_ids = self._pending_entity_ids
        try:
            if user_input is not None:
                entities = {
                    eid: user_input.get(f"field_{eid}", _entity_id_to_field_name(eid)).strip().replace(" ", "_").lower()
                    for eid in entity_ids
                }
                try:
                    created = await self._client.create_source(
                        self._pending_name,
                        _infer_api_schema(self.hass, entities)
                    )
                    source_cfg = {
                        CONF_SOURCE_TYPE: self._adding_type,
                        CONF_SOURCE_NAME: self._pending_name,
                        CONF_INTERVAL: self._pending_interval,
                        CONF_ENTITIES: entities,
                        CONF_SOURCE_ID: created["id"],
                    }
                    self._pending_sources.append(source_cfg)
                    self._adding_type = None
                    return await self.async_step_pick_type()
                except UpzDownzRateLimitError:
                    errors["base"] = "row_limit"
                except UpzDownzAuthError:
                    errors["base"] = "invalid_auth"
                except UpzDownzApiError as err:
                    _LOGGER.error("UpzDownz: create_source API error: %s", err)
                    errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.error("UpzDownz: unexpected exception in async_step_field_names:\n%s", traceback.format_exc())
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="field_names",
            data_schema=_field_names_form(entity_ids),
            errors=errors,
            description_placeholders={
                "source_name": self._pending_name,
                "entity_count": str(len(entity_ids)),
            },
        )
