# Task: ulkovalot runtime logging

**Status:** done
**Issue:** #9
**Type:** tech
**Complexity:** small
**Version bump:** patch
**Created:** 2026-08-26
**Completed:** 2026-08-26

## Context

The integration currently logs almost nothing: `coordinator.py` has
three `_LOGGER.debug` calls for edge cases (a cancelled apply, an
unresolved scene key, `scene.turn_on` not yet available), and
`__init__.py` / `config_flow.py` have no logger at all. When something
looks wrong on a live install — the wrong scene fires, an override
doesn't start, a service call is ignored — there is no trail in the HA
log to explain why. This adds structured logging across the entry
lifecycle, the override state machine, and each scene-decision cycle
so `logger: custom_components.ulkovalot: debug` in HA's
`configuration.yaml` gives a full picture of what the integration did
and why.

---

## Work items

### 1. Entry lifecycle + service-call logging
**Files:** `custom_components/ulkovalot/__init__.py`

Add a module logger and log the points where HA hands control to (or
takes it back from) this integration, and where a user-invoked service
call arrives.

- [x] Add `_LOGGER = logging.getLogger(__name__)`
- [x] `async_setup_entry`: `_LOGGER.debug("Setting up entry %s", entry.entry_id)` before starting the coordinator, `_LOGGER.info("ulkovalot entry %s set up", entry.entry_id)` after
- [x] `async_unload_entry`: `_LOGGER.debug("Unloading entry %s", entry.entry_id)` before `coordinator.unload()`
- [x] `_handle_override`: `_LOGGER.info("Service override called: scene=%s duration=%s", call.data.get("scene"), call.data.get("duration"))`
- [x] `_handle_cancel`: `_LOGGER.info("Service cancel_override called")`

### 2. Override state-machine logging
**Files:** `custom_components/ulkovalot/coordinator.py`

The override state machine (`start_override`, `cancel_override`, expiry)
is the part most likely to be triggered by a person or an automation
and most useful to trace.

- [x] `start_override`: `_LOGGER.info("Override started: scene=%s until=%s", self.override_scene, self.override_until)` after setting `self.override_until`
- [x] `cancel_override`: `_LOGGER.info("Override cancelled")` before `apply_scene()`
- [x] `_on_expiry`: `_LOGGER.info("Override expired")` before `_clear_override_state()`
- [x] `wire_trigger`: `_LOGGER.debug("Subscribed override trigger: %s", trigger)` when a trigger entity is configured

### 3. Scene-decision logging in the apply cycle
**Files:** `custom_components/ulkovalot/coordinator.py`

`_apply_scene_impl` is where every input (disable flag, sun, lux,
motion, override) gets turned into a scene dispatch. Log the inputs
and the outcome at `debug` so a full trace is available without being
noisy at default log levels; keep the dispatch itself visible at
`debug` too (matches the existing `_LOGGER.debug` calls right below
it, so the whole function reads consistently).

- [x] Early-return when `disable_flag` is on: `_LOGGER.debug("Disabled via %s — skipping apply", cfg.disable_flag)`
- [x] After computing `phase`, `motion`, `override`, `scene_key`: `_LOGGER.debug("Apply: elev=%.1f lux=%s dark=%s phase=%s motion=%s override=%s -> %s", elev, lux, self.last_dark, phase, motion, override, scene_key)`
- [x] Right before `async_call(SCENE_DOMAIN, ...)`: `_LOGGER.debug("Dispatching scene.turn_on entity=%s transition=%s", entity, transition)`

### 4. Sun-crossing + motion-timeout trace logging
**Files:** `custom_components/ulkovalot/coordinator.py`

Lower-value but cheap context for why a re-evaluation fired at all.

- [x] `_on_sun_state`: when `_crossed(...)` is true, `_LOGGER.debug("Sun elevation crossed threshold: %.1f -> %.1f", old_elev, new_elev)` before `self._schedule_apply()`
- [x] `_on_watched_state`: `_LOGGER.debug("Watched entity changed: %s -> %s", entity_id, new.state if new else None)` before `self._schedule_apply()`

---

## Rollout / state invalidation

n/a — fully transparent to in-flight clients. Logging is additive and
carries no persisted or client-cached state; no HA restart semantics
change.

---

## Test updates

Use `caplog` (already available via pytest) to assert on log records
rather than string-matching the whole log; set `caplog.set_level(logging.DEBUG, logger="custom_components.ulkovalot.coordinator")`
(and `...__init__`) per test as needed.

- [x] `tests/test_init.py` — new test asserting `async_setup_entry` logs an INFO "set up" record containing the entry id; new test asserting the `override` and `cancel_override` service handlers each log an INFO record when called
- [x] `tests/test_coordinator.py` — new test asserting `start_override` logs INFO containing the resolved scene; new test asserting `cancel_override` logs INFO; new test asserting `_on_expiry` logs INFO "expired"; new test (DEBUG level) asserting `_apply_scene_impl` logs the decision summary line with the resolved `scene_key`; new test asserting the disable-flag short-circuit logs DEBUG and skips dispatch

---

## Commit plan

| # | Scope | Files | Message |
|---|-------|-------|---------|
| 1 | init | `custom_components/ulkovalot/__init__.py`, `tests/test_init.py` | `feat(ulkovalot): log entry lifecycle and service calls` |
| 2 | coordinator | `custom_components/ulkovalot/coordinator.py`, `tests/test_coordinator.py` | `feat(ulkovalot): log override state machine and apply decisions` |
| 3 | wrap-up | rename to `tasks/done/0009-tech-runtime-logging-done.md`, set `Status: done` and `Completed: <date>` | `chore: mark runtime-logging plan as done` |

---

## Definition of done

- [x] All work items above are checked off
- [x] Rollout / state invalidation reflected (n/a, noted above)
- [x] Tests in "Test updates" added/updated
- [x] `logger: custom_components.ulkovalot: debug` in a test HA config surfaces a full decision trace for one apply cycle (spot-checked manually or via the new tests' captured records)

## Actual commits

- c037792 feat(ulkovalot): log entry lifecycle and service calls
- 3ac79ff feat(ulkovalot): log override state machine and apply decisions
