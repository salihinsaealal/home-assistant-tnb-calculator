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
    CONF_IMPORT_ENTITY,
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

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            # Validate the input
            if not user_input.get(CONF_IMPORT_ENTITY):
                errors[CONF_IMPORT_ENTITY] = "import_entity_required"

            # Store the data
            self._import_entity = user_input.get(CONF_IMPORT_ENTITY)
            self._export_entity = user_input.get(CONF_EXPORT_ENTITY)
            self._tou_enabled = user_input.get(CONF_TOU_ENABLED, False)
            self._api_key = user_input.get(CONF_CALENDARIFIC_API_KEY)

            # If ToU is enabled but no API key provided, require API key
            if self._tou_enabled and not self._api_key:
                errors[CONF_CALENDARIFIC_API_KEY] = "api_key_required_for_tou"

            if not errors:
                # If ToU is enabled and we have API key, validate it
                if self._tou_enabled and self._api_key:
                    # Validate API key before proceeding
                    if await self._validate_api_key(self._api_key, "MY", 2024):
                        return self._create_entry()
                    else:
                        errors[CONF_CALENDARIFIC_API_KEY] = "invalid_api_key"
                else:
                    return self._create_entry()

        # Get available energy entities
        energy_entities = await self._get_energy_entities()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_IMPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "utility_meter"],
                        device_class=["energy"],
                    )
                ),
                vol.Optional(CONF_EXPORT_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "utility_meter"],
                        device_class=["energy"],
                    )
                ),
                vol.Optional(CONF_TOU_ENABLED, default=False): selector.BooleanSelector(),
                vol.Optional(CONF_CALENDARIFIC_API_KEY): selector.TextSelector(
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

    async def async_step_tou_config(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle ToU configuration step."""
        errors = {}

        if user_input is not None:
            # Validate API key by testing it
            api_key = user_input.get(CONF_CALENDARIFIC_API_KEY)
            country = user_input.get(CONF_COUNTRY, "MY")
            year = user_input.get(CONF_YEAR)

            if await self._validate_api_key(api_key, country, year):
                # Update stored data
                self._api_key = api_key
                return self._create_entry(
                    {
                        CONF_COUNTRY: country,
                        CONF_YEAR: year,
                    }
                )
            else:
                errors[CONF_CALENDARIFIC_API_KEY] = "invalid_api_key"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CALENDARIFIC_API_KEY, default=self._api_key): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    )
                ),
                vol.Optional(CONF_COUNTRY, default="MY"): selector.TextSelector(),
                vol.Optional(CONF_YEAR, default=2024): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=2020,
                        max=2030,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="tou_config",
            data_schema=data_schema,
            errors=errors,
        )

    def _create_entry(self, extra_data: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Create the config entry."""
        data = {
            CONF_IMPORT_ENTITY: self._import_entity,
            CONF_EXPORT_ENTITY: self._export_entity,
            CONF_TOU_ENABLED: self._tou_enabled,
        }

        if self._api_key:
            data[CONF_CALENDARIFIC_API_KEY] = self._api_key

        if extra_data:
            data.update(extra_data)

        return self.async_create_entry(
            title=DEFAULT_NAME,
            data=data,
        )

    async def _get_energy_entities(self) -> list:
        """Get list of available energy entities."""
        # This would normally query Home Assistant for available entities
        # For now, return empty list as we'll use entity selector
        return []

    async def _validate_api_key(self, api_key: str, country: str, year: int) -> bool:
        """Validate the Calendarific API key."""
        try:
            import aiohttp

            session = async_get_clientsession(self.hass)
            params = {
                "api_key": api_key,
                "country": country,
                "year": year,
                "month": 1,
                "day": 1,
            }

            async with session.get(
                "https://calendarific.com/api/v2/holidays",
                params=params,
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return "response" in data
                return False
        except Exception as ex:
            _LOGGER.error("Error validating API key: %s", ex)
            return False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return TNBCalculatorOptionsFlowHandler(config_entry)


class TNBCalculatorOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for TNB Calculator."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
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
                        CONF_TOU_ENABLED,
                        default=self.config_entry.data.get(CONF_TOU_ENABLED, False),
                    ): selector.BooleanSelector(),
                    vol.Optional(
                        CONF_CALENDARIFIC_API_KEY,
                        default=self.config_entry.data.get(CONF_CALENDARIFIC_API_KEY),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        )
                    ),
                    vol.Optional(
                        CONF_COUNTRY,
                        default=self.config_entry.data.get(CONF_COUNTRY, "MY"),
                    ): selector.TextSelector(),
                    vol.Optional(
                        CONF_YEAR,
                        default=self.config_entry.data.get(CONF_YEAR, 2024),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=2020,
                            max=2030,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
