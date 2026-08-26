"""Tests for the diagnostic sensor platform.

Builds the coordinator directly (rather than through the full config-entry
lifecycle) and drives its ``diagnostics`` snapshot, since these are unit
tests of the entity classes' state mapping — the entry-forwarding wiring is
covered separately in ``tests/test_init.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_snapshot

from custom_components.ulkovalot.const import (
    CONF_DISABLE_FLAG,
    CONF_ILLUMINANCE_SENSORS,
    CONF_LUX_OFF_ABOVE,
    CONF_LUX_ON_BELOW,
    CONF_MOTION_SENSORS,
    CONF_NIGHT_SCENE_END_TIME,
    CONF_NIGHT_SCENE_START_TIME,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_DURATION,
    CONF_OVERRIDE_SCENE,
    CONF_OVERRIDE_TRIGGER,
    CONF_SCENE_DAY,
    CONF_SCENE_EVENING,
    CONF_SCENE_MORNING,
    CONF_SCENE_MOTION,
    CONF_SCENE_NIGHT,
    CONF_SUN_ELEV_BRIGHT_CEILING,
    CONF_SUN_ELEV_DARK_FLOOR,
    CONF_TRANSITION_TIME,
    CONF_TRANSITION_TIME_MOTION,
    DATA_KEYS,
    DOMAIN,
    OPTION_KEYS,
)
from custom_components.ulkovalot.coordinator import (
    DiagnosticsSnapshot,
    UlkovalotCoordinator,
)
from custom_components.ulkovalot.logic import (
    DarknessSource,
    LuxDarkness,
    Phase,
    SunDarkness,
)
from custom_components.ulkovalot.sensor import (
    CurrentSceneSensor,
    DarknessSourceSensor,
    IlluminanceSensor,
    LastEvaluatedSensor,
    LuxDarknessSensor,
    LuxOffAboveSensor,
    LuxOnBelowSensor,
    PhaseSensor,
    ReasonSensor,
    SunDarknessSensor,
    SunElevBrightCeilingSensor,
    SunElevationSensor,
    SunElevDarkFloorSensor,
)


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {
        CONF_MOTION_SENSORS: [],
        CONF_ILLUMINANCE_SENSORS: [],
        CONF_DISABLE_FLAG: None,
        CONF_SCENE_DAY: "scene.day",
        CONF_SCENE_MORNING: "scene.morning",
        CONF_SCENE_EVENING: "scene.evening",
        CONF_SCENE_NIGHT: "scene.night",
        CONF_SCENE_MOTION: "scene.motion",
        CONF_OVERRIDE_SCENE: "scene.override_default",
        CONF_OVERRIDE_TRIGGER: None,
        CONF_NIGHT_SCENE_START_TIME: "23:00:00",
        CONF_NIGHT_SCENE_END_TIME: "07:00:00",
        CONF_LUX_ON_BELOW: 30,
        CONF_LUX_OFF_ABOVE: 100,
        CONF_SUN_ELEV_DARK_FLOOR: -3,
        CONF_SUN_ELEV_BRIGHT_CEILING: 6,
        CONF_NO_MOTION_WAIT: 120,
        CONF_TRANSITION_TIME: 10,
        CONF_TRANSITION_TIME_MOTION: 1,
        CONF_OVERRIDE_DURATION: 7200,
    }
    base.update(overrides)
    return base


def _entry(**overrides: Any) -> MockConfigEntry:
    payload = _payload(**overrides)
    return MockConfigEntry(
        domain=DOMAIN,
        title="Outdoor lights coordinator",
        data={k: payload[k] for k in DATA_KEYS},
        options={k: payload[k] for k in OPTION_KEYS},
    )


def _snapshot(**overrides: Any) -> DiagnosticsSnapshot:
    return make_snapshot(**overrides)


def test_illuminance_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(illuminance=1234.5)
    sensor = IlluminanceSensor(coordinator, entry)

    assert sensor.native_value == 1234.5
    assert sensor.unique_id == f"{entry.entry_id}-illuminance"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_illuminance_sensor_none_when_no_valid_readings(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(illuminance=None)
    sensor = IlluminanceSensor(coordinator, entry)

    assert sensor.native_value is None


def test_sun_elevation_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(sun_elevation=-4.5)
    sensor = SunElevationSensor(coordinator, entry)

    assert sensor.native_value == -4.5
    assert sensor.unique_id == f"{entry.entry_id}-sun_elevation"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_phase_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(phase=Phase.NIGHT)
    sensor = PhaseSensor(coordinator, entry)

    assert sensor.native_value == "night"
    assert sensor.unique_id == f"{entry.entry_id}-phase"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_reason_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(reason="motion")
    sensor = ReasonSensor(coordinator, entry)

    assert sensor.native_value == "motion"
    assert sensor.unique_id == f"{entry.entry_id}-reason"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_current_scene_sensor_reflects_applied_scene(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(applied_scene="scene.motion")
    sensor = CurrentSceneSensor(coordinator, entry)

    assert sensor.native_value == "scene.motion"
    assert sensor.unique_id == f"{entry.entry_id}-current_scene"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_current_scene_sensor_is_none_string_when_unset(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(applied_scene=None)
    sensor = CurrentSceneSensor(coordinator, entry)

    assert sensor.native_value == "none"


# --- threshold attributes on the existing sensors --------------------------


def test_illuminance_sensor_exposes_lux_thresholds(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    sensor = IlluminanceSensor(coordinator, entry)

    assert sensor.extra_state_attributes == {
        "lux_on_below": 30.0,
        "lux_off_above": 100.0,
    }


def test_sun_elevation_sensor_exposes_elevation_thresholds(
    hass: HomeAssistant,
) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    sensor = SunElevationSensor(coordinator, entry)

    assert sensor.extra_state_attributes == {
        "sun_elev_dark_floor": -3.0,
        "sun_elev_bright_ceiling": 6.0,
    }


def test_phase_sensor_exposes_night_window_bounds(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    sensor = PhaseSensor(coordinator, entry)

    assert sensor.extra_state_attributes == {
        "night_start": "23:00:00",
        "night_end": "07:00:00",
    }


def test_current_scene_sensor_exposes_scene_key_and_transition(
    hass: HomeAssistant,
) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(scene_key="scene_motion", transition=1.0)
    sensor = CurrentSceneSensor(coordinator, entry)

    assert sensor.extra_state_attributes == {
        "scene_key": "scene_motion",
        "transition": 1.0,
    }


# --- new ingredient sensors ------------------------------------------------


def test_sun_darkness_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(
        sun_darkness=SunDarkness.AMBIGUOUS, sun_elevation=1.5
    )
    sensor = SunDarknessSensor(coordinator, entry)

    assert sensor.native_value == "ambiguous"
    assert sensor.unique_id == f"{entry.entry_id}-sun_darkness"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.extra_state_attributes == {
        "elevation": 1.5,
        "dark_floor": -3.0,
        "bright_ceiling": 6.0,
    }


def test_lux_darkness_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(lux_darkness=LuxDarkness.HOLD, illuminance=60.0)
    sensor = LuxDarknessSensor(coordinator, entry)

    assert sensor.native_value == "hold"
    assert sensor.unique_id == f"{entry.entry_id}-lux_darkness"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.extra_state_attributes == {
        "illuminance": 60.0,
        "lux_on_below": 30.0,
        "lux_off_above": 100.0,
    }


def test_lux_darkness_sensor_unknown_when_no_readings(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(
        lux_darkness=LuxDarkness.UNKNOWN, illuminance=None
    )
    sensor = LuxDarknessSensor(coordinator, entry)

    assert sensor.native_value == "unknown"
    assert sensor.extra_state_attributes["illuminance"] is None


def test_darkness_source_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(
        darkness_source=DarknessSource.LUX_HYSTERESIS_HOLD
    )
    sensor = DarknessSourceSensor(coordinator, entry)

    assert sensor.native_value == "lux_hysteresis_hold"
    assert sensor.unique_id == f"{entry.entry_id}-darkness_source"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_last_evaluated_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    stamp = datetime(2026, 8, 26, 21, 40, tzinfo=timezone.utc)
    coordinator.diagnostics = _snapshot(updated_at=stamp)
    sensor = LastEvaluatedSensor(coordinator, entry)

    assert sensor.native_value == stamp
    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize(
    ("sensor_class", "key", "expected", "unit"),
    [
        (LuxOnBelowSensor, "lux_on_below", 30.0, "lx"),
        (LuxOffAboveSensor, "lux_off_above", 100.0, "lx"),
        (SunElevDarkFloorSensor, "sun_elev_dark_floor", -3.0, "°"),
        (SunElevBrightCeilingSensor, "sun_elev_bright_ceiling", 6.0, "°"),
    ],
)
def test_threshold_sensors_publish_configured_values(
    hass: HomeAssistant, sensor_class, key, expected, unit
) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    sensor = sensor_class(coordinator, entry)

    assert sensor.native_value == expected
    assert sensor.native_unit_of_measurement == unit
    assert sensor.unique_id == f"{entry.entry_id}-{key}"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_threshold_sensors_follow_a_config_change(hass: HomeAssistant) -> None:
    """Thresholds read RuntimeConfig, so an entry reload republishes them."""
    entry = _entry(**{CONF_LUX_ON_BELOW: 55})
    coordinator = UlkovalotCoordinator(hass, entry)
    sensor = LuxOnBelowSensor(coordinator, entry)

    assert sensor.native_value == 55.0


@pytest.mark.parametrize(
    ("sensor_class", "value"),
    [
        (PhaseSensor, "phase"),
        (SunDarknessSensor, "sun_darkness"),
        (LuxDarknessSensor, "lux_darkness"),
        (DarknessSourceSensor, "darkness_source"),
        (ReasonSensor, "reason"),
    ],
)
def test_enum_sensor_values_are_declared_options(
    hass: HomeAssistant, sensor_class, value
) -> None:
    """HA drops a state that isn't in the sensor's own options list."""
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    sensor = sensor_class(coordinator, entry)

    assert sensor.native_value in sensor.options
