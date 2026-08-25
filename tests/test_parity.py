"""Blueprint parity trace (Stage 4).

Sensor-less config replay comparing `logic.py` against a Python
re-implementation of the `Ulkovalot 3` blueprint's ``variables:`` block
(`~/dev/home-assistant-config/blueprints/automation/testi/ulkovalot.yaml`).
The reference implementation below is deliberately independent of
`logic.py` so a regression on either side shows up as a per-minute
scene mismatch.

Because time no longer bounds evening/morning in the component (only
the night dim scene has an explicit window — see divergence 1 below),
strict parity is only guaranteed while the sun elevation stays on one
side of ``sun_elev_bright_ceiling`` for the whole
``night_scene_start_time -> night_scene_end_time`` window. The winter
and equinox traces below stay inside that envelope for their whole
night window; the summer trace pokes outside it (elevation is still
well above the ceiling at the 07:00 window edge) to prove the
component and the blueprint still agree once you collapse the
blueprint's two elevation inputs into one (divergence 2) — the
resulting phase partition is identical either way.

Documented, deliberate divergences between the component and the raw
blueprint:

1. Time bounds only the night dim scene in the component; the
   blueprint time-bounds evening/morning too (via the same
   ``morning_light_on_time`` / ``evening_light_off_time`` window). The
   two windows are exact complements of each other, so the resulting
   phase partition matches even though the component doesn't re-check
   the window for evening/morning.
2. The blueprint's two separate elevation thresholds
   (``lights_off_morning_sun``, ``lights_on_evening_sun``) collapse
   into the component's single ``sun_elev_bright_ceiling``. The
   reference below pins both blueprint inputs to that same value to
   model an equivalent deployment.
3. ``motion_sensors`` accepts 0..N in the component vs. the
   blueprint's fixed pair. The harness runs two motion sensors,
   matching the blueprint's shape.
4. ``disable_flag`` is an optional entity selector (``str | None``) in
   the component vs. the blueprint's empty-string sentinel. Not
   exercised by ``pick_scene`` (handled by the coordinator layer), so
   it doesn't affect this trace.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time as dtime, timedelta

import pytest

from custom_components.ulkovalot.logic import (
    LogicConfig,
    MotionSample,
    aggregate_lux,
    derive_phase,
    is_dark,
    motion_active,
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

NO_MOTION_WAIT = 120.0

# Pulse windows, as fractional hours, per motion sensor.
MOTION_1_PULSES = [(8.0, 8.083)]  # ~08:00-08:05
MOTION_2_PULSES = [(21.0, 21.083)]  # ~21:00-21:05


# --- blueprint reference implementation ------------------------------------


def _blueprint_scene(
    now: datetime,
    rising: bool,
    elevation: float,
    motion_samples: tuple[MotionSample, MotionSample],
    no_motion_wait: float,
    morning_on: dtime,
    evening_off: dtime,
    ceiling: float,
) -> tuple[str, str]:
    """Port of the blueprint's `variables:` + `choose:` block.

    Both blueprint elevation inputs (`lights_off_morning_sun`,
    `lights_on_evening_sun`) are pinned to ``ceiling`` — see divergence 2
    in the module docstring.
    """
    morning_on_dt = datetime.combine(now.date(), morning_on)
    evening_off_dt = datetime.combine(now.date(), evening_off)

    after_sunrise = rising and elevation >= ceiling
    before_sunset = (not rising) and elevation > ceiling
    is_day_time = after_sunrise or before_sunset

    in_day_window = morning_on_dt <= now < evening_off_dt
    is_evening = (not rising) and in_day_window and elevation <= ceiling
    is_morning = rising and in_day_window and elevation < ceiling
    is_night = (now >= evening_off_dt and elevation <= ceiling) or (
        now < morning_on_dt and elevation < ceiling
    )

    is_motion = any(
        sample.state == "on" or (now - sample.last_changed) <= timedelta(seconds=no_motion_wait)
        for sample in motion_samples
    )

    if is_day_time:
        return ("scene_day", "transition_time")
    if is_morning:
        return ("scene_morning", "transition_time")
    if is_motion:
        return ("scene_motion", "transition_time_motion")
    if is_evening:
        return ("scene_evening", "transition_time")
    if is_night:
        return ("scene_night", "transition_time")
    return ("scene_motion", "transition_time")


# --- synthetic 24h trace driver ---------------------------------------------


def _elevation(hour: float, peak: float, trough: float) -> float:
    """Smooth single-trough/single-peak arc: trough at midnight, peak at noon."""
    mid = (peak + trough) / 2
    amp = (peak - trough) / 2
    return mid + amp * math.cos(2 * math.pi * (hour - 12) / 24)


def _in_pulse(hour: float, pulses: list[tuple[float, float]]) -> bool:
    return any(start <= hour < end for start, end in pulses)


@dataclass
class _MotionSim:
    """Tracks state + last_changed the way an HA entity would."""

    state: str = "off"
    last_changed: datetime | None = None

    def step(self, now: datetime, on: bool) -> MotionSample:
        new_state = "on" if on else "off"
        if self.last_changed is None or new_state != self.state:
            self.state = new_state
            self.last_changed = now
        return MotionSample(state=self.state, last_changed=self.last_changed)


SEASONS = [
    pytest.param(date(2026, 12, 21), 7.0, -50.0, id="winter"),
    pytest.param(date(2026, 3, 20), 25.0, -40.0, id="equinox"),
    pytest.param(date(2026, 6, 21), 53.0, -8.0, id="summer"),
]


@pytest.mark.parametrize(("day", "peak", "trough"), SEASONS)
def test_parity_trace_sensor_less(day, peak, trough):
    """Sensor-less 24h trace at 1-minute resolution, override disabled.

    `logic.py` and the blueprint reference must agree on every sampled
    scene — the config is symmetric enough (single elevation threshold,
    two motion sensors, no disable flag) that none of the documented
    divergences actually change the outcome.
    """
    sensor_1 = _MotionSim()
    sensor_2 = _MotionSim()
    mismatches: list[tuple] = []

    for minute in range(24 * 60):
        hour = minute / 60
        now = datetime.combine(day, dtime()) + timedelta(minutes=minute)
        elevation = _elevation(hour, peak, trough)
        rising = hour < 12

        sample_1 = sensor_1.step(now, _in_pulse(hour, MOTION_1_PULSES))
        sample_2 = sensor_2.step(now, _in_pulse(hour, MOTION_2_PULSES))

        lux = aggregate_lux([])  # sensor-less config
        dark = is_dark(elevation, lux, last_dark=False, cfg=CFG)
        phase = derive_phase(now, rising, dark, CFG)
        motion = motion_active(now, [sample_1, sample_2], NO_MOTION_WAIT)
        actual = pick_scene(phase, motion, override=False)

        expected = _blueprint_scene(
            now=now,
            rising=rising,
            elevation=elevation,
            motion_samples=(sample_1, sample_2),
            no_motion_wait=NO_MOTION_WAIT,
            morning_on=CFG.night_end,
            evening_off=CFG.night_start,
            ceiling=CFG.sun_elev_bright_ceiling,
        )

        if actual != expected:
            mismatches.append((now.isoformat(timespec="minutes"), round(elevation, 2), rising, actual, expected))

    assert not mismatches, (
        f"{len(mismatches)} parity mismatches for {day} "
        f"(now, elev, rising, actual, expected): {mismatches[:10]}"
    )
