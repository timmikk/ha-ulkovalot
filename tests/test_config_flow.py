"""Tests for the ulkovalot config, reconfigure, and options flows."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    ERROR_LUX_HYSTERESIS,
    ERROR_SUN_ELEV_RANGE,
    OPTION_KEYS,
)


def _full_input() -> dict[str, Any]:
    """A valid payload covering every field in the initial user step."""
    return {
        # data
        CONF_MOTION_SENSORS: ["binary_sensor.pir_a", "binary_sensor.pir_b"],
        CONF_ILLUMINANCE_SENSORS: ["sensor.lux_a"],
        CONF_DISABLE_FLAG: "input_boolean.disable",
        CONF_SCENE_DAY: "scene.day",
        CONF_SCENE_MORNING: "scene.morning",
        CONF_SCENE_EVENING: "scene.evening",
        CONF_SCENE_NIGHT: "scene.night",
        CONF_SCENE_MOTION: "scene.motion",
        CONF_OVERRIDE_SCENE: "scene.override",
        CONF_OVERRIDE_TRIGGER: "input_button.override",
        # options
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


async def _mock_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create a fully-configured MockConfigEntry and add it to hass."""
    payload = _full_input()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Outdoor lights coordinator",
        data={k: payload[k] for k in DATA_KEYS},
        options={k: payload[k] for k in OPTION_KEYS},
    )
    entry.add_to_hass(hass)
    return entry


async def test_user_step_happy_path(hass: HomeAssistant) -> None:
    """Full valid input creates an entry with the expected data/options split."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _full_input()
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Outdoor lights coordinator"
    for key in DATA_KEYS:
        assert result["data"][key] == _full_input()[key]
    for key in OPTION_KEYS:
        assert result["options"][key] == _full_input()[key]
    # No leakage between buckets.
    assert set(result["data"]).isdisjoint(OPTION_KEYS)
    assert set(result["options"]).isdisjoint(DATA_KEYS)


async def test_single_instance_abort(hass: HomeAssistant) -> None:
    """A second user-initiated flow aborts with single_instance_allowed."""
    await _mock_entry(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_round_trip(hass: HomeAssistant) -> None:
    """Values set via the options flow round-trip cleanly."""
    entry = await _mock_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    new_options = {k: _full_input()[k] for k in OPTION_KEYS}
    new_options[CONF_LUX_ON_BELOW] = 40
    new_options[CONF_LUX_OFF_ABOVE] = 150
    new_options[CONF_NIGHT_SCENE_START_TIME] = "22:30:00"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], new_options
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    for key, expected in new_options.items():
        assert entry.options[key] == expected

    # Reopening surfaces the persisted values (defaults are read from options).
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    defaults = {
        key.schema: key.default() if callable(key.default) else key.default
        for key in schema
    }
    assert defaults[CONF_LUX_ON_BELOW] == 40
    assert defaults[CONF_LUX_OFF_ABOVE] == 150
    assert defaults[CONF_NIGHT_SCENE_START_TIME] == "22:30:00"


async def test_reconfigure_swaps_sensor_list(hass: HomeAssistant) -> None:
    """The reconfigure step can swap identity fields (e.g. sensor list)."""
    entry = await _mock_entry(hass)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_input = _full_input()
    new_input[CONF_MOTION_SENSORS] = ["binary_sensor.pir_c"]
    new_input[CONF_ILLUMINANCE_SENSORS] = ["sensor.lux_x", "sensor.lux_y"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], new_input
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"

    assert entry.data[CONF_MOTION_SENSORS] == ["binary_sensor.pir_c"]
    assert entry.data[CONF_ILLUMINANCE_SENSORS] == ["sensor.lux_x", "sensor.lux_y"]


@pytest.mark.parametrize(
    ("mutation", "field", "error"),
    [
        (
            {CONF_LUX_ON_BELOW: 200, CONF_LUX_OFF_ABOVE: 100},
            CONF_LUX_OFF_ABOVE,
            ERROR_LUX_HYSTERESIS,
        ),
        (
            {CONF_SUN_ELEV_DARK_FLOOR: 10, CONF_SUN_ELEV_BRIGHT_CEILING: 5},
            CONF_SUN_ELEV_BRIGHT_CEILING,
            ERROR_SUN_ELEV_RANGE,
        ),
    ],
)
async def test_user_step_validation_errors(
    hass: HomeAssistant,
    mutation: dict[str, Any],
    field: str,
    error: str,
) -> None:
    """Invalid threshold combos return to the form with the right error key."""
    payload = {**_full_input(), **mutation}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], payload
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {field: error}
