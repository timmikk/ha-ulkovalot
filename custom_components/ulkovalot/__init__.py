"""Outdoor lights coordinator."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS
from .coordinator import UlkovalotCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_OVERRIDE = "override"
SERVICE_CANCEL_OVERRIDE = "cancel_override"

_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Optional("scene"): cv.entity_id,
        vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)


async def async_setup(_hass: HomeAssistant, _config: dict) -> bool:
    """Set up the ulkovalot integration from YAML (unused — config flow only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ulkovalot from a config entry."""
    _LOGGER.debug("Setting up entry %s", entry.entry_id)
    store = hass.data.setdefault(DOMAIN, {})
    coordinator = UlkovalotCoordinator(hass, entry)
    await coordinator.async_start()
    store[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    # RuntimeConfig is snapshotted once per coordinator, so options saved in
    # the UI only take effect on reload — without this listener they'd sit
    # unused until Home Assistant restarted.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    _LOGGER.info("ulkovalot entry %s set up", entry.entry_id)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so the coordinator picks up the new options."""
    _LOGGER.debug("Options updated for entry %s — reloading", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading entry %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False
    store = hass.data[DOMAIN]
    coordinator: UlkovalotCoordinator = store.pop(entry.entry_id)
    coordinator.unload()
    if not store:
        hass.services.async_remove(DOMAIN, SERVICE_OVERRIDE)
        hass.services.async_remove(DOMAIN, SERVICE_CANCEL_OVERRIDE)
    return unload_ok


def _register_services(hass: HomeAssistant) -> None:
    """Register override + cancel_override once, on first entry setup."""
    if hass.services.has_service(DOMAIN, SERVICE_OVERRIDE):
        return

    async def _handle_override(call: ServiceCall) -> None:
        _LOGGER.info(
            "Service override called: scene=%s duration=%s",
            call.data.get("scene"),
            call.data.get("duration"),
        )
        for coordinator in hass.data[DOMAIN].values():
            coordinator.start_override(
                scene=call.data.get("scene"),
                duration=call.data.get("duration"),
            )

    async def _handle_cancel(call: ServiceCall) -> None:
        _LOGGER.info("Service cancel_override called")
        for coordinator in hass.data[DOMAIN].values():
            coordinator.cancel_override()

    hass.services.async_register(
        DOMAIN, SERVICE_OVERRIDE, _handle_override, schema=_OVERRIDE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL_OVERRIDE, _handle_cancel
    )
