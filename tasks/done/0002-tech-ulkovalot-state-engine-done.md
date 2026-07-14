# Task: ulkovalot pure state engine (Stage 2)

**Status:** done
**Issue:** #2
**Type:** tech
**Complexity:** medium
**Version bump:** patch
**Created:** 2026-07-08
**Completed:** 2026-07-14

## Context

Stage 2 of the [Ulkovalot integration plan](0000-overview-integration-stages.md).
Adds `logic.py` — a pure-Python module with the phase / dark-bright /
lux-aggregation / motion / override / scene-picking functions. Zero HA
imports; runs in a plain `pytest` process. Target: 100 % line + branch
coverage. Everything downstream (override plumbing, coordinator, parity
tests) depends on this module's contract.

---

Read the [overview](0000-overview-integration-stages.md) first for the
shared feature surface, dark/bright rules, phase derivation, choose
priority, and testing strategy.

## Goal

Deterministic pure functions that decide which scene *would* fire, given
a snapshot of inputs. Zero HA imports — this module runs in a plain
`pytest` process with no `hass` fixture.

## Deliverables

`custom_components/ulkovalot/logic.py`:

- `aggregate_lux(readings: list[float | str | None]) -> float | None`
  — filter out `None` / `"unknown"` / `"unavailable"` / non-numeric,
  return the median of the remainder (mean of two middles on even
  count). Returns `None` if no valid readings — signals fallback.
- `is_dark(elev: float, lux: float | None, last_dark: bool, cfg) -> bool`
  — encodes the lock-floor / lock-ceiling / hysteresis rule from the
  overview. `last_dark` is the previous state, used only inside the
  hysteresis band. `lux=None` triggers the single-threshold
  sun-fallback branch.
- `derive_phase(now, rising: bool, dark: bool, cfg) -> Phase` where
  `Phase ∈ {DAY, MORNING, EVENING, NIGHT}`, using the phase rules from
  the overview.
- `motion_active(now, sensors_state, no_motion_wait) -> bool` — any
  sensor `on` or last `on→off` within the wait window. Empty list →
  always `False`.
- `override_active(now, override_until: datetime | None) -> bool` —
  pure time check.
- `pick_scene(phase, motion, override) -> (scene_key, transition_key)`
  — first-match-wins over the choose priority from the overview
  (override wins first).

Notes:

- Config is passed as a plain dataclass / named tuple so tests don't
  need HA's config-entry helpers.
- `now` is passed in — the module never calls `datetime.now()` itself.
- No mutable module state. `is_dark` takes `last_dark` explicitly so
  the caller owns hysteresis history.

## Tests (`tests/test_logic.py`)

Table-driven, one parametrize per function. Cases to cover:

- **`aggregate_lux`**: single-sensor, odd-count median, even-count
  median, mixed valid + `None`, all-`unavailable` → `None`, empty
  list → `None`, non-numeric strings ignored.
- **`is_dark`**: floor lock (elev ≤ floor → dark regardless of lux),
  ceiling lock (elev ≥ ceiling → bright regardless of lux),
  hysteresis band edges (`lux_on_below`, `lux_off_above`,
  in-between-holds-state), `lux=None` fallback with elev on both
  sides of the ceiling.
- **`derive_phase`**: night-window boundaries at 23:00 / 07:00
  exactly, rising vs not-rising when dark inside window, bright at
  every hour → DAY.
- **`motion_active`**: single sensor active, latched within wait,
  latched past wait → False, multi-sensor mix, empty list.
- **`override_active`**: none set → False, in-window → True, exactly
  at expiry → False.
- **`pick_scene`**: exercise every one of the seven choose branches
  including default; assert both scene key and transition key.

Target: **100 % line + branch coverage of `logic.py`**. See the
overview for coverage tooling. Add `freezegun` to
`requirements_test.txt` if any test needs a frozen `datetime.now`.

## Exit criteria

- `pytest tests/test_logic.py` green.
- `logic.py` at 100 % line + branch coverage.
- No HA imports in `logic.py` (grep-verifiable).

## Release

At the end of Stage 2, bump `manifest.json` to `0.1.0` and tag
`v0.1.0`. It's the first version with useful code even though nothing
observable happens in HA yet — Stage 2b/3 depend on this being a
release surface.

## Out of scope

- Anything that touches `hass` — Stage 3.
- Override state machine (timer, service registration) — Stage 2b.
- Parity replay against blueprint — Stage 4.

## Actual commits

- e168f7e feat(logic): add pure state engine module
- ca7655e test(logic): cover state engine at 100% line and branch
- cd52169 chore(release): bump manifest to 0.1.0
