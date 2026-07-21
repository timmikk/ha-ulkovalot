"""Outdoor lights coordinator."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import UlkovalotCoordinator

SERVICE_OVERRIDE = "override"
SERVICE_CANCEL_OVERRIDE = "cancel_override"

_OVERRIDE_SCHEMA = vol.Schema(
    {
        vol.Optional("scene"): cv.entity_id,
        vol.Optional("duration"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    }
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the ulkovalot integration from YAML (unused — config flow only)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ulkovalot from a config entry."""
    store = hass.data.setdefault(DOMAIN, {})
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.wire_trigger()
    store[entry.entry_id] = coordinator
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    store = hass.data[DOMAIN]
    coordinator: UlkovalotCoordinator = store.pop(entry.entry_id)
    coordinator.unload()
    if not store:
        hass.services.async_remove(DOMAIN, SERVICE_OVERRIDE)
        hass.services.async_remove(DOMAIN, SERVICE_CANCEL_OVERRIDE)
    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register override + cancel_override once, on first entry setup."""
    if hass.services.has_service(DOMAIN, SERVICE_OVERRIDE):
        return

    async def _handle_override(call: ServiceCall) -> None:
        for coordinator in hass.data[DOMAIN].values():
            coordinator.start_override(
                scene=call.data.get("scene"),
                duration=call.data.get("duration"),
            )

    async def _handle_cancel(call: ServiceCall) -> None:
        for coordinator in hass.data[DOMAIN].values():
            coordinator.cancel_override()

    hass.services.async_register(
        DOMAIN, SERVICE_OVERRIDE, _handle_override, schema=_OVERRIDE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CANCEL_OVERRIDE, _handle_cancel
    )
