"""Pure state engine for ulkovalot.

Deterministic functions that decide which scene should fire, given a
snapshot of inputs. Contains zero Home Assistant imports so it can be
exercised in a plain ``pytest`` process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
from enum import Enum
from statistics import median
from typing import Iterable


class Phase(str, Enum):
    """Coarse time-of-day phase driving the scene choose priority."""

    DAY = "day"
    MORNING = "morning"
    EVENING = "evening"
    NIGHT = "night"


@dataclass(frozen=True)
class LogicConfig:
    """Snapshot of options used by the pure functions."""

    night_start: dtime
    night_end: dtime
    lux_on_below: float
    lux_off_above: float
    sun_elev_dark_floor: float
    sun_elev_bright_ceiling: float


@dataclass(frozen=True)
class MotionSample:
    """State + last-changed timestamp for one motion sensor."""

    state: str
    last_changed: datetime


_INVALID_LUX_STRINGS = {"unknown", "unavailable", "none", ""}


def aggregate_lux(readings: Iterable[float | int | str | None]) -> float | None:
    """Median of the valid readings, or ``None`` if none remain."""
    valid: list[float] = []
    for raw in readings:
        if raw is None:
            continue
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            valid.append(float(raw))
            continue
        if isinstance(raw, str):
            if raw.strip().lower() in _INVALID_LUX_STRINGS:
                continue
            try:
                valid.append(float(raw))
            except ValueError:
                continue
    if not valid:
        return None
    return float(median(valid))


def is_dark(
    elev: float,
    lux: float | None,
    last_dark: bool,
    cfg: LogicConfig,
) -> bool:
    """Combined lux + sun-elevation dark/bright decision with hysteresis."""
    if lux is None:
        return elev < cfg.sun_elev_bright_ceiling
    if elev <= cfg.sun_elev_dark_floor:
        return True
    if elev >= cfg.sun_elev_bright_ceiling:
        return False
    if last_dark:
        return lux < cfg.lux_off_above
    return lux <= cfg.lux_on_below


def derive_phase(
    now: datetime,
    rising: bool,
    dark: bool,
    cfg: LogicConfig,
) -> Phase:
    """Map (time, sun direction, dark) to a coarse phase."""
    if not dark:
        return Phase.DAY
    t = now.time()
    if t >= cfg.night_start or t < cfg.night_end:
        return Phase.NIGHT
    if rising:
        return Phase.MORNING
    return Phase.EVENING


def motion_active(
    now: datetime,
    sensors: Iterable[MotionSample],
    no_motion_wait: float,
) -> bool:
    """Any sensor on, or recently changed within the wait window."""
    threshold = now - timedelta(seconds=no_motion_wait)
    for sample in sensors:
        if sample.state == "on":
            return True
        if sample.last_changed >= threshold:
            return True
    return False


def override_active(now: datetime, override_until: datetime | None) -> bool:
    """True while ``now`` is strictly before the override expiry."""
    if override_until is None:
        return False
    return now < override_until


def pick_scene(
    phase: Phase,
    motion: bool,
    override: bool,
) -> tuple[str, str]:
    """First-match-wins scene selection from the overview's choose priority.

    Returns ``(scene_key, transition_key)`` — the caller resolves both
    keys against the runtime config to get the actual scene entity id
    and transition seconds.
    """
    if override:
        return ("override_scene", "transition_time")
    if phase == Phase.DAY:
        return ("scene_day", "transition_time")
    if phase == Phase.MORNING:
        return ("scene_morning", "transition_time")
    if motion:
        return ("scene_motion", "transition_time_motion")
    if phase == Phase.EVENING:
        return ("scene_evening", "transition_time")
    if phase == Phase.NIGHT:
        return ("scene_night", "transition_time")
    return ("scene_motion", "transition_time")
