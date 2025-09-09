"""TNB Calculator integration for Home Assistant."""
import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TNB Calculator from a config entry."""
    _LOGGER.info("Setting up TNB Calculator integration")

    try:
        # Initialize the integration coordinator or data handler here
        # For now, we'll create a simple data structure

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "import_entity": entry.data.get("import_entity"),
            "export_entity": entry.data.get("export_entity"),
            "tou_enabled": entry.data.get("tou_enabled", False),
            "calendarific_api_key": entry.data.get("calendarific_api_key"),
            "country": entry.data.get("country", "MY"),
            "year": entry.data.get("year"),
        }

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True

    except Exception as ex:
        _LOGGER.error("Error setting up TNB Calculator: %s", ex)
        raise ConfigEntryNotReady from ex


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading TNB Calculator integration")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
