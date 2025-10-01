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
        # Validate required entities exist before forwarding to platforms
        import_entity = entry.data.get("import_entity")
        if import_entity:
            state = hass.states.get(import_entity)
            if state is None:
                _LOGGER.warning("Import entity %s not found, will retry setup", import_entity)
                raise ConfigEntryNotReady(f"Import entity {import_entity} not available yet")
        
        # Initialize the integration coordinator or data handler here
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "import_entity": import_entity,
            "export_entity": entry.data.get("export_entity"),
            "tou_enabled": entry.data.get("tou_enabled", False),
            "calendarific_api_key": entry.data.get("calendarific_api_key"),
            "country": entry.data.get("country", "MY"),
            "year": entry.data.get("year"),
            "import_peak_entity": entry.data.get("import_peak_entity"),
            "import_offpeak_entity": entry.data.get("import_offpeak_entity"),
            "export_total_entity": entry.data.get("export_total_entity"),
        }

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True
    
    except ConfigEntryNotReady:
        # Re-raise ConfigEntryNotReady as-is
        raise
    except Exception as ex:
        # Catch any other exception and convert to ConfigEntryNotReady
        _LOGGER.error("Error setting up TNB Calculator: %s", ex, exc_info=True)
        raise ConfigEntryNotReady(f"Failed to set up TNB Calculator: {ex}") from ex


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading TNB Calculator integration")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
