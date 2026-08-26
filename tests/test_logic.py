"""Unit tests for the pure state engine (`custom_components/ulkovalot/logic.py`)."""

from __future__ import annotations

from datetime import datetime, time as dtime, timedelta

import pytest

from custom_components.ulkovalot.logic import (
    DarknessSource,
    LogicConfig,
    LuxDarkness,
    MotionSample,
    Phase,
    SunDarkness,
    aggregate_lux,
    derive_phase,
    in_night_window,
    is_dark,
    lux_darkness,
    motion_active,
    override_active,
    pick_scene,
    selection_reason,
    sun_darkness,
)


CFG = LogicConfig(
    night_start=dtime(23, 0),
    night_end=dtime(7, 0),
    lux_on_below=30,
    lux_off_above=100,
    sun_elev_dark_floor=-3,
    sun_elev_bright_ceiling=6,
)


# --- aggregate_lux --------------------------------------------------------


@pytest.mark.parametrize(
    ("readings", "expected"),
    [
        ([42.0], 42.0),
        ([10, 20, 90], 20.0),
        ([10, 20, 30, 40], 25.0),
        ([50.0, None, 70.0], 60.0),
        ([None, "unknown", "unavailable"], None),
        ([], None),
        (["12.5", "not-a-number", None, "UNKNOWN", ""], 12.5),
        ([True, False, 15], 15.0),
        ([[1, 2], object(), 42], 42.0),
    ],
)
def test_aggregate_lux(readings, expected):
    assert aggregate_lux(readings) == expected


# --- is_dark -------------------------------------------------------------


@pytest.mark.parametrize(
    ("elev", "lux", "last_dark", "expected", "source"),
    [
        # Floor lock — dark regardless of high lux.
        (-3, 500, False, True, DarknessSource.SUN_BELOW_FLOOR),
        (-10, 5000, False, True, DarknessSource.SUN_BELOW_FLOOR),
        # Ceiling lock — bright regardless of low lux.
        (6, 0, True, False, DarknessSource.SUN_ABOVE_CEILING),
        (20, 5, True, False, DarknessSource.SUN_ABOVE_CEILING),
        # Hysteresis band: was-bright flips dark only at/under lux_on_below.
        (0, 30, False, True, DarknessSource.LUX_THRESHOLD),
        (0, 31, False, False, DarknessSource.LUX_HYSTERESIS_HOLD),
        # Was-dark stays dark until lux crosses lux_off_above.
        (0, 99, True, True, DarknessSource.LUX_HYSTERESIS_HOLD),
        (0, 100, True, False, DarknessSource.LUX_THRESHOLD),
        # Fallback when lux is None: single ceiling threshold.
        (5, None, False, True, DarknessSource.NO_LUX_FALLBACK),
        (6, None, False, False, DarknessSource.NO_LUX_FALLBACK),
        (-10, None, True, True, DarknessSource.NO_LUX_FALLBACK),
    ],
)
def test_is_dark(elev, lux, last_dark, expected, source):
    dark, reported = is_dark(elev, lux, last_dark, CFG)
    assert dark is expected
    assert reported is source


@pytest.mark.parametrize("last_dark", [True, False])
def test_is_dark_hysteresis_hold_retains_previous_state(last_dark):
    """Inside the band, lux declines to decide — in *both* directions."""
    dark, source = is_dark(0, 50, last_dark, CFG)
    assert source is DarknessSource.LUX_HYSTERESIS_HOLD
    assert dark is last_dark


# --- sun_darkness / lux_darkness -----------------------------------------


@pytest.mark.parametrize(
    ("elev", "expected"),
    [
        (-10, SunDarkness.DARK),
        (-3, SunDarkness.DARK),  # floor is inclusive
        (-2.9, SunDarkness.AMBIGUOUS),
        (0, SunDarkness.AMBIGUOUS),
        (5.9, SunDarkness.AMBIGUOUS),
        (6, SunDarkness.BRIGHT),  # ceiling is inclusive
        (20, SunDarkness.BRIGHT),
    ],
)
def test_sun_darkness(elev, expected):
    assert sun_darkness(elev, CFG) is expected


@pytest.mark.parametrize(
    ("lux", "expected"),
    [
        (None, LuxDarkness.UNKNOWN),
        (0, LuxDarkness.DARK),
        (30, LuxDarkness.DARK),  # lux_on_below is inclusive
        (31, LuxDarkness.HOLD),
        (99, LuxDarkness.HOLD),
        (100, LuxDarkness.BRIGHT),  # lux_off_above is inclusive
        (5000, LuxDarkness.BRIGHT),
    ],
)
def test_lux_darkness(lux, expected):
    assert lux_darkness(lux, CFG) is expected


@pytest.mark.parametrize("last_dark", [True, False])
@pytest.mark.parametrize("lux", [0, 30, 31, 50, 99, 100, 5000])
def test_lux_darkness_agrees_with_is_dark_in_the_band(lux, last_dark):
    """The standalone lux verdict must not drift from is_dark's lux branch.

    Only meaningful at an ambiguous elevation, where the sun defers.
    """
    dark, source = is_dark(0, lux, last_dark, CFG)
    verdict = lux_darkness(lux, CFG)
    if verdict is LuxDarkness.HOLD:
        assert source is DarknessSource.LUX_HYSTERESIS_HOLD
        assert dark is last_dark
    else:
        assert source is DarknessSource.LUX_THRESHOLD
        assert dark is (verdict is LuxDarkness.DARK)


# --- derive_phase --------------------------------------------------------


def _at(h: int, m: int = 0) -> datetime:
    return datetime(2026, 1, 1, h, m)


@pytest.mark.parametrize(
    ("now", "rising", "dark", "expected"),
    [
        # Bright always → DAY, regardless of hour or sun direction.
        (_at(3), False, False, Phase.DAY),
        (_at(12), True, False, Phase.DAY),
        # Night window boundaries: 23:00 inclusive, 07:00 exclusive.
        (_at(23, 0), False, True, Phase.NIGHT),
        (_at(6, 59), True, True, Phase.NIGHT),
        (_at(7, 0), True, True, Phase.MORNING),
        # Inside window, rising doesn't upgrade to morning.
        (_at(2, 0), True, True, Phase.NIGHT),
        # Outside window: rising vs not-rising picks morning vs evening.
        (_at(10, 0), True, True, Phase.MORNING),
        (_at(20, 0), False, True, Phase.EVENING),
    ],
)
def test_derive_phase(now, rising, dark, expected):
    assert derive_phase(now, rising, dark, CFG) is expected


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        # The window wraps midnight: 23:00 inclusive -> 07:00 exclusive.
        (_at(23, 0), True),
        (_at(23, 30), True),
        (_at(0, 0), True),
        (_at(6, 59), True),
        (_at(7, 0), False),
        (_at(12, 0), False),
        (_at(22, 59), False),
    ],
)
def test_in_night_window(now, expected):
    assert in_night_window(now, CFG) is expected


@pytest.mark.parametrize("hour", range(24))
def test_derive_phase_agrees_with_in_night_window(hour):
    """NIGHT is reported exactly when the window says so, given dark."""
    now = _at(hour)
    phase = derive_phase(now, rising=False, dark=True, cfg=CFG)
    assert (phase is Phase.NIGHT) is in_night_window(now, CFG)


# --- motion_active -------------------------------------------------------


NOW = datetime(2026, 1, 1, 12, 0, 0)


def _sample(state: str, seconds_ago: float) -> MotionSample:
    return MotionSample(state=state, last_changed=NOW - timedelta(seconds=seconds_ago))


@pytest.mark.parametrize(
    ("samples", "wait", "expected"),
    [
        ([], 120, False),
        ([_sample("on", 999)], 120, True),
        ([_sample("off", 30)], 120, True),
        ([_sample("off", 300)], 120, False),
        ([_sample("off", 300), _sample("off", 10)], 120, True),
        ([_sample("off", 300), _sample("on", 5)], 120, True),
    ],
)
def test_motion_active(samples, wait, expected):
    assert motion_active(NOW, samples, wait) is expected


# --- override_active -----------------------------------------------------


@pytest.mark.parametrize(
    ("until", "expected"),
    [
        (None, False),
        (NOW + timedelta(seconds=1), True),
        (NOW, False),
        (NOW - timedelta(seconds=1), False),
    ],
)
def test_override_active(until, expected):
    assert override_active(NOW, until) is expected


# --- pick_scene ----------------------------------------------------------


@pytest.mark.parametrize(
    ("phase", "motion", "override", "expected"),
    [
        # 1. override wins over everything.
        (Phase.DAY, True, True, ("override_scene", "transition_time")),
        (Phase.NIGHT, False, True, ("override_scene", "transition_time")),
        # 2. day.
        (Phase.DAY, False, False, ("scene_day", "transition_time")),
        # 3. morning wins over motion.
        (Phase.MORNING, True, False, ("scene_morning", "transition_time")),
        # 4. non-day + motion → scene_motion (fast transition).
        (Phase.EVENING, True, False, ("scene_motion", "transition_time_motion")),
        (Phase.NIGHT, True, False, ("scene_motion", "transition_time_motion")),
        # 5, 6. evening / night without motion.
        (Phase.EVENING, False, False, ("scene_evening", "transition_time")),
        (Phase.NIGHT, False, False, ("scene_night", "transition_time")),
        # 7. default fallback for out-of-band phase.
        ("unknown", False, False, ("scene_motion", "transition_time")),
    ],
)
def test_pick_scene(phase, motion, override, expected):
    assert pick_scene(phase, motion, override) == expected


# --- selection_reason ------------------------------------------------------


@pytest.mark.parametrize(
    ("phase", "motion", "override", "disabled", "expected"),
    [
        # disabled beats everything, including override.
        (Phase.DAY, True, True, True, "disabled"),
        # override beats phase.
        (Phase.DAY, False, True, False, "override"),
        (Phase.NIGHT, False, True, False, "override"),
        # day.
        (Phase.DAY, False, False, False, "day"),
        # morning wins over motion.
        (Phase.MORNING, True, False, False, "morning"),
        # motion during evening/night.
        (Phase.EVENING, True, False, False, "motion"),
        (Phase.NIGHT, True, False, False, "motion"),
        # evening / night without motion.
        (Phase.EVENING, False, False, False, "evening"),
        (Phase.NIGHT, False, False, False, "night"),
    ],
)
def test_selection_reason(phase, motion, override, disabled, expected):
    assert selection_reason(phase, motion, override, disabled) == expected


@pytest.mark.parametrize(
    ("phase", "motion", "override"),
    [
        (Phase.DAY, False, False),
        (Phase.MORNING, True, False),
        (Phase.EVENING, True, False),
        (Phase.NIGHT, True, False),
        (Phase.EVENING, False, False),
        (Phase.NIGHT, False, False),
        (Phase.DAY, False, True),
    ],
)
def test_selection_reason_parity_with_pick_scene(phase, motion, override):
    """When not disabled, the reason should match the branch pick_scene took."""
    scene_key, _ = pick_scene(phase, motion, override)
    reason = selection_reason(phase, motion, override, disabled=False)
    if override:
        assert scene_key == "override_scene" and reason == "override"
    elif motion and phase not in (Phase.DAY, Phase.MORNING):
        assert scene_key == "scene_motion" and reason == "motion"
    else:
        assert scene_key == f"scene_{reason}"
