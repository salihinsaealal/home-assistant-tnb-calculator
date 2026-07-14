"""Button platform for TNB Calculator integration."""
import logging
from typing import Any, Dict

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TNB Calculator button entities."""
    coordinator_data = hass.data[DOMAIN].get(config_entry.entry_id)
    if not coordinator_data or "coordinator" not in coordinator_data:
        _LOGGER.error("Could not find TNB Calculator coordinator for button setup")
        return

    coordinator = coordinator_data["coordinator"]

    async_add_entities([
        TNBAcceptSpikeButton(coordinator, config_entry),
    ])


class TNBAcceptSpikeButton(CoordinatorEntity, ButtonEntity):
    """Button to force-accept a blocked spike reading and reset the baseline."""

    _attr_icon = "mdi:lightning-bolt-circle"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, config_entry: ConfigEntry) -> None:
        """Initialize the accept spike button."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = f"{DEFAULT_NAME} Accept Spike Reading"
        self._attr_unique_id = f"{config_entry.entry_id}_accept_spike_reading"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
        }

    @property
    def available(self) -> bool:
        """Button is only pressable when a spike is currently blocked."""
        if self.coordinator.data is None:
            return False
        return (
            self.coordinator.data.get("import_spike_blocked", False)
            or self.coordinator.data.get("export_spike_blocked", False)
        )

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return spike status attributes for user visibility."""
        data = self.coordinator.data or {}
        return {
            "import_spike_blocked": data.get("import_spike_blocked", False),
            "export_spike_blocked": data.get("export_spike_blocked", False),
            "import_blocked_value_kwh": data.get("import_spike_blocked_value", 0.0),
            "export_blocked_value_kwh": data.get("export_spike_blocked_value", 0.0),
            "import_consecutive_rejections": data.get("import_consecutive_rejections", 0),
            "export_consecutive_rejections": data.get("export_consecutive_rejections", 0),
        }

    async def async_press(self) -> None:
        """Handle button press — accept blocked spike reading and reload integration."""
        _LOGGER.info("Accept Spike Reading button pressed.")
        await self.coordinator.accept_spike_reading()
        # Reload integration so sensor coordinator picks up storage change immediately
        await self.hass.config_entries.async_reload(self._config_entry.entry_id)
