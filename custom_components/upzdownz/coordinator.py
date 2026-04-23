"""DataUpdateCoordinator for UpzDownz integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UpzDownzApiClient, UpzDownzApiError, UpzDownzAuthError, UpzDownzRateLimitError
from .const import (
    CONF_API_KEY,
    CONF_SOURCES,
    CONF_SOURCE_ID,
    CONF_SOURCE_NAME,
    CONF_SOURCE_TYPE,
    CONF_ENTITIES,
    CONF_INTERVAL,
    CONF_THRESHOLD,
    CONF_DOMAINS_EXCLUDE,
    CONF_CALENDAR_ENTITIES,
    CONF_WEATHER_ENTITY,
    CONF_FIELD_MAPPINGS,
    DEFAULT_BATTERY_THRESHOLD,
    DEFAULT_EXCLUDED_DOMAINS,
    DEFAULT_INTERVAL,
    DOMAIN,
    SOURCE_TYPE_SENSORS,
    SOURCE_TYPE_BATTERY,
    SOURCE_TYPE_UNAVAILABLE,
    SOURCE_TYPE_CALENDAR,
    SOURCE_TYPE_WEATHER,
    SOURCE_TYPE_CUSTOM,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_NO_DATA,
)

_LOGGER = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class UpzDownzSourceCoordinator(DataUpdateCoordinator):
    """Coordinator that manages a single UpzDownz data source."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: UpzDownzApiClient,
        source_config: dict,
        entry: ConfigEntry,
    ) -> None:
        self.client = client
        self.source_config = source_config
        self.entry = entry
        self.source_id: str = source_config[CONF_SOURCE_ID]
        self.source_name: str = source_config[CONF_SOURCE_NAME]
        self.source_type: str = source_config[CONF_SOURCE_TYPE]
        self.status: str = STATUS_OK
        self.last_sync: datetime | None = None
        self.rows_sent: int = 0

        interval_seconds = source_config.get(CONF_INTERVAL, DEFAULT_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"UpzDownz [{self.source_name}]",
            update_interval=timedelta(seconds=interval_seconds),
        )

    async def _async_update_data(self) -> dict:
        """Fetch data and push it to UpzDownz."""
        try:
            rows = await self._collect_rows()
            if not rows:
                self.status = STATUS_NO_DATA
                return {"status": STATUS_NO_DATA, "rows": 0}

            await self.client.push_data(self.source_id, rows)
            self.status = STATUS_OK
            self.last_sync = datetime.now(timezone.utc)
            self.rows_sent += len(rows)
            _LOGGER.debug(
                "UpzDownz: pushed %d rows to source '%s' (%s)",
                len(rows),
                self.source_name,
                self.source_id,
            )
            return {"status": STATUS_OK, "rows": len(rows)}

        except UpzDownzAuthError as err:
            self.status = STATUS_ERROR
            _LOGGER.error("UpzDownz auth error for source '%s': %s", self.source_name, err)
            await self._notify(
                f"UpzDownz — Authentication error ({self.source_name})",
                "Your API key was rejected by UpzDownz. Please go to Settings → Devices & Services → UpzDownz → Configure and re-enter your API key.",
                notification_id=f"upzdownz_auth_{self.source_id}",
            )
            raise UpdateFailed(f"Authentication failed: {err}") from err

        except UpzDownzRateLimitError as err:
            self.status = STATUS_ERROR
            _LOGGER.warning(
                "UpzDownz row limit reached for source '%s': %s", self.source_name, err
            )
            await self._notify(
                f"UpzDownz — Row limit reached ({self.source_name})",
                "Your UpzDownz plan has reached its row limit. Data for this source is being skipped until the limit resets. To fix this, upgrade your UpzDownz plan or reduce the sync frequency in Settings → Devices & Services → UpzDownz → Configure.",
                notification_id=f"upzdownz_limit_{self.source_id}",
            )
            return {"status": STATUS_ERROR, "rows": 0}

        except UpzDownzApiError as err:
            self.status = STATUS_ERROR
            _LOGGER.error("UpzDownz API error for source '%s': %s", self.source_name, err)
            # Only notify on first failure to avoid spamming
            if self.last_sync is None:
                await self._notify(
                    f"UpzDownz — Connection error ({self.source_name})",
                    f"Could not reach UpzDownz for data source '{self.source_name}'. The integration will keep retrying automatically. Check your network connection if this persists.",
                    notification_id=f"upzdownz_conn_{self.source_id}",
                )
            return {"status": STATUS_ERROR, "rows": 0}

        except Exception as err:  # noqa: BLE001
            self.status = STATUS_ERROR
            _LOGGER.error(
                "Unexpected error in UpzDownz coordinator for source '%s': %s",
                self.source_name,
                err,
                exc_info=True,
            )
            return {"status": STATUS_ERROR, "rows": 0}

    async def _notify(self, title: str, message: str, notification_id: str) -> None:
        """Fire a persistent notification in Home Assistant."""
        try:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": title,
                    "message": message,
                    "notification_id": notification_id,
                },
                blocking=False,
            )
        except Exception:  # noqa: BLE001
            pass  # Never let notification failure break the coordinator

    async def _collect_rows(self) -> list[dict]:
        """Collect rows based on source_type."""
        source_type = self.source_type
        if source_type == SOURCE_TYPE_SENSORS:
            return await self._collect_sensors()
        if source_type == SOURCE_TYPE_BATTERY:
            return await self._collect_battery()
        if source_type == SOURCE_TYPE_UNAVAILABLE:
            return await self._collect_unavailable()
        if source_type == SOURCE_TYPE_CALENDAR:
            return await self._collect_calendar()
        if source_type == SOURCE_TYPE_WEATHER:
            return await self._collect_weather()
        if source_type == SOURCE_TYPE_CUSTOM:
            return await self._collect_custom()
        _LOGGER.warning("UpzDownz: unknown source_type '%s'", source_type)
        return []

    async def _collect_sensors(self) -> list[dict]:
        """Collect a snapshot row from selected sensor entities."""
        entities: dict[str, str] = self.source_config.get(CONF_ENTITIES, {})
        # entities is { entity_id: field_name }
        row: dict[str, Any] = {"recorded_at": _utcnow_iso()}
        for entity_id, field_name in entities.items():
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            row[field_name] = _coerce_state(state.state)
        return [row] if len(row) > 1 else []

    async def _collect_battery(self) -> list[dict]:
        """Collect one row per low-battery entity."""
        threshold = self.source_config.get(CONF_THRESHOLD, DEFAULT_BATTERY_THRESHOLD)
        rows = []
        recorded_at = _utcnow_iso()
        for state in self.hass.states.async_all():
            if state.attributes.get("device_class") != "battery":
                continue
            try:
                level = float(state.state)
            except (ValueError, TypeError):
                continue
            if level < threshold:
                rows.append({
                    "entity_id": state.entity_id,
                    "friendly_name": state.attributes.get("friendly_name", state.entity_id),
                    "battery_level": level,
                    "recorded_at": recorded_at,
                })
        return rows

    async def _collect_unavailable(self) -> list[dict]:
        """Collect one row per unavailable/unknown entity."""
        excluded_domains: list[str] = self.source_config.get(
            CONF_DOMAINS_EXCLUDE, DEFAULT_EXCLUDED_DOMAINS
        )
        rows = []
        recorded_at = _utcnow_iso()
        for state in self.hass.states.async_all():
            if state.state not in ("unavailable", "unknown"):
                continue
            domain = state.entity_id.split(".")[0]
            if domain in excluded_domains:
                continue
            rows.append({
                "entity_id": state.entity_id,
                "domain": domain,
                "friendly_name": state.attributes.get("friendly_name", state.entity_id),
                "last_changed": state.last_changed.strftime("%Y-%m-%dT%H:%M:%SZ")
                if state.last_changed
                else None,
                "recorded_at": recorded_at,
            })
        return rows

    async def _collect_calendar(self) -> list[dict]:
        """Collect upcoming calendar events (next 7 days)."""
        calendar_entities: list[str] = self.source_config.get(CONF_CALENDAR_ENTITIES, [])
        rows = []
        recorded_at = _utcnow_iso()
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=7)

        for cal_entity in calendar_entities:
            try:
                result = await self.hass.services.async_call(
                    "calendar",
                    "get_events",
                    {
                        "entity_id": cal_entity,
                        "start_date_time": now.isoformat(),
                        "end_date_time": end.isoformat(),
                    },
                    blocking=True,
                    return_response=True,
                )
                events = result.get(cal_entity, {}).get("events", []) if result else []
                for event in events:
                    rows.append({
                        "calendar": cal_entity,
                        "summary": event.get("summary", ""),
                        "start": str(event.get("start", "")),
                        "end": str(event.get("end", "")),
                        "all_day": event.get("all_day", False),
                        "recorded_at": recorded_at,
                    })
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "UpzDownz: failed to get events for '%s': %s", cal_entity, err
                )
        return rows

    async def _collect_weather(self) -> list[dict]:
        """Collect current weather + daily forecast."""
        weather_entity: str = self.source_config.get(CONF_WEATHER_ENTITY, "")
        if not weather_entity:
            return []

        state = self.hass.states.get(weather_entity)
        if state is None:
            return []

        attrs = state.attributes
        recorded_at = _utcnow_iso()
        rows = []

        # Current conditions
        current_row: dict[str, Any] = {
            "type": "current",
            "condition": state.state,
            "temperature": attrs.get("temperature"),
            "humidity": attrs.get("humidity"),
            "wind_speed": attrs.get("wind_speed"),
            "pressure": attrs.get("pressure"),
            "recorded_at": recorded_at,
        }
        rows.append(current_row)

        # Forecast via service
        try:
            result = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather_entity, "type": "daily"},
                blocking=True,
                return_response=True,
            )
            forecasts = result.get(weather_entity, {}).get("forecast", []) if result else []
            for fc in forecasts:
                rows.append({
                    "type": "forecast",
                    "condition": fc.get("condition", ""),
                    "temperature": fc.get("temperature"),
                    "templow": fc.get("templow"),
                    "precipitation": fc.get("precipitation"),
                    "wind_speed": fc.get("wind_speed"),
                    "datetime": str(fc.get("datetime", "")),
                    "recorded_at": recorded_at,
                })
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning(
                "UpzDownz: failed to get weather forecast for '%s': %s", weather_entity, err
            )
        return rows

    async def _collect_custom(self) -> list[dict]:
        """Collect snapshot row for a custom-configured set of entities."""
        field_mappings: dict[str, str] = self.source_config.get(CONF_FIELD_MAPPINGS, {})
        row: dict[str, Any] = {"recorded_at": _utcnow_iso()}
        for entity_id, field_name in field_mappings.items():
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            row[field_name] = _coerce_state(state.state)
        return [row] if len(row) > 1 else []


def _coerce_state(value: str) -> Any:
    """Try to convert a HA state string to a numeric value."""
    if value in ("unavailable", "unknown", "none", "null", ""):
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except (ValueError, TypeError):
        return value
