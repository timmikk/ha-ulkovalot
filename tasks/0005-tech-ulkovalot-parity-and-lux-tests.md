# Task: ulkovalot parity harness and lux tests (Stage 4)

**Status:** pending
**Issue:** #5
**Type:** tech
**Complexity:** medium
**Version bump:** patch
**Created:** 2026-07-08
**Completed:** —

## Context

Stage 4 of the [Ulkovalot integration plan](0000-overview-integration-stages.md).
Adds `tests/test_parity.py` — a synthetic 24-hour trace replay that
compares the component against a Python re-implementation of the
blueprint's `variables:` block for sensor-less configs (where parity
still holds). Adds focused tests for the new lux behaviour: floor /
ceiling locks, storm scenarios, sensor-lost fallback, override
precedence over every phase.

---

Read the [overview](0000-overview-integration-stages.md) for the
blueprint reference, the semantic shift (time no longer bounds
evening/morning), and the testing strategy.

## Goal

Prove the component matches the blueprint on the paths that were
supposed to be preserved, and prove the new behaviour on the paths
that intentionally diverge.

Because time no longer bounds evening/morning, **strict blueprint
parity holds only for sensor-less configurations where the sun
elevation stays above/below the fallback ceiling for the whole
`night_scene_start_time → night_scene_end_time` window**. Outside
that envelope we assert the *new* behaviour, not the blueprint's.

## Deliverables

`tests/test_parity.py`:

- **Blueprint reference implementation** — a second copy of the
  blueprint's `variables:` block ported to Python, deliberately
  independent of `logic.py`. Lives inline in the test module so
  divergences are visible next to the assertions.
- **Trace replay** driver:
  - Synthetic 24-hour timeline at 1-minute resolution.
  - Sun elevation swept along a plausible arc for the site
    (parametrize a couple of dates: winter, equinox, summer).
  - Motion pulses at representative hours.
  - Sensor-less config (no `illuminance_sensors`).
  - Override disabled.
- Assert `pick_scene` output matches the blueprint reference at every
  event, or the difference is on the deliberately-diverged list.
- **Deliberate divergences** documented in a Python constant at the
  top of the file — the assertions know to expect these:
  1. Time bounds only the night dim scene, not evening/morning.
  2. The two blueprint elevation thresholds collapse into one
     (`sun_elev_bright_ceiling` — same field used for the fallback).
  3. `motion_sensors` accepts 0..N (parity harness runs with two, as
     the blueprint does).
  4. `disable_flag` is an entity selector, empty = unused
     (blueprint's empty-string sentinel maps to `None`).

Additional focused tests (may live in the same file or a new
`tests/test_lux_focus.py` — split for readability):

- **Override precedence**: for each phase in {DAY, MORNING, EVENING,
  NIGHT}, an active override picks `override_scene`.
- **Lux storm**: mid-day, sun at +20°, lux drops from 500 to 10 →
  `is_dark` stays False (ceiling lock).
- **Lux dawn boost**: elev −1° (between floor and ceiling), lux
  rises past `lux_off_above` → phase flips DAY.
- **Sensor-lost fallback**: lux sensor goes `unavailable` mid-run →
  next `apply_scene` uses fallback path; scene may change because the
  decision function changed.
- **Floor lock at deep night**: elev −10°, someone shines a torch on
  the sensor (lux = 200) → still dark, still NIGHT/EVENING scene.
- **Multi-sensor median**: one sensor covered (5 lx) + two open
  (400 lx each) → median 400 → bright.

## Tests

All of Stage 4 is tests. Add a coverage check specific to this stage:
the blueprint reference and `logic.py` must agree on the sensor-less
parity trace at 100 % of sampled points, minus the documented
divergences.

## Exit criteria

- `pytest tests/test_parity.py` (+ lux focus) green.
- Divergence list matches what we implemented — no surprise mismatches
  during runs.
- Coverage totals still meet the overview's thresholds.

## Out of scope

- Live cutover — Stage 5.
- Docs update — Stage 6.
