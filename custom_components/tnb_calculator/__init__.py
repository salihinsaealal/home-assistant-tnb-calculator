"""TNB Calculator integration for Home Assistant."""
import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN
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
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
