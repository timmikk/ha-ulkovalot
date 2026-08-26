"""Shared base class for ulkovalot diagnostic entities."""

from __future__ import annotations

from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import UlkovalotCoordinator


class UlkovalotEntity(Entity):
    """Base entity reading straight from the coordinator's diagnostics snapshot."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self.entry = entry
        self._remove_listener: Callable[[], None] | None = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=self.entry.title,
            manufacturer="ulkovalot",
            model="Outdoor lights coordinator",
        )

    async def async_added_to_hass(self) -> None:
        self._remove_listener = self.coordinator.async_add_listener(
            self._handle_coordinator_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
