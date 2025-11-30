"""Switch platform for TNB Calculator integration."""
import logging
from typing import Any, Dict, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DEFAULT_NAME,
    DOMAIN,
    DEFAULT_AFA_RATE,
    DEFAULT_RETAILING_CHARGE,
    TARIFF_SOURCE_DEFAULT,
    AUTO_FETCH_API_URL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TNB Calculator switch entities."""
    # Get coordinator from hass.data (stored by __init__.py)
    coordinator_data = hass.data[DOMAIN].get(config_entry.entry_id)
    if not coordinator_data or "coordinator" not in coordinator_data:
        _LOGGER.error("Could not find TNB Calculator coordinator for switch setup")
        return
    
    coordinator = coordinator_data["coordinator"]
    
    # Create the auto-fetch switch
    async_add_entities([
        TNBAutoFetchSwitch(coordinator, config_entry),
    ])


class TNBAutoFetchSwitch(CoordinatorEntity, SwitchEntity):
    """Switch entity to toggle auto-fetch tariffs from API (Experimental).
    
    When ON: Fetches all tariff rates from the external API and uses them.
    When OFF: Resets ALL rates (including AFA) to hardcoded defaults.
    
    ⚠️ WARNING: This is an experimental feature.
    - When turning OFF, AFA rate will also be reset to default.
    - Monitor calculated rates for accuracy when enabled.
    """

    _attr_icon = "mdi:cloud-sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the auto-fetch switch."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"{DEFAULT_NAME} Auto Fetch Tariffs (Experimental)"
        self._attr_unique_id = f"{config_entry.entry_id}_auto_fetch_tariffs"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
        }

    @property
    def is_on(self) -> bool:
        """Return True if auto-fetch is enabled."""
        return self.coordinator.auto_fetch_enabled

    @property
    def icon(self) -> str:
        """Return icon based on state."""
        if self.is_on:
            return "mdi:cloud-sync"
        return "mdi:cloud-off-outline"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on auto-fetch - fetches rates from API."""
        success = await self.coordinator.async_toggle_auto_fetch(enabled=True)
        if not success:
            _LOGGER.warning("Failed to enable auto-fetch tariffs")
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off auto-fetch - resets all rates to hardcoded defaults."""
        await self.coordinator.async_toggle_auto_fetch(enabled=False)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return extra state attributes with warnings and status info."""
        attrs: Dict[str, Any] = {
            "tariff_source": self.coordinator._tariff_overrides.get("source", TARIFF_SOURCE_DEFAULT),
        }
        
        if self.is_on:
            # Show warning when enabled
            attrs["warning"] = "⚠️ Experimental: Monitor calculated rates for accuracy"
            attrs["api_url"] = AUTO_FETCH_API_URL
            attrs["last_updated"] = self.coordinator._tariff_overrides.get("last_updated")
            attrs["effective_date"] = self.coordinator._tariff_overrides.get("effective_date")
            
            # Show current rates from API
            afa = self.coordinator._tariff_overrides.get("afa_rate")
            if afa is not None:
                attrs["afa_rate_myr"] = afa
            
            tariffs = self.coordinator._tariff_overrides.get("tariffs")
            if tariffs:
                shared = tariffs.get("shared", {})
                attrs["capacity_rate"] = shared.get("capacity")
                attrs["network_rate"] = shared.get("network")
                attrs["retailing_charge"] = shared.get("retailing")
        else:
            # Show info when disabled
            attrs["info"] = "Using hardcoded default rates"
            attrs["default_afa_rate"] = DEFAULT_AFA_RATE
            attrs["default_capacity_rate"] = 0.0455
            attrs["default_network_rate"] = 0.1285
            attrs["default_retailing_charge"] = DEFAULT_RETAILING_CHARGE
        
        # Show error if any
        error = self.coordinator.auto_fetch_last_error
        if error:
            attrs["last_error"] = error
        
        return attrs
