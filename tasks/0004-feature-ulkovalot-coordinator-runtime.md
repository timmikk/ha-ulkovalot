# Task: ulkovalot coordinator runtime wiring (Stage 3)

**Status:** pending
**Issue:** #4
**Type:** feature
**Complexity:** large
**Version bump:** minor
**Created:** 2026-07-08
**Completed:** —

## Context

Stage 3 of the [Ulkovalot integration plan](0000-overview-integration-stages.md).
Wires the coordinator into the full HA runtime: subscribes to motion
sensors, illuminance sensors, sun elevation crossings, night-window
time triggers, HA start, automation/scene reloads, disable flag, and
the override trigger. On any event: recomputes via `logic.py` and
calls `scene.turn_on` with the right transition. First stage where
the integration observably controls lights.

---

Read the [overview](0000-overview-integration-stages.md) first for the
dark/bright decision, phase derivation, choose priority, trigger set,
and testing strategy.

## Goal

On every relevant event, the coordinator recomputes the target scene
via `logic.py` and calls `scene.turn_on`. The override state machine
from Stage 2b now composes with the full trigger set.

## Deliverables

`custom_components/ulkovalot/coordinator.py` (fleshed out):

- Resolve config from `entry.data` + `entry.options` into a plain
  dataclass on setup.
- Subscribe to:
  - `async_track_state_change_event` on: every motion sensor, every
    configured illuminance sensor, disable flag, override trigger.
  - `async_track_state_change_event` on `sun.sun` — handler filters on
    `elevation` attribute crossings at `sun_elev_dark_floor` and
    `sun_elev_bright_ceiling`.
  - `async_track_time_change` at `night_scene_start_time` and
    `night_scene_end_time`.
  - `EVENT_HOMEASSISTANT_STARTED`.
  - `EVENT_AUTOMATION_RELOADED`, `EVENT_SCENE_RELOADED`.
- On any trigger event: `apply_scene()`
  1. If disable flag entity is `on` → skip (do not clear override).
  2. Read current motion states, sun `rising`/`elevation`, aggregated
     lux (via `aggregate_lux`), override state, `now`.
  3. Call `is_dark` (with stored `last_dark` for hysteresis).
  4. Call `derive_phase` → phase.
  5. Call `motion_active` → motion.
  6. Call `pick_scene` → target scene + transition.
  7. Call `hass.services.async_call('scene', 'turn_on', ...)` with
     the target entity and the resolved transition seconds.
- `restart` semantics: a single asyncio Task in the coordinator;
  cancel + reschedule on a new trigger while one is in flight. Silent
  on overrun (log at `debug` only).
- Motion-timeout re-fire: `async_call_later(no_motion_wait, apply_scene)`
  on any motion `on → off`. Matches the blueprint's `for:`.
- `last_dark` persisted in coordinator memory; NOT in `hass.data`
  across restarts — on startup, the first `apply_scene` recomputes
  fresh with the current lux + sun state.
- Wire coordinator lifecycle from `async_setup_entry`; cancel all
  subscriptions and timers in `async_unload_entry`.
- Override expiry callback (from Stage 2b) now calls the full
  `apply_scene`.

## Tests (`tests/test_coordinator.py`)

Use `pytest-homeassistant-custom-component` with `MockConfigEntry` +
shared fixtures from the overview (`mock_sun`, `mock_lux`,
`mock_motion`, `advance`, `installed`). Mock `scene.turn_on` via
`hass.services.async_register` or `async_mock_service`.

Scenarios (each asserts `scene.turn_on` targets + `transition`
values + call count):

- Startup: entity added → `apply_scene` runs once, picks the correct
  scene for the current environment.
- Motion pulse when dark: `scene_motion` fires with
  `transition_time_motion`.
- Motion timeout: after `no_motion_wait` seconds, re-fires with the
  underlying phase scene at `transition_time`.
- Sun crosses `sun_elev_bright_ceiling`: phase flips to DAY, scene
  changes.
- Lux drops below `lux_on_below` mid-day (storm): dark → phase
  becomes EVENING/MORNING depending on `rising`; DAY→EVENING scene
  change fires.
- Time hits `night_scene_start_time`: while dark, phase flips to
  NIGHT, `scene_night` fires.
- Disable flag `on`: no `scene.turn_on` calls, but override state
  still updated by service calls.
- Override active: any other trigger during override → still uses
  `override_scene`, doesn't reset the timer.
- Sun elev at floor lock: lux over `lux_off_above` → still dark
  (floor wins).
- Restart semantics: two rapid triggers → first task cancelled, only
  one `scene.turn_on` from the second (or exactly one debounced
  call).

Target: **≥ 90 % coverage of `coordinator.py`**.

## Exit criteria

- `pytest tests/test_coordinator.py` green.
- Manual smoke test in a dev HA instance shows scenes firing on
  motion, lux crossings, sun crossings, and time triggers; disable
  flag bypasses; override wins.
- `pytest` + `hassfest` + `hacs/action` green in CI.

## Out of scope

- Blueprint parity replay — Stage 4.
- Live cutover — Stage 5.
