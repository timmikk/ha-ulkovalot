"""Diagnostic sensor entities exposing coordinator state."""

from __future__ import annotations

from datetime import datetime

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
from .logic import DarknessSource, LuxDarkness, Phase, SunDarkness


def _options(enum: type) -> list[str]:
    """Option list for an ENUM sensor, derived from the enum itself.

    Hand-typing these lets them drift from the values the coordinator
    actually reports, and HA silently drops a state that isn't in the
    list — so always derive.
    """
    return [member.value for member in enum]


_PHASE_OPTIONS = _options(Phase)
_REASON_OPTIONS = ["disabled", "override", "day", "morning", "motion", "evening", "night"]
_SUN_DARKNESS_OPTIONS = _options(SunDarkness)
_LUX_DARKNESS_OPTIONS = _options(LuxDarkness)
_DARKNESS_SOURCE_OPTIONS = _options(DarknessSource)


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
            SunDarknessSensor(coordinator, entry),
            LuxDarknessSensor(coordinator, entry),
            DarknessSourceSensor(coordinator, entry),
            LastEvaluatedSensor(coordinator, entry),
            LuxOnBelowSensor(coordinator, entry),
            LuxOffAboveSensor(coordinator, entry),
            SunElevDarkFloorSensor(coordinator, entry),
            SunElevBrightCeilingSensor(coordinator, entry),
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


class SunDarknessSensor(_DiagnosticSensor):
    """Sun elevation's standalone verdict, before lux is consulted.

    ``ambiguous`` means the elevation sits between the two configured
    bounds and the sun deferred to lux — see ``LuxDarknessSensor``.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _SUN_DARKNESS_OPTIONS

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "sun_darkness", "Sun darkness")

    @property
    def native_value(self) -> str:
        return self.coordinator.diagnostics.sun_darkness.value

    @property
    def extra_state_attributes(self) -> dict[str, float | None]:
        config = self.coordinator.config
        return {
            "elevation": self.coordinator.diagnostics.sun_elevation,
            "dark_floor": config.sun_elev_dark_floor,
            "bright_ceiling": config.sun_elev_bright_ceiling,
        }


class LuxDarknessSensor(_DiagnosticSensor):
    """Lux's standalone verdict, independent of sun elevation.

    ``hold`` means lux sat inside the hysteresis band and declined to
    decide, so the previous dark state was retained.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _LUX_DARKNESS_OPTIONS

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "lux_darkness", "Lux darkness")

    @property
    def native_value(self) -> str:
        return self.coordinator.diagnostics.lux_darkness.value

    @property
    def extra_state_attributes(self) -> dict[str, float | None]:
        config = self.coordinator.config
        return {
            "illuminance": self.coordinator.diagnostics.illuminance,
            "lux_on_below": config.lux_on_below,
            "lux_off_above": config.lux_off_above,
        }


class DarknessSourceSensor(_DiagnosticSensor):
    """Which input actually decided the combined dark/bright answer."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _DARKNESS_SOURCE_OPTIONS

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "darkness_source", "Darkness source")

    @property
    def native_value(self) -> str:
        return self.coordinator.diagnostics.darkness_source.value


class LastEvaluatedSensor(_DiagnosticSensor):
    """When the coordinator last ran a scene-decision cycle.

    Makes a stalled evaluation visible — every other diagnostic here is
    only as current as this timestamp.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "last_evaluated", "Last evaluated")

    @property
    def native_value(self) -> datetime:
        return self.coordinator.diagnostics.updated_at


class _ThresholdSensor(_DiagnosticSensor):
    """A configured threshold, published as a real entity.

    These read ``RuntimeConfig`` rather than the per-cycle snapshot, so
    that a history graph can draw the threshold as a line against the
    measurement it gates. The config entry reloads on an options change,
    which rebuilds the coordinator with the new values.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UlkovalotCoordinator,
        entry: ConfigEntry,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator, entry, key, name)
        self._config_key = key

    @property
    def native_value(self) -> float:
        return getattr(self.coordinator.config, self._config_key)


class LuxOnBelowSensor(_ThresholdSensor):
    """Lux at or under which the lights are considered needed."""

    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LUX_UNIT

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "lux_on_below", "Lux on below")


class LuxOffAboveSensor(_ThresholdSensor):
    """Lux at or above which the lights are considered unnecessary."""

    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LUX_UNIT

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "lux_off_above", "Lux off above")


class SunElevDarkFloorSensor(_ThresholdSensor):
    """Elevation at or under which it is dark regardless of lux."""

    _attr_native_unit_of_measurement = SUN_ELEV_UNIT

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "sun_elev_dark_floor", "Sun elevation dark floor"
        )


class SunElevBrightCeilingSensor(_ThresholdSensor):
    """Elevation at or above which it is bright regardless of lux."""

    _attr_native_unit_of_measurement = SUN_ELEV_UNIT

    def __init__(self, coordinator: UlkovalotCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "sun_elev_bright_ceiling",
            "Sun elevation bright ceiling",
        )
