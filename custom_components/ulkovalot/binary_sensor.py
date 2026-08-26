"""Diagnostic binary sensor entities exposing coordinator state."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import UlkovalotCoordinator
from .entity import UlkovalotEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ulkovalot diagnostic binary sensors."""
    coordinator: UlkovalotCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            MotionBinarySensor(coordinator, entry),
            DarkBinarySensor(coordinator, entry),
            OverrideActiveBinarySensor(coordinator, entry),
            DisabledBinarySensor(coordinator, entry),
            NightWindowBinarySensor(coordinator, entry),
            SunRisingBinarySensor(coordinator, entry),
        ]
    )


class _DiagnosticBinarySensor(UlkovalotEntity, BinarySensorEntity):
    """Common diagnostic-category setup for all binary sensors in this platform."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UlkovalotCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}-{key}"
        self._attr_name = name


class MotionBinarySensor(_DiagnosticBinarySensor):
    """True when any configured motion sensor is active or within the wait window."""

    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "motion", "Motion")

    @property
    def is_on(self) -> bool:
        return self.coordinator.diagnostics.motion

    @property
    def extra_state_attributes(self) -> dict[str, float]:
        return {"no_motion_wait": self.coordinator.config.no_motion_wait}


class DarkBinarySensor(_DiagnosticBinarySensor):
    """True when ``is_dark()`` says dark (drives phase != DAY)."""

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "dark", "Dark")

    @property
    def is_on(self) -> bool:
        return self.coordinator.diagnostics.dark


class OverrideActiveBinarySensor(_DiagnosticBinarySensor):
    """True while an override is in effect."""

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "override_active", "Override active")

    @property
    def is_on(self) -> bool:
        return self.coordinator.diagnostics.override_active

    @property
    def extra_state_attributes(self) -> dict[str, str | None]:
        diagnostics = self.coordinator.diagnostics
        until = diagnostics.override_until
        return {
            "scene": diagnostics.override_scene,
            "until": until.isoformat() if until is not None else None,
        }


class DisabledBinarySensor(_DiagnosticBinarySensor):
    """True when the configured disable-flag entity was ``on`` for this cycle."""

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "disabled", "Disabled")

    @property
    def is_on(self) -> bool:
        return self.coordinator.diagnostics.disabled


class NightWindowBinarySensor(_DiagnosticBinarySensor):
    """True while the clock sits inside the configured night window.

    This is a **time-only** signal: it never feeds ``is_dark()`` and can
    never make the lights come on by itself. It only splits an already-dark
    state into night vs. morning/evening, which is why it can read ``on``
    at the same time as ``Dark`` reads ``off``.
    """

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "night_window", "Night window")

    @property
    def is_on(self) -> bool:
        return self.coordinator.diagnostics.night_window

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        config = self.coordinator.config
        return {
            "night_start": config.night_start.isoformat(),
            "night_end": config.night_end.isoformat(),
        }


class SunRisingBinarySensor(_DiagnosticBinarySensor):
    """True while the sun is climbing — picks morning over evening."""

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "sun_rising", "Sun rising")

    @property
    def is_on(self) -> bool:
        return self.coordinator.diagnostics.rising
