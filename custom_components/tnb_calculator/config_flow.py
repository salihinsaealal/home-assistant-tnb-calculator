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
    CALENDARIFIC_BASE_URL,
    CALENDARIFIC_HOLIDAYS_ENDPOINT,
    CONF_CALENDARIFIC_API_KEY,
    CONF_EXPORT_ENTITY,
    CONF_IMPORT_ENTITY,
    DEFAULT_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class TNBCalculatorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TNB Calculator."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._import_entity: Optional[str] = None
        self._export_entity: Optional[str] = None
        self._api_key: Optional[str] = None

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

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    async def _validate_api_key(self, api_key: str) -> bool:
        """Validate the Calendarific API key."""
        try:
            session = async_get_clientsession(self.hass)
            params = {
                "api_key": api_key,
                "country": "MY",
                "year": 2024,
                "month": 1,
                "day": 1,
            }
            
            async with session.get(
                f"{CALENDARIFIC_BASE_URL}{CALENDARIFIC_HOLIDAYS_ENDPOINT}",
                params=params,
                timeout=10,
            ) as response:
                return response.status == 200
        except Exception:
            return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return TNBCalculatorOptionsFlow(config_entry)


class TNBCalculatorOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for TNB Calculator."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate API key if provided
            api_key = user_input.get(CONF_CALENDARIFIC_API_KEY)
            if api_key and not await self._validate_api_key(api_key):
                errors["base"] = "invalid_api_key"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_IMPORT_ENTITY,
                        default=self.config_entry.data.get(CONF_IMPORT_ENTITY),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["sensor", "utility_meter"],
                            device_class=["energy"],
                        )
                    ),
                    vol.Optional(
                        CONF_EXPORT_ENTITY,
                        default=self.config_entry.data.get(CONF_EXPORT_ENTITY),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["sensor", "utility_meter"],
                            device_class=["energy"],
                        )
                    ),
                    vol.Optional(
                        CONF_CALENDARIFIC_API_KEY,
                        default=self.config_entry.data.get(CONF_CALENDARIFIC_API_KEY),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def _validate_api_key(self, api_key: str) -> bool:
        """Validate the Calendarific API key."""
        try:
            session = async_get_clientsession(self.hass)
            params = {
                "api_key": api_key,
                "country": "MY",
                "year": 2024,
                "month": 1,
                "day": 1,
            }
            
            async with session.get(
                f"{CALENDARIFIC_BASE_URL}{CALENDARIFIC_HOLIDAYS_ENDPOINT}",
                params=params,
                timeout=10,
            ) as response:
                return response.status == 200
        except Exception:
            return False
