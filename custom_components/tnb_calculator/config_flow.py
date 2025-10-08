"""Config flow for TNB Calculator integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol
from aiohttp import ClientError
from asyncio import TimeoutError

from homeassistant import config_entries
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import (
    CALENDARIFIC_BASE_URL,
    CALENDARIFIC_HOLIDAYS_ENDPOINT,
    CONF_CALENDARIFIC_API_KEY,
    CONF_EXPORT_ENTITY,
    CONF_IMPORT_ENTITY,
    CONF_BILLING_START_DAY,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

ALLOWED_DOMAINS = {"sensor", "utility_meter"}
ALLOWED_DEVICE_CLASSES = {"energy"}
ALLOWED_STATE_CLASSES = {"total", "total_increasing", "measurement"}
ALLOWED_UNITS = {"kwh", "wh", "mwh"}


async def async_validate_energy_entity(
    hass,
    entity_id: str,
    *,
    allow_unknown_state: bool = False,
) -> Optional[str]:
    """Validate that the selected entity is a usable energy sensor."""

    if not entity_id:
        return "entity_not_found"

    registry = async_get_entity_registry(hass)
    entry = registry.async_get(entity_id)
    if entry is None:
        return "entity_not_found"

    if entry.domain not in ALLOWED_DOMAINS:
        return "entity_invalid_domain"

    state = hass.states.get(entity_id)
    if state is None:
        return "entity_state_missing"

    device_class = (entry.device_class or entry.original_device_class or state.attributes.get("device_class"))
    if device_class and device_class.lower() not in ALLOWED_DEVICE_CLASSES:
        return "entity_invalid_device_class"

    state_class = state.attributes.get("state_class")
    if not state_class and entry.capabilities:
        state_class = entry.capabilities.get("state_class")
    if not state_class:
        return "entity_missing_state_class"
    if state_class not in ALLOWED_STATE_CLASSES:
        return "entity_invalid_state_class"

    unit = state.attributes.get("unit_of_measurement")
    if unit and unit.lower() not in ALLOWED_UNITS:
        return "entity_invalid_unit"

    if state.state in {STATE_UNKNOWN, STATE_UNAVAILABLE}:
        return None if allow_unknown_state else "entity_state_unavailable"

    try:
        float(state.state)
    except (TypeError, ValueError):
        return "entity_state_non_numeric"

    return None


async def async_validate_calendarific_api_key(hass, api_key: str) -> Optional[str]:
    """Validate Calendarific API key and return error code if invalid."""

    session = async_get_clientsession(hass)
    params = {
        "api_key": api_key,
        "country": "MY",
        "year": 2024,
        "month": 1,
        "day": 1,
    }

    try:
        async with session.get(
            f"{CALENDARIFIC_BASE_URL}{CALENDARIFIC_HOLIDAYS_ENDPOINT}",
            params=params,
            timeout=10,
        ) as response:
            if response.status == 200:
                payload: Dict[str, Any] = await response.json()
                meta = payload.get("meta", {})
                code = meta.get("code", 200)
                if code == 200:
                    return None
                if code in (401, 403):
                    return "invalid_api_key"
                if code == 429:
                    return "api_key_rate_limited"
                _LOGGER.debug("Unexpected Calendarific meta response: %s", meta)
                return "api_key_http_error"

            if response.status in (401, 403):
                return "invalid_api_key"
            if response.status == 429:
                return "api_key_rate_limited"
            if 500 <= response.status < 600:
                return "api_key_server_error"

            _LOGGER.debug("Unexpected Calendarific status %s", response.status)
            return "api_key_http_error"

    except TimeoutError:
        return "api_key_timeout"
    except ClientError:
        return "api_key_cannot_connect"
    except Exception:  # pylint: disable=broad-except
        _LOGGER.exception("Unexpected error while validating Calendarific API key")
        return "api_key_unknown_error"


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
        defaults: Dict[str, Any] = {}

        if user_input is not None:
            # Validate import entity
            import_entity = user_input.get(CONF_IMPORT_ENTITY)
            import_error = await async_validate_energy_entity(self.hass, import_entity)
            if import_error:
                errors[CONF_IMPORT_ENTITY] = import_error

            # Validate export entity if provided
            export_entity = user_input.get(CONF_EXPORT_ENTITY)
            if export_entity:
                export_error = await async_validate_energy_entity(
                    self.hass, export_entity, allow_unknown_state=True
                )
                if export_error:
                    errors[CONF_EXPORT_ENTITY] = export_error

            # Validate API key if provided
            api_key = user_input.get(CONF_CALENDARIFIC_API_KEY)
            if api_key and not errors:
                api_error = await async_validate_calendarific_api_key(self.hass, api_key)
                if api_error:
                    errors["base"] = api_error

            if not errors:
                cleaned_input = {
                    key: value
                    for key, value in user_input.items()
                    if value not in (None, "", [])
                }
                return self.async_create_entry(
                    title="TNB Calculator",
                    data=cleaned_input,
                )

            # Prepare defaults for form re-rendering (preserve user selections only when meaningful)
            for key in (CONF_IMPORT_ENTITY, CONF_EXPORT_ENTITY, CONF_CALENDARIFIC_API_KEY, CONF_BILLING_START_DAY):
                value = user_input.get(key)
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                defaults[key] = value

        selector_import = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor", "utility_meter"],
                device_class=["energy"],
            )
        )
        selector_export = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor", "utility_meter"],
                device_class=["energy"],
            )
        )
        selector_api = selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.PASSWORD,
            )
        )
        selector_billing_day = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=31,
                mode=selector.NumberSelectorMode.BOX,
            )
        )

        schema_dict: Dict[Any, Any] = {}
        if CONF_IMPORT_ENTITY in defaults:
            schema_dict[
                vol.Required(CONF_IMPORT_ENTITY, default=defaults[CONF_IMPORT_ENTITY])
            ] = selector_import
        else:
            schema_dict[vol.Required(CONF_IMPORT_ENTITY)] = selector_import

        if CONF_EXPORT_ENTITY in defaults:
            schema_dict[
                vol.Optional(CONF_EXPORT_ENTITY, default=defaults[CONF_EXPORT_ENTITY])
            ] = selector_export
        else:
            schema_dict[vol.Optional(CONF_EXPORT_ENTITY)] = selector_export

        if CONF_CALENDARIFIC_API_KEY in defaults:
            schema_dict[
                vol.Optional(
                    CONF_CALENDARIFIC_API_KEY,
                    default=defaults[CONF_CALENDARIFIC_API_KEY],
                )
            ] = selector_api
        else:
            schema_dict[vol.Optional(CONF_CALENDARIFIC_API_KEY)] = selector_api
        
        # Billing start day (default to 1)
        billing_day_default = defaults.get(CONF_BILLING_START_DAY, 1)
        schema_dict[vol.Optional(CONF_BILLING_START_DAY, default=billing_day_default)] = selector_billing_day

        data_schema = vol.Schema(schema_dict)

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

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
            import_entity = user_input.get(CONF_IMPORT_ENTITY)
            import_error = await async_validate_energy_entity(self.hass, import_entity)
            if import_error:
                errors[CONF_IMPORT_ENTITY] = import_error

            export_entity = user_input.get(CONF_EXPORT_ENTITY)
            if export_entity:
                export_error = await async_validate_energy_entity(
                    self.hass, export_entity, allow_unknown_state=True
                )
                if export_error:
                    errors[CONF_EXPORT_ENTITY] = export_error

            api_key = user_input.get(CONF_CALENDARIFIC_API_KEY)
            if api_key and not errors:
                api_error = await async_validate_calendarific_api_key(self.hass, api_key)
                if api_error:
                    errors["base"] = api_error

            if not errors:
                cleaned_input = {
                    key: value
                    for key, value in user_input.items()
                    if value not in (None, "", [])
                }
                return self.async_create_entry(title="", data=cleaned_input)

        source_defaults: Dict[str, Any] = {}
        if user_input is not None:
            candidate_source = user_input
        else:
            candidate_source = {**self.config_entry.data, **self.config_entry.options}

        for key in (CONF_IMPORT_ENTITY, CONF_EXPORT_ENTITY, CONF_CALENDARIFIC_API_KEY, CONF_BILLING_START_DAY):
            value = candidate_source.get(key)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            source_defaults[key] = value

        selector_import = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor", "utility_meter"],
                device_class=["energy"],
            )
        )
        selector_export = selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain=["sensor", "utility_meter"],
                device_class=["energy"],
            )
        )
        selector_api = selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.PASSWORD,
            )
        )
        selector_billing_day = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=31,
                mode=selector.NumberSelectorMode.BOX,
            )
        )

        schema_dict: Dict[Any, Any] = {}
        if CONF_IMPORT_ENTITY in source_defaults:
            schema_dict[
                vol.Required(CONF_IMPORT_ENTITY, default=source_defaults[CONF_IMPORT_ENTITY])
            ] = selector_import
        else:
            schema_dict[vol.Required(CONF_IMPORT_ENTITY)] = selector_import

        if CONF_EXPORT_ENTITY in source_defaults:
            schema_dict[
                vol.Optional(CONF_EXPORT_ENTITY, default=source_defaults[CONF_EXPORT_ENTITY])
            ] = selector_export
        else:
            schema_dict[vol.Optional(CONF_EXPORT_ENTITY)] = selector_export

        if CONF_CALENDARIFIC_API_KEY in source_defaults:
            schema_dict[
                vol.Optional(
                    CONF_CALENDARIFIC_API_KEY,
                    default=source_defaults[CONF_CALENDARIFIC_API_KEY],
                )
            ] = selector_api
        else:
            schema_dict[vol.Optional(CONF_CALENDARIFIC_API_KEY)] = selector_api
        
        # Billing start day (default to 1)
        billing_day_default = source_defaults.get(CONF_BILLING_START_DAY, 1)
        schema_dict[vol.Optional(CONF_BILLING_START_DAY, default=billing_day_default)] = selector_billing_day

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
        )
