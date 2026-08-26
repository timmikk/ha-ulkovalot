"""Diagnostic sensor entities exposing coordinator state."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LUX_UNIT, SUN_ELEV_UNIT
from .coordinator import UlkovalotCoordinator
from .entity import UlkovalotEntity

_PHASE_OPTIONS = ["day", "morning", "evening", "night"]
_REASON_OPTIONS = ["disabled", "override", "day", "morning", "motion", "evening", "night"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up ulkovalot diagnostic sensors."""
    coordinator: UlkovalotCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            IlluminanceSensor(coordinator, entry),
            SunElevationSensor(coordinator, entry),
            PhaseSensor(coordinator, entry),
            ReasonSensor(coordinator, entry),
            CurrentSceneSensor(coordinator, entry),
        ]
    )


class _DiagnosticSensor(UlkovalotEntity, SensorEntity):
    """Common diagnostic-category setup for all sensors in this platform."""

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


class IlluminanceSensor(_DiagnosticSensor):
    """Aggregated median lux, or ``None`` if no valid readings."""

    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LUX_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "illuminance", "Illuminance")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.diagnostics.illuminance

    @property
    def extra_state_attributes(self) -> dict[str, float]:
        config = self.coordinator.config
        return {
            "lux_on_below": config.lux_on_below,
            "lux_off_above": config.lux_off_above,
        }


class SunElevationSensor(_DiagnosticSensor):
    """Last-read sun elevation."""

    _attr_native_unit_of_measurement = SUN_ELEV_UNIT
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "sun_elevation", "Sun elevation")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.diagnostics.sun_elevation

    @property
    def extra_state_attributes(self) -> dict[str, float]:
        config = self.coordinator.config
        return {
            "sun_elev_dark_floor": config.sun_elev_dark_floor,
            "sun_elev_bright_ceiling": config.sun_elev_bright_ceiling,
        }


class PhaseSensor(_DiagnosticSensor):
    """Coarse time-of-day phase."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _PHASE_OPTIONS

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "phase", "Phase")

    @property
    def native_value(self) -> str:
        return self.coordinator.diagnostics.phase.value

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        config = self.coordinator.config
        return {
            "night_start": config.night_start.isoformat(),
            "night_end": config.night_end.isoformat(),
        }


class ReasonSensor(_DiagnosticSensor):
    """Mirrors the branch that pick_scene/selection_reason actually took."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _REASON_OPTIONS

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "reason", "Reason")

    @property
    def native_value(self) -> str:
        return self.coordinator.diagnostics.reason


class CurrentSceneSensor(_DiagnosticSensor):
    """The scene entity id last dispatched via scene.turn_on, or ``none``."""

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "current_scene", "Current scene")

    @property
    def native_value(self) -> str:
        return self.coordinator.diagnostics.applied_scene or "none"

    @property
    def extra_state_attributes(self) -> dict[str, str | float]:
        diagnostics = self.coordinator.diagnostics
        return {
            "scene_key": diagnostics.scene_key,
            "transition": diagnostics.transition,
        }
