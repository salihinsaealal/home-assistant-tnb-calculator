"""TNB Calculator integration for Home Assistant."""
import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.components.webhook import async_register, async_unregister
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN, WEBHOOK_ID
from .sensor import TNBDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Service schemas
SERVICE_COMPARE_BILL_SCHEMA = vol.Schema({
    vol.Required("actual_bill"): cv.positive_float,
    vol.Optional("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("year"): vol.All(vol.Coerce(int), vol.Range(min=2020, max=2030)),
})

SERVICE_RESET_STORAGE_SCHEMA = vol.Schema({
    vol.Required("confirm"): cv.string,
})

SERVICE_SET_IMPORT_ENERGY_VALUES_SCHEMA = vol.Schema({
    vol.Required("import_total"): cv.positive_float,
    vol.Optional("distribution", default="auto"): vol.In([
        "auto",
        "peak_only", 
        "offpeak_only", 
        "proportional", 
        "manual"
    ]),
    vol.Optional("import_peak"): cv.positive_float,
    vol.Optional("import_offpeak"): cv.positive_float,
})

SERVICE_SET_EXPORT_ENERGY_VALUES_SCHEMA = vol.Schema({
    vol.Required("export_total"): cv.positive_float,
})

SERVICE_ADJUST_IMPORT_ENERGY_VALUES_SCHEMA = vol.Schema({
    vol.Required("import_adjustment"): vol.Coerce(float),
    vol.Optional("distribution", default="auto"): vol.In([
        "auto",
        "peak_only", 
        "offpeak_only", 
        "proportional", 
        "manual"
    ]),
    vol.Optional("peak_adjustment"): vol.Coerce(float),
    vol.Optional("offpeak_adjustment"): vol.Coerce(float),
})

SERVICE_ADJUST_EXPORT_ENERGY_VALUES_SCHEMA = vol.Schema({
    vol.Required("export_adjustment"): vol.Coerce(float),
})

SERVICE_SET_AFA_RATE_SCHEMA = vol.Schema({
    vol.Required("afa_rate"): vol.All(
        vol.Coerce(float), 
        vol.Range(min=0, max=1)
    ),
})

SERVICE_RESET_TARIFF_RATES_SCHEMA = vol.Schema({
    vol.Required("confirm"): cv.string,
})

SERVICE_FETCH_AFA_RATE_SCHEMA = vol.Schema({
    vol.Optional("api_url"): cv.url,
})

SERVICE_FETCH_ALL_RATES_SCHEMA = vol.Schema({
    vol.Optional("api_url"): cv.url,
})


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

        # Merge data and options (options override data)
        config = {**entry.data, **entry.options}
        config["entry_id"] = entry.entry_id

        # Initialize coordinator and perform first refresh before forwarding platforms
        coordinator = TNBDataCoordinator(hass, config)
        await coordinator.async_config_entry_first_refresh()

        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "coordinator": coordinator,
            "config": config,
        }

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        # Register update listener for options changes
        entry.async_on_unload(entry.add_update_listener(async_reload_entry))
        
        # Register services
        async def handle_compare_bill(call: ServiceCall) -> None:
            """Handle the compare_with_bill service call."""
            actual_bill = call.data["actual_bill"]
            month = call.data.get("month")
            year = call.data.get("year")
            
            # Find the coordinator for this entry
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for bill comparison")
                return
            
            coordinator = coordinator_data["coordinator"]
            
            # Get calculated cost
            calculated_cost = coordinator.data.get("total_cost_tou", 0.0)
            if calculated_cost == 0.0:
                calculated_cost = coordinator.data.get("total_cost_non_tou", 0.0)
            
            # Calculate difference
            difference = calculated_cost - actual_bill
            percentage_diff = (difference / actual_bill * 100) if actual_bill > 0 else 0
            
            # Log the comparison
            _LOGGER.info(
                "Bill Comparison - Actual: RM %.2f, Calculated: RM %.2f, Difference: RM %.2f (%.1f%%)",
                actual_bill, calculated_cost, difference, percentage_diff
            )
            
            # Create persistent notification
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "TNB Bill Comparison",
                    "message": f"""**Bill Comparison Results**

Actual Bill: RM {actual_bill:.2f}
Calculated: RM {calculated_cost:.2f}
Difference: RM {difference:.2f} ({percentage_diff:+.1f}%)

{"✅ Calculation is accurate!" if abs(percentage_diff) < 5 else "⚠️ Significant difference detected"}

Monthly Import: {coordinator.data.get('import_energy', 0):.2f} kWh
Monthly Export: {coordinator.data.get('export_energy', 0):.2f} kWh
""",
                    "notification_id": "tnb_bill_comparison",
                },
            )
        
        # Register the service
        hass.services.async_register(
            DOMAIN,
            "compare_with_bill",
            handle_compare_bill,
            schema=SERVICE_COMPARE_BILL_SCHEMA,
        )

        async def handle_reset_storage(call: ServiceCall) -> None:
            """Handle clearing stored integration data."""
            confirmation = call.data.get("confirm", "").strip().upper()
            if confirmation != "RESET":
                raise HomeAssistantError("Confirmation string must be 'RESET'")

            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for reset_storage")
                return

            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            await coordinator.async_reset_storage()
            _LOGGER.info("TNB Calculator data reset requested via service")
            await coordinator.async_refresh()

        hass.services.async_register(
            DOMAIN,
            "reset_storage",
            handle_reset_storage,
            schema=SERVICE_RESET_STORAGE_SCHEMA,
        )
        
        async def handle_set_import_energy_values(call: ServiceCall) -> None:
            """Handle setting exact import energy values."""
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for set_import_energy_values")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            await coordinator.async_set_energy_values(call)
        
        hass.services.async_register(
            DOMAIN,
            "set_import_energy_values",
            handle_set_import_energy_values,
            schema=SERVICE_SET_IMPORT_ENERGY_VALUES_SCHEMA,
        )
        
        async def handle_adjust_import_energy_values(call: ServiceCall) -> None:
            """Handle adjusting import energy values with offsets."""
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for adjust_import_energy_values")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            await coordinator.async_adjust_import_energy_values(call)
        
        hass.services.async_register(
            DOMAIN,
            "adjust_import_energy_values",
            handle_adjust_import_energy_values,
            schema=SERVICE_ADJUST_IMPORT_ENERGY_VALUES_SCHEMA,
        )
        
        async def handle_set_export_energy_values(call: ServiceCall) -> None:
            """Handle setting exact export values."""
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for set_export_energy_values")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            await coordinator.async_set_export_values(call)
        
        hass.services.async_register(
            DOMAIN,
            "set_export_energy_values",
            handle_set_export_energy_values,
            schema=SERVICE_SET_EXPORT_ENERGY_VALUES_SCHEMA,
        )
        
        async def handle_adjust_export_energy_values(call: ServiceCall) -> None:
            """Handle adjusting export energy values."""
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for adjust_export_energy_values")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            await coordinator.async_adjust_export_energy_values(call)
        
        hass.services.async_register(
            DOMAIN,
            "adjust_export_energy_values",
            handle_adjust_export_energy_values,
            schema=SERVICE_ADJUST_EXPORT_ENERGY_VALUES_SCHEMA,
        )
        
        async def handle_set_afa_rate(call: ServiceCall) -> None:
            """Handle manual AFA rate setting."""
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for set_afa_rate")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            afa_rate = call.data.get("afa_rate")
            await coordinator.async_set_afa_rate(afa_rate=afa_rate)
        
        hass.services.async_register(
            DOMAIN,
            "set_afa_rate",
            handle_set_afa_rate,
            schema=SERVICE_SET_AFA_RATE_SCHEMA,
        )
        
        async def handle_reset_tariff_rates(call: ServiceCall) -> None:
            """Handle resetting tariff rates to defaults."""
            confirmation = call.data.get("confirm", "").strip().upper()
            if confirmation != "RESET":
                raise HomeAssistantError("Confirmation string must be 'RESET'")
            
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for reset_tariff_rates")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            await coordinator.async_reset_tariff_rates()
            _LOGGER.info("TNB Calculator tariff rates reset to defaults via service")
        
        hass.services.async_register(
            DOMAIN,
            "reset_tariff_rates",
            handle_reset_tariff_rates,
            schema=SERVICE_RESET_TARIFF_RATES_SCHEMA,
        )
        
        async def handle_fetch_afa_rate(call: ServiceCall) -> None:
            """Handle fetching AFA rate from /afa/simple API."""
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for fetch_afa_rate")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            api_url = call.data.get("api_url")
            success = await coordinator.async_fetch_afa_rate(api_url=api_url)
            
            if not success:
                raise HomeAssistantError("Failed to fetch AFA rate from API")
            
            _LOGGER.info("TNB Calculator AFA rate fetched from API via service")
        
        hass.services.async_register(
            DOMAIN,
            "fetch_afa_rate",
            handle_fetch_afa_rate,
            schema=SERVICE_FETCH_AFA_RATE_SCHEMA,
        )
        
        async def handle_fetch_all_rates(call: ServiceCall) -> None:
            """Handle fetching all tariff rates from /complete API."""
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for fetch_all_rates")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            api_url = call.data.get("api_url")
            success = await coordinator.async_fetch_all_rates(api_url=api_url)
            
            if not success:
                raise HomeAssistantError("Failed to fetch all rates from API")
            
            _LOGGER.info("TNB Calculator all tariff rates fetched from API via service")
        
        hass.services.async_register(
            DOMAIN,
            "fetch_all_rates",
            handle_fetch_all_rates,
            schema=SERVICE_FETCH_ALL_RATES_SCHEMA,
        )
        
        # Register webhook for tariff updates
        async def handle_tariff_webhook(hass: HomeAssistant, webhook_id: str, request) -> None:
            """Handle incoming webhook for tariff rate updates."""
            try:
                data = await request.json()
            except Exception as ex:
                _LOGGER.error("Invalid JSON in tariff webhook: %s", ex)
                return
            
            coordinator_data = hass.data[DOMAIN].get(entry.entry_id)
            if not coordinator_data or "coordinator" not in coordinator_data:
                _LOGGER.error("Could not find TNB Calculator coordinator for webhook")
                return
            
            coordinator: TNBDataCoordinator = coordinator_data["coordinator"]
            success = await coordinator.async_update_tariff_from_webhook(data)
            
            if success:
                _LOGGER.info("Tariff rates updated via webhook")
            else:
                _LOGGER.warning("Webhook tariff update failed - check payload format")
        
        # Generate unique webhook ID per entry
        webhook_id = f"{WEBHOOK_ID}_{entry.entry_id}"
        async_register(
            hass,
            DOMAIN,
            "TNB Calculator Tariff Webhook",
            webhook_id,
            handle_tariff_webhook,
        )
        
        # Store webhook ID for cleanup
        hass.data[DOMAIN][entry.entry_id]["webhook_id"] = webhook_id
        
        # Log webhook URL for user
        webhook_url = f"{hass.config.external_url or hass.config.internal_url}/api/webhook/{webhook_id}"
        _LOGGER.info("TNB Calculator tariff webhook registered: %s", webhook_url)

        return True

    except ConfigEntryNotReady:
        raise
    except Exception as ex:
        _LOGGER.error("Error setting up TNB Calculator: %s", ex, exc_info=True)
        raise ConfigEntryNotReady(f"Failed to set up TNB Calculator: {ex}") from ex


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    _LOGGER.info("Reloading TNB Calculator integration due to options change")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading TNB Calculator integration")

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Unregister webhook
        entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
        webhook_id = entry_data.get("webhook_id")
        if webhook_id:
            async_unregister(hass, webhook_id)
            _LOGGER.debug("Unregistered tariff webhook: %s", webhook_id)
        
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
