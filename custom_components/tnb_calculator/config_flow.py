"""Config flow for TNB Calculator integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_CALENDARIFIC_API_KEY,
    CONF_COUNTRY,
    CONF_EXPORT_ENTITY,
    CONF_EXPORT_TOTAL_ENTITY,
    CONF_IMPORT_ENTITY,
    CONF_IMPORT_OFFPEAK_ENTITY,
    CONF_IMPORT_PEAK_ENTITY,
    CONF_TOU_ENABLED,
    CONF_YEAR,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class TNBCalculatorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TNB Calculator."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._import_entity = None
        self._export_entity = None
        self._tou_enabled = False
        self._api_key = None
        self._import_peak_entity = None
        self._import_offpeak_entity = None
        self._export_total_entity = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate the input
            if not user_input.get(CONF_IMPORT_ENTITY):
                errors[CONF_IMPORT_ENTITY] = "import_entity_required"

            # Validate API key if provided
            api_key = user_input.get(CONF_CALENDARIFIC_API_KEY)
            if api_key and not await self._validate_api_key(api_key):
                errors["base"] = "invalid_api_key"

            if not errors:
                return self.async_create_entry(
                    title="TNB Calculator",
                    data=user_input,
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_IMPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "utility_meter"],
                        device_class=["energy"],
                    )
                ),
                vol.Optional(
                    CONF_EXPORT_ENTITY,
                    default=user_input.get(CONF_EXPORT_ENTITY) if user_input else None,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "utility_meter"],
                        device_class=["energy"],
                    )
                ),
                vol.Optional(
                    CONF_CALENDARIFIC_API_KEY,
                    default=user_input.get(CONF_CALENDARIFIC_API_KEY) if user_input else None,
                ): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    )
                ),
            }
        )
