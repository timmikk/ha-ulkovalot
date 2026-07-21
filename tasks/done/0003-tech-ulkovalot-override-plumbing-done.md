# Task: ulkovalot manual override plumbing (Stage 2b)

**Status:** done
**Issue:** #3
**Type:** tech
**Complexity:** small
**Version bump:** patch
**Created:** 2026-07-08
**Completed:** 2026-07-21

## Context

Stage 2b of the [Ulkovalot integration plan](0000-overview-integration-stages.md).
Adds the coordinator's override state machine and the two services
(`ulkovalot.override`, `ulkovalot.cancel_override`) in isolation —
before the sun/motion/lux subscriptions of Stage 3 tangle with the
timer restart / cancel / expiry logic. Enables tight, fast tests for
override edge cases.

---

Read the [overview](0000-overview-integration-stages.md) first for the
manual override semantics and testing strategy.

## Why a sub-stage

Override edge cases (timer restart on re-press, service + trigger
parity, explicit cancel, expiry re-evaluation) are subtle and
easy to break once they're tangled with sun/motion/lux subscriptions
in Stage 3. Isolating them here means their tests can run without a
full HA runtime and stay fast.

## Goal

The coordinator holds an override state machine and exposes the two
services from the overview. No sun/motion/lux wiring yet — those come
in Stage 3.

## Deliverables

`custom_components/ulkovalot/coordinator.py` (initial skeleton):

- Coordinator class holding:
  - `override_scene: str | None`
  - `override_until: datetime | None`
  - single `async_call_later` cancel handle for the expiry callback
- Instantiated in `async_setup_entry`; torn down in `async_unload_entry`
  (cancel the pending timer, deregister services if last entry).

Services registered in `async_setup_entry`:

- `ulkovalot.override(scene?: entity_id, duration?: seconds)`
  1. Resolve defaults from config for missing params.
  2. Cancel any existing expiry callback.
  3. Set `override_scene` + `override_until = now + duration`.
  4. Schedule new expiry via `async_call_later(duration, _on_expiry)`.
  5. Trigger a re-evaluation (a coordinator method that Stage 3 will
     flesh out — in Stage 2b it may just log + no-op, or hit a stub
     `apply_scene` that gets replaced later).
- `ulkovalot.cancel_override()`
  1. Cancel timer, clear state, trigger re-evaluation.

Optional configured `override_trigger` entity: subscribed via
`async_track_state_change_event`. Any state change on it is treated
as `ulkovalot.override()` with config defaults.

Re-press behaviour: cancel + reschedule with the new duration; swap
scene if a new one was passed.

Expiry callback: clear state, then re-evaluate — Stage 3 will make
this actually pick a new scene.

## Tests (`tests/test_override.py`)

Use `pytest-homeassistant-custom-component` for `hass` + config-entry
setup, but keep the override coordinator's re-evaluation stubbed
(monkey-patch or DI a fake `apply_scene`) so the tests only assert on
override state.

- Service `ulkovalot.override()` with no args → uses config defaults;
  sets scene + timer.
- Service with explicit `scene` + `duration` → overrides both.
- Re-press within active window → old timer cancelled, new one set;
  scene replaced if new one passed.
- Explicit `ulkovalot.cancel_override()` → state cleared, timer
  cancelled, re-evaluation fired.
- Expiry via `async_fire_time_changed`: state clears, re-evaluation
  fired once.
- Configured trigger entity state change → same effect as service
  call with defaults.
- Unload entry → timer cancelled, services deregistered on last
  entry.

Target: coverage of the override paths in `coordinator.py`. See the
overview for shared fixtures + clock control (`advance`,
`installed`).

## Exit criteria

- `pytest tests/test_override.py` green.
- Override behaviour fully specified by tests, independently of any
  sun/motion/lux wiring.

## Out of scope

- Motion / lux / sun / time subscriptions — Stage 3.
- Actual `scene.turn_on` dispatch — Stage 3 (Stage 2b tests use a
  stubbed apply function).
- Blueprint parity — Stage 4.

## Actual commits

- 8774f84 feat(coordinator): add override state machine
- c0b09f3 feat(services): register override and cancel_override services
- 9bca7b8 test(override): cover state machine, services, and trigger entity
