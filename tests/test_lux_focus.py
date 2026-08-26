"""Focused lux / override / lock behaviour tests (Stage 4).

Split from `test_parity.py` for readability — these exercise `logic.py`
directly rather than replaying the blueprint reference trace.
"""

from __future__ import annotations

from datetime import datetime, time as dtime

import pytest

from custom_components.ulkovalot.logic import (
    DarknessSource,
    LogicConfig,
    Phase,
    aggregate_lux,
    derive_phase,
    is_dark,
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


# --- override precedence ---------------------------------------------------


@pytest.mark.parametrize("phase", [Phase.DAY, Phase.MORNING, Phase.EVENING, Phase.NIGHT])
@pytest.mark.parametrize("motion", [False, True])
def test_override_wins_over_every_phase(phase, motion):
    assert pick_scene(phase, motion, override=True) == ("override_scene", "transition_time")


# --- lux storm: ceiling lock holds even as lux crashes ---------------------


def test_lux_storm_ceiling_lock_holds():
    # Mid-day, sun well above the ceiling; lux sensor reports a storm-driven
    # crash from 500 to 10 lx but the elevation safety lock stays bright.
    last_dark = False
    for lux in (500, 300, 100, 50, 10):
        dark, source = is_dark(elev=20, lux=lux, last_dark=last_dark, cfg=CFG)
        assert dark is False
        assert source is DarknessSource.SUN_ABOVE_CEILING
        last_dark = dark


# --- lux dawn boost: hysteresis flips the phase to DAY ----------------------


def test_lux_dawn_boost_flips_phase_to_day():
    now = datetime(2026, 1, 1, 10, 0, 0)
    elev = -1  # between floor (-3) and ceiling (+6): hysteresis band
    rising = True

    dark_before, source_before = is_dark(elev, lux=20, last_dark=True, cfg=CFG)
    phase_before = derive_phase(now, rising, dark_before, CFG)
    assert dark_before is True
    assert source_before is DarknessSource.LUX_THRESHOLD
    assert phase_before is Phase.MORNING

    dark_after, source_after = is_dark(
        elev, lux=CFG.lux_off_above, last_dark=dark_before, cfg=CFG
    )
    phase_after = derive_phase(now, rising, dark_after, CFG)
    assert dark_after is False
    assert source_after is DarknessSource.LUX_THRESHOLD
    assert phase_after is Phase.DAY


# --- sensor-lost fallback: decision path (and scene) can change ------------


def test_sensor_lost_falls_back_to_sun_only():
    now = datetime(2026, 1, 1, 12, 0, 0)
    elev = 4  # between floor and ceiling
    rising = False

    dark_with_sensor, source_with_sensor = is_dark(
        elev, lux=150, last_dark=True, cfg=CFG
    )
    scene_with_sensor = pick_scene(
        derive_phase(now, rising, dark_with_sensor, CFG), motion=False, override=False
    )
    assert dark_with_sensor is False
    assert source_with_sensor is DarknessSource.LUX_THRESHOLD
    assert scene_with_sensor == ("scene_day", "transition_time")

    lux = aggregate_lux(["unavailable"])
    assert lux is None

    dark_fallback, source_fallback = is_dark(
        elev, lux=lux, last_dark=dark_with_sensor, cfg=CFG
    )
    scene_fallback = pick_scene(
        derive_phase(now, rising, dark_fallback, CFG), motion=False, override=False
    )

    assert dark_fallback is True  # fallback ignores hysteresis: elev < ceiling -> dark
    # The diagnostic names the sensor loss, so a surprise evening scene at
    # midday is traceable to the dead sensor rather than the sun or the lux.
    assert source_fallback is DarknessSource.NO_LUX_FALLBACK
    assert scene_fallback == ("scene_evening", "transition_time")
    assert scene_fallback != scene_with_sensor


# --- floor lock: torch on the sensor doesn't fake bright at deep night -----


def test_floor_lock_ignores_torch_on_sensor():
    now = datetime(2026, 1, 1, 2, 0, 0)
    elev = -10
    rising = False

    dark, source = is_dark(elev, lux=200, last_dark=True, cfg=CFG)
    assert dark is True  # floor lock: elev <= floor -> dark regardless of lux
    assert source is DarknessSource.SUN_BELOW_FLOOR

    phase = derive_phase(now, rising, dark, CFG)
    scene = pick_scene(phase, motion=False, override=False)
    assert phase is Phase.NIGHT
    assert scene == ("scene_night", "transition_time")


# --- multi-sensor median: one covered sensor doesn't fool the aggregate ----


def test_multi_sensor_median_ignores_covered_sensor():
    lux = aggregate_lux([5, 400, 400])
    assert lux == 400

    dark, source = is_dark(elev=0, lux=lux, last_dark=True, cfg=CFG)
    assert dark is False
    assert source is DarknessSource.LUX_THRESHOLD
