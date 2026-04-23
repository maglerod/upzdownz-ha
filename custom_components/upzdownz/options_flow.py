"""Options flow for UpzDownz."""
from __future__ import annotations

import logging
import traceback
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .api import UpzDownzApiClient, UpzDownzApiError, UpzDownzAuthError, UpzDownzRateLimitError
from .config_flow import (
    CONF_ENTITY_IDS, FORM_FOR_TYPE,
    _entity_id_to_field_name, _parse_domain_list, _infer_api_schema, _api_schema_for,
    _entity_pick_form, _field_names_form,
)
from .const import (
    CONF_API_KEY, CONF_SOURCES, CONF_SOURCE_ID, CONF_SOURCE_NAME, CONF_SOURCE_TYPE,
    CONF_ENTITIES, CONF_INTERVAL, CONF_THRESHOLD, CONF_DOMAINS_EXCLUDE,
    CONF_CALENDAR_ENTITIES, CONF_WEATHER_ENTITY, CONF_BATTERY_REPORT_ALL,
    DEFAULT_BATTERY_THRESHOLD, DEFAULT_EXCLUDED_DOMAINS, DEFAULT_INTERVAL,
    SOURCE_TYPE_SENSORS, SOURCE_TYPE_BATTERY, SOURCE_TYPE_UNAVAILABLE,
    SOURCE_TYPE_CALENDAR, SOURCE_TYPE_WEATHER, SOURCE_TYPE_CUSTOM, SOURCE_TYPE_LABELS,
)

_LOGGER = logging.getLogger(__name__)


class UpzDownzOptionsFlow(OptionsFlow):

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry
        self._sources: list[dict] = list(
            config_entry.options.get(CONF_SOURCES)
            or config_entry.data.get(CONF_SOURCES)
            or []
        )
        self._adding_type: str | None = None
        self._client: UpzDownzApiClient | None = None
        self._pending_name = ""
        self._pending_interval = DEFAULT_INTERVAL
        self._pending_entity_ids: list[str] = []

    async def async_step_init(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz options: async_step_init")
        try:
            api_key = self.config_entry.data[CONF_API_KEY]
            session = async_get_clientsession(self.hass)
            self._client = UpzDownzApiClient(api_key, session)
            _LOGGER.debug("UpzDownz options: client created, sources=%s", len(self._sources))
        except Exception:
            _LOGGER.error("UpzDownz options: exception in async_step_init:\n%s", traceback.format_exc())
        return await self.async_step_manage()

    # ── Manage ────────────────────────────────────────────────────────────────

    async def async_step_manage(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz options: async_step_manage, user_input=%s", user_input)
        errors = {}
        try:
            if user_input is not None:
                action = user_input.get("action", "")
                _LOGGER.debug("UpzDownz options: manage action=%s", action)
                if action == "finish":
                    return self.async_create_entry(title="", data={CONF_SOURCES: self._sources})
                if action.startswith("remove:"):
                    sid = action.split(":", 1)[1]
                    self._sources = [s for s in self._sources if s.get(CONF_SOURCE_ID) != sid]
                    return await self.async_step_manage()
                if action in SOURCE_TYPE_LABELS:
                    self._adding_type = action
                    if action in (SOURCE_TYPE_SENSORS, SOURCE_TYPE_CUSTOM):
                        return await self.async_step_pick_entities()
                    return await self.async_step_configure_source()
        except Exception:
            _LOGGER.error("UpzDownz options: exception in async_step_manage:\n%s", traceback.format_exc())
            errors["base"] = "unknown"

        options: dict[str, str] = {}
        for src in self._sources:
            label = SOURCE_TYPE_LABELS.get(src.get(CONF_SOURCE_TYPE, ""), "")
            options[f"remove:{src[CONF_SOURCE_ID]}"] = f"Remove: {src[CONF_SOURCE_NAME]} ({label})"
        for t, label in SOURCE_TYPE_LABELS.items():
            options[t] = f"Add: {label}"
        options["finish"] = "Save"

        return self.async_show_form(
            step_id="manage",
            data_schema=vol.Schema({
                vol.Required("action"): selector.selector({
                    "select": {"options": [{"value": k, "label": v} for k, v in options.items()], "mode": "list"}
                })
            }),
            errors=errors,
        )

    # ── Configure source ──────────────────────────────────────────────────────

    async def async_step_configure_source(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz options: async_step_configure_source, type=%s", self._adding_type)
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
                try:
                    _LOGGER.debug("UpzDownz options: creating source '%s'", source_cfg[CONF_SOURCE_NAME])
                    created = await self._client.create_source(
                        source_cfg[CONF_SOURCE_NAME],
                        _api_schema_for(self._adding_type, source_cfg, self.hass)
                    )
                    source_cfg[CONF_SOURCE_ID] = created["id"]
                    self._sources.append(source_cfg)
                    self._adding_type = None
                    return await self.async_step_manage()
                except UpzDownzRateLimitError:
                    errors["base"] = "row_limit"
                except UpzDownzAuthError:
                    errors["base"] = "invalid_auth"
                except UpzDownzApiError as err:
                    _LOGGER.error("UpzDownz options: create_source API error: %s", err)
                    errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.error("UpzDownz options: exception in async_step_configure_source:\n%s", traceback.format_exc())
            errors["base"] = "unknown"

        form_fn = FORM_FOR_TYPE.get(self._adding_type, list(FORM_FOR_TYPE.values())[0])
        return self.async_show_form(
            step_id="configure_source",
            data_schema=form_fn(),
            errors=errors,
            description_placeholders={
                "source_type": SOURCE_TYPE_LABELS.get(self._adding_type, self._adding_type or ""),
                "threshold": str(threshold_val),
            },
        )

    # ── Pick entities ─────────────────────────────────────────────────────────

    async def async_step_pick_entities(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz options: async_step_pick_entities")
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
            _LOGGER.error("UpzDownz options: exception in async_step_pick_entities:\n%s", traceback.format_exc())
            errors["base"] = "unknown"

        return self.async_show_form(
            step_id="pick_entities",
            data_schema=_entity_pick_form(),
            errors=errors,
            description_placeholders={"source_type": SOURCE_TYPE_LABELS.get(self._adding_type, "")},
        )

    # ── Field names ───────────────────────────────────────────────────────────

    async def async_step_field_names(self, user_input=None) -> FlowResult:
        _LOGGER.debug("UpzDownz options: async_step_field_names")
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
                    self._sources.append(source_cfg)
                    self._adding_type = None
                    return await self.async_step_manage()
                except UpzDownzRateLimitError:
                    errors["base"] = "row_limit"
                except UpzDownzAuthError:
                    errors["base"] = "invalid_auth"
                except UpzDownzApiError as err:
                    _LOGGER.error("UpzDownz options: create_source API error: %s", err)
                    errors["base"] = "cannot_connect"
        except Exception:
            _LOGGER.error("UpzDownz options: exception in async_step_field_names:\n%s", traceback.format_exc())
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
