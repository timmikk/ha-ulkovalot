"""Tests for the diagnostic binary_sensor platform.

Builds the coordinator directly (rather than through the full config-entry
lifecycle) and drives its ``diagnostics`` snapshot — see ``test_sensor.py``
for the same pattern and rationale.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import make_snapshot

from custom_components.ulkovalot.binary_sensor import (
    DarkBinarySensor,
    DisabledBinarySensor,
    MotionBinarySensor,
    OverrideActiveBinarySensor,
)
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


def _entry() -> MockConfigEntry:
    payload = _payload()
    return MockConfigEntry(
        domain=DOMAIN,
        title="Outdoor lights coordinator",
        data={k: payload[k] for k in DATA_KEYS},
        options={k: payload[k] for k in OPTION_KEYS},
    )


def _snapshot(**overrides: Any) -> DiagnosticsSnapshot:
    return make_snapshot(**overrides)


def test_motion_binary_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(motion=True)
    sensor = MotionBinarySensor(coordinator, entry)

    assert sensor.is_on is True
    assert sensor.unique_id == f"{entry.entry_id}-motion"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_dark_binary_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(dark=True)
    sensor = DarkBinarySensor(coordinator, entry)

    assert sensor.is_on is True
    assert sensor.unique_id == f"{entry.entry_id}-dark"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_disabled_binary_sensor_reflects_diagnostics(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(disabled=True)
    sensor = DisabledBinarySensor(coordinator, entry)

    assert sensor.is_on is True
    assert sensor.unique_id == f"{entry.entry_id}-disabled"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


def test_override_active_binary_sensor_attributes(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    until = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
    coordinator.diagnostics = _snapshot(
        override_active=True, override_scene="scene.party", override_until=until
    )
    sensor = OverrideActiveBinarySensor(coordinator, entry)

    assert sensor.is_on is True
    assert sensor.unique_id == f"{entry.entry_id}-override_active"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.extra_state_attributes == {
        "scene": "scene.party",
        "until": until.isoformat(),
    }


def test_override_active_binary_sensor_attributes_when_inactive(
    hass: HomeAssistant,
) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    coordinator.diagnostics = _snapshot(
        override_active=False, override_scene=None, override_until=None
    )
    sensor = OverrideActiveBinarySensor(coordinator, entry)

    assert sensor.is_on is False
    assert sensor.extra_state_attributes == {"scene": None, "until": None}


def test_motion_binary_sensor_exposes_no_motion_wait(hass: HomeAssistant) -> None:
    entry = _entry()
    coordinator = UlkovalotCoordinator(hass, entry)
    sensor = MotionBinarySensor(coordinator, entry)

    assert sensor.extra_state_attributes == {"no_motion_wait": 120.0}
