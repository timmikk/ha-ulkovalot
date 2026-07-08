# Task: ulkovalot config flow surface (Stage 1)

**Status:** done
**Issue:** #1
**Type:** feature
**Complexity:** medium
**Version bump:** minor
**Created:** 2026-07-08
**Completed:** 2026-07-08

## Context

Stage 1 of the [Ulkovalot integration plan](0000-overview-integration-stages.md).
Builds the full config + options flow so a user can add the integration
and enter every input the coordinator will need. No behaviour yet;
nothing subscribes, no `scene.turn_on` runs. Downstream stages depend
on this schema being stable.

---

Read the [overview](0000-overview-integration-stages.md) first — it
holds the shared feature surface, dark/bright rules, phase derivation,
testing strategy, and non-goals every stage relies on. This file only
carries the delta specific to Stage 1.

## Goal

A user can add the integration in the UI and enter every input listed
in the overview's *Feature surface*. Nothing runs yet — no
subscriptions, no `scene.turn_on` calls. This stage builds the schema
that Stages 2b and 3 later consume.

## Deliverables

- `config_flow.py`
  - `async_step_user`: single-instance abort, then a schema covering
    the full input set. Use HA selectors matching each field:
    - Times: `TimeSelector`.
    - Motion / illuminance / scenes / disable / override trigger:
      `EntitySelector` with domain + `multiple` where appropriate
      (`motion_sensors`, `illuminance_sensors`).
    - Number inputs: `NumberSelector` with min/max/step/unit.
  - `async_step_reconfigure` for editing the initial set.
  - `OptionsFlow` for values that should be editable at runtime
    (thresholds, times, waits, transitions). Sensor lists and scene
    selectors stay in the initial set — changing them warrants a
    reconfigure.
- `const.py`
  - Domain, config keys (as constants — no bare strings anywhere else),
    default values, min/max ranges, units.
  - `PLATFORMS = []` — no entities in this stage.
- Split `entry.data` (immutable identity: sensors, scenes) from
  `entry.options` (tunables: thresholds, times, waits).
- Input validation:
  - `lux_off_above > lux_on_below` (hysteresis must be positive).
  - `sun_elev_bright_ceiling > sun_elev_dark_floor`.
  - Rejects with a form error, not a stack trace.
- No behaviour changes to `__init__.py` beyond ensuring
  `hass.data[DOMAIN]` is initialised.

## Tests (`tests/test_config_flow.py`)

- User step happy path (all fields set) → creates entry with expected
  `data` + `options` split.
- Single-instance abort on second attempt.
- Options-flow round trip: set new values → reopen → sees them.
- Reconfigure flow: swap a sensor list, verify new values persist.
- Validation errors: inverted hysteresis, inverted sun-elev
  thresholds. Confirm the flow returns to the form with the right
  error key, not an exception.

Target: ≥ 90 % coverage of `config_flow.py`. See the overview's
*Testing strategy* for fixtures + coverage tooling.

## Exit criteria

- `pytest tests/test_config_flow.py` green.
- `hassfest` + `hacs/action` green in CI.
- Adding the integration in a dev HA instance produces a config entry
  with every input populated; reconfiguring and options-flow both
  persist changes across restart.

## Out of scope

- Any subscription or scene call — Stage 3.
- Override services — Stage 2b.
- `logic.py` — Stage 2.

Version: stays at `0.0.1`. No release tag from this stage alone; it's
released together with Stage 2 as `0.1.0`.

## Actual commits

- 1262c1f feat(const): add config keys, defaults, and ranges
- 875b769 feat(config_flow): implement user, reconfigure, and options flows
- 7e7b2ce test(config_flow): cover happy path, abort, options, reconfigure, validation
