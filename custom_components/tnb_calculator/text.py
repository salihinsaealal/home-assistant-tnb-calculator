"""Text platform for TNB Calculator integration."""
import logging
from typing import Any

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    AFA_AUTO_FETCH_API_URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TNB Calculator text entities."""
    # Get coordinator from hass.data (stored by __init__.py)
    coordinator_data = hass.data[DOMAIN].get(config_entry.entry_id)
    if not coordinator_data or "coordinator" not in coordinator_data:
        _LOGGER.error("Could not find TNB Calculator coordinator for text setup")
        return
    
    coordinator = coordinator_data["coordinator"]
    
    # Create the AFA API URL text entity
    async_add_entities([
        TNBAFAApiUrlText(coordinator, config_entry),
    ])


class TNBAFAApiUrlText(CoordinatorEntity, TextEntity):
    """Text entity to configure AFA API URL for fetch_afa_rate service.
    
    This URL is used by:
    - The fetch_afa_rate service (when no URL is passed)
    - Weekly auto-fetch for AFA-only mode
    
    Leave empty to use the default: https://tnb.cikgusaleh.work/afa/simple
    """

    _attr_icon = "mdi:api"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = TextMode.TEXT
    _attr_native_max = 255
    _attr_native_min = 0

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the AFA API URL text entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"{DEFAULT_NAME} AFA API URL"
        self._attr_unique_id = f"{config_entry.entry_id}_afa_api_url"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
        }

    @property
    def native_value(self) -> str:
        """Return the current AFA API URL."""
        # Priority: stored api_url > empty (shows placeholder in UI)
        url = self.coordinator._tariff_overrides.get("api_url") or ""
        return url

    async def async_set_value(self, value: str) -> None:
        """Set the AFA API URL."""
        value = value.strip()
        
        if value:
            # Validate URL format (basic check)
            if not value.startswith(("http://", "https://")):
                _LOGGER.warning("Invalid URL format: %s (must start with http:// or https://)", value)
                return
            
            self.coordinator._tariff_overrides["api_url"] = value
            _LOGGER.info("AFA API URL set to: %s", value)
        else:
            # Clear the URL - will fall back to default
            self.coordinator._tariff_overrides["api_url"] = None
            _LOGGER.info("AFA API URL cleared - will use default: %s", AFA_AUTO_FETCH_API_URL)
        
        # Save to storage
        await self.coordinator._save_monthly_data()
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        current_url = self.coordinator._tariff_overrides.get("api_url")
        return {
            "current_url": current_url or "(not set)",
            "default_url": AFA_AUTO_FETCH_API_URL,
            "effective_url": current_url or AFA_AUTO_FETCH_API_URL,
            "note": "Leave empty to use default URL. Used by fetch_afa_rate service and weekly auto-fetch.",
        }
