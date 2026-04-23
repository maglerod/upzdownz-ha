"""The UpzDownz integration."""
from __future__ import annotations

import logging
import traceback

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import UpzDownzApiClient
from .const import CONF_API_KEY, CONF_SOURCES, CONF_SOURCE_NAME, CONF_SOURCE_ID, DOMAIN
from .coordinator import UpzDownzSourceCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("UpzDownz: async_setup_entry called, entry_id=%s", entry.entry_id)
    try:
        hass.data.setdefault(DOMAIN, {})

        api_key: str = entry.data[CONF_API_KEY]
        session = async_get_clientsession(hass)
        client = UpzDownzApiClient(api_key, session)

        sources: list[dict] = list(
            entry.options.get(CONF_SOURCES)
            or entry.data.get(CONF_SOURCES)
            or []
        )
        _LOGGER.debug("UpzDownz: setting up %d source(s)", len(sources))

        coordinators: list[UpzDownzSourceCoordinator] = []
        for source_config in sources:
            try:
                coordinator = UpzDownzSourceCoordinator(hass, client, source_config, entry)
                await coordinator.async_config_entry_first_refresh()
                coordinators.append(coordinator)
                _LOGGER.debug("UpzDownz: coordinator ready for source '%s'", source_config.get(CONF_SOURCE_NAME))
            except Exception:
                _LOGGER.warning(
                    "UpzDownz: first refresh failed for source '%s', will retry:\n%s",
                    source_config.get(CONF_SOURCE_NAME, source_config.get(CONF_SOURCE_ID, "unknown")),
                    traceback.format_exc(),
                )
                coordinators.append(coordinator)

        hass.data[DOMAIN][entry.entry_id] = {"client": client, "coordinators": coordinators}

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(_async_options_updated))

        _LOGGER.debug("UpzDownz: setup complete")
        return True

    except Exception:
        _LOGGER.error("UpzDownz: fatal error in async_setup_entry:\n%s", traceback.format_exc())
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
