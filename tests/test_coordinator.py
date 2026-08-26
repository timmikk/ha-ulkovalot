"""Runtime scene-dispatch tests for the Stage 3 coordinator.

Exercises the full HA runtime: state subscriptions, sun elevation
crossings, night time triggers, disable flag, and the composition with
the override state machine. Uses ``async_mock_service`` for scene calls
and ``freezegun`` to pin phase-deciding wall-clock time — all state
setup happens inside the freeze so ``state.last_changed`` timestamps
stay consistent with ``dt_util.utcnow()``.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest

from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.ulkovalot import SERVICE_OVERRIDE
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

MOTION = "binary_sensor.pir_a"
LUX = "sensor.lux_a"
DISABLE = "input_boolean.disable"


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {
        CONF_MOTION_SENSORS: [MOTION],
        CONF_ILLUMINANCE_SENSORS: [LUX],
        CONF_DISABLE_FLAG: DISABLE,
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


def _mock_sun(hass: HomeAssistant, elevation: float, rising: bool = False) -> None:
    hass.states.async_set(
        "sun.sun",
        "above_horizon" if elevation >= 0 else "below_horizon",
        {"elevation": elevation, "rising": rising},
    )


def _seed_environment(
    hass: HomeAssistant,
    frozen: Any,
    *,
    elevation: float,
    rising: bool = False,
    lux: str | None = "5000",
    motion_state: str = "off",
    disable_state: str = "off",
) -> None:
    """Seed sun / lux / motion / disable state — call inside ``freeze_time``.

    Rewinds the frozen clock by well over ``no_motion_wait`` before setting
    the motion state so its ``last_changed`` doesn't count as a "recent"
    motion event, then restores the target time.
    """
    target = dt_util.utcnow()
    frozen.move_to(target - timedelta(seconds=300))
    _mock_sun(hass, elevation=elevation, rising=rising)
    if lux is not None:
        hass.states.async_set(LUX, lux)
    hass.states.async_set(MOTION, motion_state)
    hass.states.async_set(DISABLE, disable_state)
    frozen.move_to(target)


async def _install(hass: HomeAssistant, **overrides: Any) -> MockConfigEntry:
    payload = _payload(**overrides)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Outdoor lights coordinator",
        data={k: payload[k] for k in DATA_KEYS},
        options={k: payload[k] for k in OPTION_KEYS},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_startup_dispatches_scene_for_current_environment(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 12:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=30, lux="5000")
        await _install(hass)

    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "scene.day", "transition": 10.0}


async def test_motion_pulse_when_dark_fires_scene_motion(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 22:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=-10, lux="0")
        await _install(hass)
        calls.clear()
        hass.states.async_set(MOTION, "on")
        await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data == {"entity_id": "scene.motion", "transition": 1.0}


async def test_motion_timeout_refires_underlying_scene(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 22:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=-10, lux="0")
        await _install(hass)
        hass.states.async_set(MOTION, "on")
        await hass.async_block_till_done()
        hass.states.async_set(MOTION, "off")
        await hass.async_block_till_done()
        calls.clear()
        frozen.tick(timedelta(seconds=121))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

    assert calls, "expected motion-timeout re-fire"
    assert calls[-1].data == {"entity_id": "scene.evening", "transition": 10.0}


async def test_sun_crosses_bright_ceiling_flips_to_day(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 08:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=0, rising=True, lux="10")
        await _install(hass)
        assert calls[-1].data["entity_id"] == "scene.morning"
        hass.states.async_set(LUX, "5000")
        _mock_sun(hass, elevation=10, rising=True)
        await hass.async_block_till_done()

    assert calls[-1].data["entity_id"] == "scene.day"


async def test_lux_drop_during_day_flips_to_evening(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 15:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=15, lux="5000")
        await _install(hass)
        assert calls[-1].data["entity_id"] == "scene.day"
        _mock_sun(hass, elevation=3, rising=False)
        hass.states.async_set(LUX, "10")
        await hass.async_block_till_done()

    assert calls[-1].data["entity_id"] == "scene.evening"


async def test_night_time_trigger_fires_night_scene(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 22:30:00") as frozen:
        _seed_environment(hass, frozen, elevation=-10, lux="0")
        await _install(hass)
        assert calls[-1].data["entity_id"] == "scene.evening"
        frozen.move_to("2026-08-17 23:00:00")
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

    assert calls[-1].data == {"entity_id": "scene.night", "transition": 10.0}


async def test_disable_flag_on_suppresses_dispatch_but_tracks_override(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 22:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=-10, lux="0", disable_state="on")
        entry = await _install(hass)
        assert calls == []
        await hass.services.async_call(
            DOMAIN,
            SERVICE_OVERRIDE,
            {"scene": "scene.party", "duration": 60},
            blocking=True,
        )
        coord = hass.data[DOMAIN][entry.entry_id]

    assert coord.override_scene == "scene.party"
    assert calls == []


async def test_override_wins_over_other_triggers_without_touching_timer(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 22:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=-10, lux="0")
        entry = await _install(hass)
        coord = hass.data[DOMAIN][entry.entry_id]
        await hass.services.async_call(
            DOMAIN,
            SERVICE_OVERRIDE,
            {"scene": "scene.party", "duration": 3600},
            blocking=True,
        )
        first_until = coord.override_until
        calls.clear()
        hass.states.async_set(MOTION, "on")
        await hass.async_block_till_done()

    assert calls[-1].data == {"entity_id": "scene.party", "transition": 10.0}
    assert coord.override_until == first_until


async def test_sun_floor_lock_keeps_dark_despite_lux(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 22:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=-5, lux="500")
        await _install(hass)

    assert calls[-1].data["entity_id"] == "scene.evening"


async def test_restart_semantics_debounces_rapid_triggers(
    hass: HomeAssistant,
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 12:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=15, lux="5000")
        await _install(hass)
        calls.clear()
        hass.states.async_set(LUX, "4999")
        hass.states.async_set(LUX, "4998")
        hass.states.async_set(LUX, "4997")
        await hass.async_block_till_done()

    assert len(calls) == 1


async def test_start_override_logs_info_with_resolved_scene(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    with freeze_time("2026-08-17 12:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=15, lux="5000")
        entry = await _install(hass)
        caplog.set_level(logging.INFO, logger="custom_components.ulkovalot.coordinator")
        caplog.clear()

        await hass.services.async_call(
            DOMAIN,
            SERVICE_OVERRIDE,
            {"scene": "scene.party", "duration": 60},
            blocking=True,
        )

    assert any(
        record.levelno == logging.INFO
        and "Override started" in record.message
        and "scene.party" in record.message
        for record in caplog.records
    )


async def test_cancel_override_logs_info(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    with freeze_time("2026-08-17 12:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=15, lux="5000")
        entry = await _install(hass)
        coord = hass.data[DOMAIN][entry.entry_id]
        coord.start_override(scene="scene.party", duration=60)
        caplog.set_level(logging.INFO, logger="custom_components.ulkovalot.coordinator")
        caplog.clear()

        coord.cancel_override()

    assert any(
        record.levelno == logging.INFO and "Override cancelled" in record.message
        for record in caplog.records
    )


async def test_override_expiry_logs_info(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    with freeze_time("2026-08-17 12:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=15, lux="5000")
        await _install(hass)
        caplog.set_level(logging.INFO, logger="custom_components.ulkovalot.coordinator")

        await hass.services.async_call(
            DOMAIN,
            SERVICE_OVERRIDE,
            {"scene": "scene.party", "duration": 60},
            blocking=True,
        )
        caplog.clear()
        frozen.tick(timedelta(seconds=61))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()

    assert any(
        record.levelno == logging.INFO and "Override expired" in record.message
        for record in caplog.records
    )


async def test_apply_scene_logs_decision_summary(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    with freeze_time("2026-08-17 12:00:00") as frozen:
        caplog.set_level(logging.DEBUG, logger="custom_components.ulkovalot.coordinator")
        _seed_environment(hass, frozen, elevation=30, lux="5000")
        await _install(hass)

    assert any(
        record.levelno == logging.DEBUG
        and "Apply:" in record.message
        and "scene_day" in record.message
        for record in caplog.records
    )


async def test_disable_flag_short_circuit_logs_debug_and_skips_dispatch(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 22:00:00") as frozen:
        caplog.set_level(logging.DEBUG, logger="custom_components.ulkovalot.coordinator")
        _seed_environment(hass, frozen, elevation=-10, lux="0", disable_state="on")
        await _install(hass)

    assert calls == []
    assert any(
        record.levelno == logging.DEBUG
        and "skipping apply" in record.message
        for record in caplog.records
    )


async def test_unload_stops_runtime_dispatch(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "scene", "turn_on")

    with freeze_time("2026-08-17 12:00:00") as frozen:
        _seed_environment(hass, frozen, elevation=15, lux="5000")
        entry = await _install(hass)
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        calls.clear()
        hass.states.async_set(LUX, "10")
        await hass.async_block_till_done()

    assert calls == []
