"""DataUpdateCoordinator for UpzDownz integration."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UpzDownzApiClient, UpzDownzApiError, UpzDownzAuthError, UpzDownzRateLimitError
from .const import (
    CONF_SOURCE_ID, CONF_SOURCE_NAME, CONF_SOURCE_TYPE,
    CONF_ENTITIES, CONF_INTERVAL, CONF_THRESHOLD, CONF_DOMAINS_EXCLUDE,
    CONF_CALENDAR_ENTITIES, CONF_WEATHER_ENTITY, CONF_FIELD_MAPPINGS,
    CONF_LIGHTS_MODE, CONF_BATTERY_REPORT_ALL,
    DEFAULT_BATTERY_THRESHOLD, DEFAULT_EXCLUDED_DOMAINS, DEFAULT_INTERVAL,
    DOMAIN,
    SOURCE_TYPE_SENSORS, SOURCE_TYPE_BATTERY, SOURCE_TYPE_UNAVAILABLE,
    SOURCE_TYPE_CALENDAR, SOURCE_TYPE_WEATHER, SOURCE_TYPE_LIGHTS, SOURCE_TYPE_CUSTOM,
    LIGHTS_MODE_PER_LIGHT, LIGHTS_MODE_SUMMARY,
    STATUS_OK, STATUS_ERROR, STATUS_NO_DATA,
)

_LOGGER = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UpzDownzSourceCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, client: UpzDownzApiClient, source_config: dict, entry: ConfigEntry) -> None:
        self.client = client
        self.source_config = source_config
        self.entry = entry
        self.source_id: str = source_config[CONF_SOURCE_ID]
        self.source_name: str = source_config[CONF_SOURCE_NAME]
        self.source_type: str = source_config[CONF_SOURCE_TYPE]
        self.status: str = STATUS_OK
        self.last_sync: datetime | None = None
        self.rows_sent: int = 0

        super().__init__(
            hass, _LOGGER,
            name=f"UpzDownz [{self.source_name}]",
            update_interval=timedelta(seconds=source_config.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        )

    async def _async_update_data(self) -> dict:
        try:
            rows = await self._collect_rows()
            if not rows:
                self.status = STATUS_NO_DATA
                return {"status": STATUS_NO_DATA, "rows": 0}

            await self.client.push_data(self.source_id, rows)
            self.status = STATUS_OK
            self.last_sync = datetime.now(timezone.utc)
            self.rows_sent += len(rows)
            _LOGGER.debug("UpzDownz: pushed %d rows to '%s'", len(rows), self.source_name)
            return {"status": STATUS_OK, "rows": len(rows)}

        except UpzDownzAuthError as err:
            self.status = STATUS_ERROR
            _LOGGER.error("UpzDownz auth error for '%s': %s", self.source_name, err)
            await self._notify(
                f"UpzDownz — Authentication error ({self.source_name})",
                "Your API key was rejected. Go to Settings → Devices & Services → UpzDownz → Configure to re-enter it.",
                f"upzdownz_auth_{self.source_id}",
            )
            raise UpdateFailed(f"Authentication failed: {err}") from err

        except UpzDownzRateLimitError as err:
            self.status = STATUS_ERROR
            _LOGGER.warning("UpzDownz row limit reached for '%s': %s", self.source_name, err)
            await self._notify(
                f"UpzDownz — Row limit reached ({self.source_name})",
                "Your UpzDownz plan has reached its row limit. Upgrade your plan or reduce sync frequency in Settings → Devices & Services → UpzDownz → Configure.",
                f"upzdownz_limit_{self.source_id}",
            )
            return {"status": STATUS_ERROR, "rows": 0}

        except UpzDownzApiError as err:
            self.status = STATUS_ERROR
            _LOGGER.error("UpzDownz API error for '%s': %s", self.source_name, err)
            if self.last_sync is None:
                await self._notify(
                    f"UpzDownz — Connection error ({self.source_name})",
                    f"Could not reach UpzDownz for '{self.source_name}'. Will retry automatically.",
                    f"upzdownz_conn_{self.source_id}",
                )
            return {"status": STATUS_ERROR, "rows": 0}

        except Exception as err:
            self.status = STATUS_ERROR
            _LOGGER.error("UpzDownz unexpected error for '%s': %s", self.source_name, err, exc_info=True)
            return {"status": STATUS_ERROR, "rows": 0}

    async def _notify(self, title: str, message: str, notification_id: str) -> None:
        try:
            await self.hass.services.async_call(
                "persistent_notification", "create",
                {"title": title, "message": message, "notification_id": notification_id},
                blocking=False,
            )
        except Exception:
            pass

    async def _collect_rows(self) -> list[dict]:
        t = self.source_type
        if t == SOURCE_TYPE_SENSORS:     return await self._collect_sensors()
        if t == SOURCE_TYPE_BATTERY:     return await self._collect_battery()
        if t == SOURCE_TYPE_UNAVAILABLE: return await self._collect_unavailable()
        if t == SOURCE_TYPE_CALENDAR:    return await self._collect_calendar()
        if t == SOURCE_TYPE_WEATHER:     return await self._collect_weather()
        if t == SOURCE_TYPE_LIGHTS:      return await self._collect_lights()
        if t == SOURCE_TYPE_CUSTOM:      return await self._collect_custom()
        _LOGGER.warning("UpzDownz: unknown source_type '%s'", t)
        return []

    # ── Sensors ───────────────────────────────────────────────────────────────

    async def _collect_sensors(self) -> list[dict]:
        entities: dict[str, str] = self.source_config.get(CONF_ENTITIES, {})
        row: dict[str, Any] = {"recorded_at": _utcnow_iso()}
        for entity_id, field_name in entities.items():
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            row[field_name] = _coerce_state(state.state)
        return [row] if len(row) > 1 else []

    # ── Battery ───────────────────────────────────────────────────────────────

    async def _collect_battery(self) -> list[dict]:
        threshold = self.source_config.get(CONF_THRESHOLD, DEFAULT_BATTERY_THRESHOLD)
        report_all = self.source_config.get(CONF_BATTERY_REPORT_ALL, False)
        rows = []
        recorded_at = _utcnow_iso()
        for state in self.hass.states.async_all():
            if state.attributes.get("device_class") != "battery":
                continue
            try:
                level = float(state.state)
            except (ValueError, TypeError):
                continue
            if report_all or level < threshold:
                rows.append({
                    "entity_id":       state.entity_id,
                    "friendly_name":   state.attributes.get("friendly_name", state.entity_id),
                    "battery_level":   level,
                    "below_threshold": level < threshold,
                    "recorded_at":     recorded_at,
                })
        return rows

    # ── Unavailable ───────────────────────────────────────────────────────────

    async def _collect_unavailable(self) -> list[dict]:
        excluded: list[str] = self.source_config.get(CONF_DOMAINS_EXCLUDE, DEFAULT_EXCLUDED_DOMAINS)
        rows = []
        recorded_at = _utcnow_iso()
        for state in self.hass.states.async_all():
            if state.state not in ("unavailable", "unknown"):
                continue
            domain = state.entity_id.split(".")[0]
            if domain in excluded:
                continue
            rows.append({
                "entity_id":    state.entity_id,
                "friendly_name": state.attributes.get("friendly_name", state.entity_id),
                "domain":       domain,
                "state":        state.state,
                "last_changed": state.last_changed.strftime("%Y-%m-%dT%H:%M:%SZ") if state.last_changed else None,
                "recorded_at":  recorded_at,
            })
        return rows

    # ── Calendar ──────────────────────────────────────────────────────────────

    async def _collect_calendar(self) -> list[dict]:
        calendar_entities: list[str] = self.source_config.get(CONF_CALENDAR_ENTITIES, [])
        rows = []
        recorded_at = _utcnow_iso()
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=7)
        for cal_entity in calendar_entities:
            try:
                result = await self.hass.services.async_call(
                    "calendar", "get_events",
                    {"entity_id": cal_entity, "start_date_time": now.isoformat(), "end_date_time": end.isoformat()},
                    blocking=True, return_response=True,
                )
                events = result.get(cal_entity, {}).get("events", []) if result else []
                for event in events:
                    rows.append({
                        "calendar":    cal_entity,
                        "summary":     event.get("summary", ""),
                        "start":       str(event.get("start", "")),
                        "end":         str(event.get("end", "")),
                        "all_day":     event.get("all_day", False),
                        "recorded_at": recorded_at,
                    })
            except Exception as err:
                _LOGGER.warning("UpzDownz: failed to get events for '%s': %s", cal_entity, err)
        return rows

    # ── Weather ───────────────────────────────────────────────────────────────

    async def _collect_weather(self) -> list[dict]:
        """Collect one row with current conditions + forecast array embedded."""
        weather_entity: str = self.source_config.get(CONF_WEATHER_ENTITY, "")
        if not weather_entity:
            return []
        state = self.hass.states.get(weather_entity)
        if state is None:
            return []

        attrs = state.attributes
        recorded_at = _utcnow_iso()

        # Fetch daily forecast via service
        forecast = []
        try:
            result = await self.hass.services.async_call(
                "weather", "get_forecasts",
                {"entity_id": weather_entity, "type": "daily"},
                blocking=True, return_response=True,
            )
            raw_forecast = result.get(weather_entity, {}).get("forecast", []) if result else []
            for fc in raw_forecast:
                forecast.append({
                    "datetime":      str(fc.get("datetime", "")),
                    "condition":     fc.get("condition", ""),
                    "temperature":   fc.get("temperature"),
                    "templow":       fc.get("templow"),
                    "precipitation": fc.get("precipitation"),
                    "wind_speed":    fc.get("wind_speed"),
                    "wind_bearing":  fc.get("wind_bearing"),
                    "humidity":      fc.get("humidity"),
                })
        except Exception as err:
            _LOGGER.warning("UpzDownz: failed to get forecast for '%s': %s", weather_entity, err)

        row: dict[str, Any] = {
            "condition":    state.state,
            "temperature":  attrs.get("temperature"),
            "humidity":     attrs.get("humidity"),
            "wind_speed":   attrs.get("wind_speed"),
            "wind_bearing": attrs.get("wind_bearing"),
            "pressure":     attrs.get("pressure"),
            "feels_like":   attrs.get("apparent_temperature") or attrs.get("temperature"),
            "forecast":     json.dumps(forecast),   # stored as JSON string in UpzDownz
            "recorded_at":  recorded_at,
        }
        return [row]

    # ── Lights ────────────────────────────────────────────────────────────────

    async def _collect_lights(self) -> list[dict]:
        mode = self.source_config.get(CONF_LIGHTS_MODE, LIGHTS_MODE_PER_LIGHT)
        recorded_at = _utcnow_iso()

        all_lights = [s for s in self.hass.states.async_all() if s.entity_id.startswith("light.")]

        if mode == LIGHTS_MODE_SUMMARY:
            lights_on = sum(1 for s in all_lights if s.state == "on")
            return [{
                "lights_on":    lights_on,
                "lights_total": len(all_lights),
                "recorded_at":  recorded_at,
            }]

        # Per-light mode
        rows = []
        for state in all_lights:
            brightness_raw = state.attributes.get("brightness", 0) or 0
            rows.append({
                "entity_id":    state.entity_id,
                "friendly_name": state.attributes.get("friendly_name", state.entity_id),
                "state":        state.state,
                "brightness":   int(brightness_raw),
                "area":         state.attributes.get("area_id", ""),
                "recorded_at":  recorded_at,
            })
        return rows

    # ── Custom ────────────────────────────────────────────────────────────────

    async def _collect_custom(self) -> list[dict]:
        field_mappings: dict[str, str] = self.source_config.get(CONF_FIELD_MAPPINGS, {})
        row: dict[str, Any] = {"recorded_at": _utcnow_iso()}
        for entity_id, field_name in field_mappings.items():
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            row[field_name] = _coerce_state(state.state)
        return [row] if len(row) > 1 else []


def _coerce_state(value: str) -> Any:
    if value in ("unavailable", "unknown", "none", "null", ""):
        return None
    try:
        return float(value) if "." in value else int(value)
    except (ValueError, TypeError):
        return value
