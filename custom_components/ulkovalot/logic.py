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


class SunDarkness(str, Enum):
    """Sun elevation's standalone verdict, ignoring lux entirely.

    ``AMBIGUOUS`` is the band between the two configured elevations, where
    the sun declines to decide and defers to lux.
    """

    DARK = "dark"
    AMBIGUOUS = "ambiguous"
    BRIGHT = "bright"


class LuxDarkness(str, Enum):
    """Lux's standalone verdict, ignoring sun elevation entirely.

    ``HOLD`` is the hysteresis band between ``lux_on_below`` and
    ``lux_off_above``, where lux declines to decide and the previous
    dark state is retained.
    """

    DARK = "dark"
    HOLD = "hold"
    BRIGHT = "bright"
    UNKNOWN = "unknown"


class DarknessSource(str, Enum):
    """Which input actually decided the combined dark/bright answer."""

    SUN_BELOW_FLOOR = "sun_below_floor"
    SUN_ABOVE_CEILING = "sun_above_ceiling"
    LUX_THRESHOLD = "lux_threshold"
    LUX_HYSTERESIS_HOLD = "lux_hysteresis_hold"
    NO_LUX_FALLBACK = "no_lux_fallback"


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


def _parse_lux_reading(raw: float | int | str | None) -> float | None:
    """Coerce one raw reading to a float, or ``None`` if it isn't valid."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    if raw.strip().lower() in _INVALID_LUX_STRINGS:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def aggregate_lux(readings: Iterable[float | int | str | None]) -> float | None:
    """Median of the valid readings, or ``None`` if none remain."""
    valid = [
        parsed
        for raw in readings
        if (parsed := _parse_lux_reading(raw)) is not None
    ]
    if not valid:
        return None
    return float(median(valid))


def sun_darkness(elev: float, cfg: LogicConfig) -> SunDarkness:
    """Sun elevation's verdict on its own, before lux is consulted."""
    if elev <= cfg.sun_elev_dark_floor:
        return SunDarkness.DARK
    if elev >= cfg.sun_elev_bright_ceiling:
        return SunDarkness.BRIGHT
    return SunDarkness.AMBIGUOUS


def lux_darkness(lux: float | None, cfg: LogicConfig) -> LuxDarkness:
    """Lux's verdict on its own, independent of sun elevation."""
    if lux is None:
        return LuxDarkness.UNKNOWN
    if lux <= cfg.lux_on_below:
        return LuxDarkness.DARK
    if lux >= cfg.lux_off_above:
        return LuxDarkness.BRIGHT
    return LuxDarkness.HOLD


def is_dark(
    elev: float,
    lux: float | None,
    last_dark: bool,
    cfg: LogicConfig,
) -> tuple[bool, DarknessSource]:
    """Combined lux + sun-elevation dark/bright decision with hysteresis.

    Returns the decision along with the input that produced it, so the
    diagnostic entities can name *why* the lights went the way they did
    rather than only reporting the outcome.
    """
    if lux is None:
        return elev < cfg.sun_elev_bright_ceiling, DarknessSource.NO_LUX_FALLBACK
    sun = sun_darkness(elev, cfg)
    if sun is SunDarkness.DARK:
        return True, DarknessSource.SUN_BELOW_FLOOR
    if sun is SunDarkness.BRIGHT:
        return False, DarknessSource.SUN_ABOVE_CEILING
    verdict = lux_darkness(lux, cfg)
    if verdict is LuxDarkness.HOLD:
        return last_dark, DarknessSource.LUX_HYSTERESIS_HOLD
    return verdict is LuxDarkness.DARK, DarknessSource.LUX_THRESHOLD


def in_night_window(now: datetime, cfg: LogicConfig) -> bool:
    """True while the clock sits inside the configured night window.

    Purely a time check — it never makes anything dark on its own; it only
    splits an already-dark state into night vs. morning/evening.
    """
    t = now.time()
    return t >= cfg.night_start or t < cfg.night_end


def derive_phase(
    now: datetime,
    rising: bool,
    dark: bool,
    cfg: LogicConfig,
) -> Phase:
    """Map (time, sun direction, dark) to a coarse phase."""
    if not dark:
        return Phase.DAY
    if in_night_window(now, cfg):
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


def selection_reason(phase: Phase, motion: bool, override: bool, disabled: bool) -> str:
    """Mirror ``pick_scene``'s branch order, with the extra ``disabled`` pre-check."""
    if disabled:
        return "disabled"
    if override:
        return "override"
    if phase == Phase.DAY:
        return "day"
    if phase == Phase.MORNING:
        return "morning"
    if motion:
        return "motion"
    if phase == Phase.EVENING:
        return "evening"
    if phase == Phase.NIGHT:
        return "night"
    return "motion"


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
