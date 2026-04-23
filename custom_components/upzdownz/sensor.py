"""Diagnostic sensor entities for UpzDownz data sources."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_LAST_SYNC,
    ATTR_ROWS_SENT,
    ATTR_SOURCE_ID,
    ATTR_SOURCE_TYPE,
    CONF_SOURCE_NAME,
    CONF_SOURCE_ID,
    CONF_SOURCE_TYPE,
    DOMAIN,
    STATUS_OK,
    STATUS_ERROR,
    STATUS_NO_DATA,
)
from .coordinator import UpzDownzSourceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up UpzDownz diagnostic sensors."""
    coordinators: list[UpzDownzSourceCoordinator] = hass.data[DOMAIN][entry.entry_id]["coordinators"]
    entities = [UpzDownzStatusSensor(coordinator) for coordinator in coordinators]
    async_add_entities(entities, update_before_add=True)


class UpzDownzStatusSensor(CoordinatorEntity[UpzDownzSourceCoordinator], SensorEntity):
    """Sensor showing the sync status for one UpzDownz data source."""

    _attr_icon = "mdi:cloud-upload-outline"
    _attr_has_entity_name = True

    def __init__(self, coordinator: UpzDownzSourceCoordinator) -> None:
        super().__init__(coordinator)
        self._source_id = coordinator.source_id
        self._source_name = coordinator.source_name
        self._source_type = coordinator.source_type
        self._attr_name = f"UpzDownz {self._source_name}"
        self._attr_unique_id = f"{DOMAIN}_{self._source_id}_status"

    @property
    def native_value(self) -> str:
        """Return the current sync status."""
        return self.coordinator.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        last_sync = self.coordinator.last_sync
        return {
            ATTR_LAST_SYNC: last_sync.isoformat() if last_sync else None,
            ATTR_ROWS_SENT: self.coordinator.rows_sent,
            ATTR_SOURCE_ID: self._source_id,
            ATTR_SOURCE_TYPE: self._source_type,
        }

    @property
    def available(self) -> bool:
        """Mark as unavailable only on auth errors (status stays available otherwise)."""
        return self.coordinator.last_update_success or self.coordinator.status != STATUS_ERROR

    @property
    def icon(self) -> str:
        status = self.coordinator.status
        if status == STATUS_OK:
            return "mdi:cloud-check-outline"
        if status == STATUS_ERROR:
            return "mdi:cloud-alert"
        return "mdi:cloud-off-outline"
