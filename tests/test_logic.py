"""Unit tests for the pure state engine (`custom_components/ulkovalot/logic.py`)."""

from __future__ import annotations

from datetime import datetime, time as dtime, timedelta

import pytest

from custom_components.ulkovalot.logic import (
    LogicConfig,
    MotionSample,
    Phase,
    aggregate_lux,
    derive_phase,
    is_dark,
    motion_active,
    override_active,
    pick_scene,
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
    ("elev", "lux", "last_dark", "expected"),
    [
        # Floor lock — dark regardless of high lux.
        (-3, 500, False, True),
        (-10, 5000, False, True),
        # Ceiling lock — bright regardless of low lux.
        (6, 0, True, False),
        (20, 5, True, False),
        # Hysteresis band: was-bright flips dark only at/under lux_on_below.
        (0, 30, False, True),
        (0, 31, False, False),
        # Was-dark stays dark until lux crosses lux_off_above.
        (0, 99, True, True),
        (0, 100, True, False),
        # Fallback when lux is None: single ceiling threshold.
        (5, None, False, True),
        (6, None, False, False),
        (-10, None, True, True),
    ],
)
def test_is_dark(elev, lux, last_dark, expected):
    assert is_dark(elev, lux, last_dark, CFG) is expected


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
