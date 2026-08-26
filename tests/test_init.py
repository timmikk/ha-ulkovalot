"""Smoke test — the module imports."""

import logging

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ulkovalot import SERVICE_CANCEL_OVERRIDE, SERVICE_OVERRIDE
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


def test_import():
    """The integration package can be imported."""
    from custom_components import ulkovalot  # noqa: F401


def _payload() -> dict:
    return {
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


async def _install(hass: HomeAssistant) -> MockConfigEntry:
    payload = _payload()
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


async def test_async_setup_entry_logs_info_with_entry_id(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="custom_components.ulkovalot")
    entry = await _install(hass)

    assert any(
        record.levelno == logging.INFO and entry.entry_id in record.message
        for record in caplog.records
    )


async def test_override_service_logs_info(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    await _install(hass)
    caplog.set_level(logging.INFO, logger="custom_components.ulkovalot")
    caplog.clear()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_OVERRIDE,
        {"scene": "scene.party", "duration": 60},
        blocking=True,
    )

    assert any(
        record.levelno == logging.INFO and "Service override called" in record.message
        for record in caplog.records
    )


async def test_cancel_override_service_logs_info(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    await _install(hass)
    caplog.set_level(logging.INFO, logger="custom_components.ulkovalot")
    caplog.clear()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CANCEL_OVERRIDE,
        {},
        blocking=True,
    )

    assert any(
        record.levelno == logging.INFO
        and "Service cancel_override called" in record.message
        for record in caplog.records
    )
