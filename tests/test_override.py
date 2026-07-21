"""Tests for the ulkovalot override state machine (Stage 2b).

Focuses purely on the override paths in ``coordinator.py``. Sun / motion /
lux subscriptions land in Stage 3 and get their own tests. The
``apply_scene`` re-evaluation hook is stubbed with a call-counter so
tests assert on override state and hook invocations without needing any
real scene service.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.ulkovalot import (
    SERVICE_CANCEL_OVERRIDE,
    SERVICE_OVERRIDE,
)
from custom_components.ulkovalot.const import (
    CONF_DISABLE_FLAG,
    CONF_ILLUMINANCE_SENSORS,
    CONF_MOTION_SENSORS,
    CONF_NIGHT_SCENE_END_TIME,
    CONF_NIGHT_SCENE_START_TIME,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_DURATION,
    CONF_OVERRIDE_SCENE,
    CONF_OVERRIDE_TRIGGER,
    CONF_LUX_OFF_ABOVE,
    CONF_LUX_ON_BELOW,
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
    DEFAULT_OVERRIDE_DURATION,
    DOMAIN,
    OPTION_KEYS,
)
from custom_components.ulkovalot.coordinator import UlkovalotCoordinator


def _payload(**overrides: Any) -> dict[str, Any]:
    base = {
        CONF_MOTION_SENSORS: ["binary_sensor.pir_a"],
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


async def _install(
    hass: HomeAssistant, **overrides: Any
) -> tuple[MockConfigEntry, UlkovalotCoordinator, list[int]]:
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

    coordinator: UlkovalotCoordinator = hass.data[DOMAIN][entry.entry_id]
    calls: list[int] = []
    coordinator.apply_scene = lambda: calls.append(1)  # type: ignore[assignment]
    return entry, coordinator, calls


async def test_service_override_uses_defaults(hass: HomeAssistant) -> None:
    _, coordinator, calls = await _install(hass)

    await hass.services.async_call(DOMAIN, SERVICE_OVERRIDE, {}, blocking=True)

    assert coordinator.override_scene == "scene.override_default"
    assert coordinator.override_until is not None
    delta = coordinator.override_until - dt_util.utcnow()
    assert timedelta(seconds=DEFAULT_OVERRIDE_DURATION - 5) < delta <= timedelta(
        seconds=DEFAULT_OVERRIDE_DURATION
    )
    assert calls == [1]


async def test_service_override_explicit_scene_and_duration(
    hass: HomeAssistant,
) -> None:
    _, coordinator, calls = await _install(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_OVERRIDE,
        {"scene": "scene.party", "duration": 60},
        blocking=True,
    )

    assert coordinator.override_scene == "scene.party"
    delta = coordinator.override_until - dt_util.utcnow()
    assert timedelta(seconds=55) < delta <= timedelta(seconds=60)
    assert calls == [1]


async def test_repress_restarts_timer_and_swaps_scene(
    hass: HomeAssistant,
) -> None:
    _, coordinator, calls = await _install(hass)

    await hass.services.async_call(
        DOMAIN, SERVICE_OVERRIDE, {"duration": 60}, blocking=True
    )
    first_until = coordinator.override_until

    # Advance well past the first duration to prove the first timer was
    # cancelled — apply_scene should NOT be called by the (dead) expiry.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_OVERRIDE,
        {"scene": "scene.other", "duration": 300},
        blocking=True,
    )

    assert coordinator.override_scene == "scene.other"
    assert coordinator.override_until > first_until
    assert calls == [1, 1]  # two starts, zero stray expirations

    # First timer really dead: advancing to its (would-be) expiry does nothing.
    async_fire_time_changed(hass, first_until + timedelta(seconds=1))
    await hass.async_block_till_done()
    assert calls == [1, 1]
    assert coordinator.override_scene == "scene.other"


async def test_cancel_override_service(hass: HomeAssistant) -> None:
    _, coordinator, calls = await _install(hass)

    await hass.services.async_call(
        DOMAIN, SERVICE_OVERRIDE, {"duration": 300}, blocking=True
    )
    await hass.services.async_call(
        DOMAIN, SERVICE_CANCEL_OVERRIDE, {}, blocking=True
    )

    assert coordinator.override_scene is None
    assert coordinator.override_until is None
    assert calls == [1, 1]  # start + cancel

    # No stray expiry after cancel.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=301))
    await hass.async_block_till_done()
    assert calls == [1, 1]


async def test_timer_expiry_clears_state_and_reevaluates(
    hass: HomeAssistant,
) -> None:
    _, coordinator, calls = await _install(hass)

    await hass.services.async_call(
        DOMAIN, SERVICE_OVERRIDE, {"duration": 60}, blocking=True
    )
    assert calls == [1]

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()

    assert coordinator.override_scene is None
    assert coordinator.override_until is None
    assert calls == [1, 1]  # start + one expiry


async def test_trigger_entity_fires_override(hass: HomeAssistant) -> None:
    trigger = "input_button.override_btn"
    hass.states.async_set(trigger, "unknown")
    _, coordinator, calls = await _install(hass, **{CONF_OVERRIDE_TRIGGER: trigger})

    hass.states.async_set(trigger, "2026-07-15T00:00:00+00:00")
    await hass.async_block_till_done()

    assert coordinator.override_scene == "scene.override_default"
    assert coordinator.override_until is not None
    assert calls == [1]


async def test_unload_cancels_timer_and_deregisters_services(
    hass: HomeAssistant,
) -> None:
    entry, coordinator, calls = await _install(hass)
    await hass.services.async_call(
        DOMAIN, SERVICE_OVERRIDE, {"duration": 60}, blocking=True
    )
    assert hass.services.has_service(DOMAIN, SERVICE_OVERRIDE)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(DOMAIN, SERVICE_OVERRIDE)
    assert not hass.services.has_service(DOMAIN, SERVICE_CANCEL_OVERRIDE)

    # Post-unload timer would-be-expiry must not re-enter apply_scene.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert calls == [1]


async def test_unload_with_trigger_cleans_trigger_subscription(
    hass: HomeAssistant,
) -> None:
    trigger = "input_button.override_btn"
    hass.states.async_set(trigger, "unknown")
    entry, coordinator, calls = await _install(
        hass, **{CONF_OVERRIDE_TRIGGER: trigger}
    )

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Firing the trigger post-unload must not touch the (unloaded) coordinator.
    hass.states.async_set(trigger, "2026-07-15T00:00:01+00:00")
    await hass.async_block_till_done()
    assert calls == []
    assert coordinator.override_scene is None


async def test_two_entries_share_services_until_last_unloads(
    hass: HomeAssistant,
) -> None:
    entry_a, _, _ = await _install(hass)
    entry_b, _, _ = await _install(hass)

    assert await hass.config_entries.async_unload(entry_a.entry_id)
    await hass.async_block_till_done()
    # Services must survive while a second entry is still loaded.
    assert hass.services.has_service(DOMAIN, SERVICE_OVERRIDE)

    assert await hass.config_entries.async_unload(entry_b.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, SERVICE_OVERRIDE)
