# Task: ulkovalot v1.0.0 release and docs (Stage 6)

**Status:** pending
**Issue:** #7
**Type:** docs
**Complexity:** small
**Version bump:** major
**Created:** 2026-07-08
**Completed:** —

## Context

Stage 6 of the [Ulkovalot integration plan](0000-overview-integration-stages.md).
Component has been running on the live instance since Stage 5; this
stage tags `v1.0.0` on Forgejo → GitHub mirror → HACS UI, adds the
full configuration reference to `README.md`, documents the two
services (`ulkovalot.override`, `ulkovalot.cancel_override`), and
updates `info.md` for the HACS listing. Also closes the six sibling
Forgejo issues with `Done: #N` trailers in the release commit.

---

Read the [overview](0000-overview-integration-stages.md) for the
pipeline reference and testing strategy.

## Goal

`v1.0.0` on Forgejo → GitHub mirror → HACS UI, with docs sufficient
for someone unfamiliar with the blueprint to configure the
integration from scratch.

## Deliverables

**Version bump**

- `custom_components/ulkovalot/manifest.json` → `1.0.0`.
- `CHANGELOG.md` entry summarising the whole plan (config-flow,
  logic engine, override, ambient lux, coordinator, parity tests,
  cutover).
- Tag `v1.0.0` on Forgejo `main`. Mirror syncs to GitHub. GitHub
  Actions release workflow creates the Release object. HACS picks
  it up in the UI.

**`README.md`**

- "What this replaces" section pointing at the retired blueprint +
  the five raw automations by name; link to the
  `home-assistant-config` commit that removed them.
- Configuration reference table for every input in the config flow,
  grouped as:
  - Phase times (`night_scene_start_time`, `night_scene_end_time`).
  - Ambient lux (`illuminance_sensors`, `lux_on_below`,
    `lux_off_above`).
  - Sun elevation safety (`sun_elev_dark_floor`,
    `sun_elev_bright_ceiling`; note the ceiling doubles as fallback).
  - Motion (`motion_sensors`, `no_motion_wait`).
  - Scenes (`scene_day` / `_morning` / `_evening` / `_night` /
    `_motion`, `transition_time`, `transition_time_motion`).
  - Manual override (`override_scene`, `override_duration`,
    `override_trigger`).
  - Bypass (`disable_flag`).
- Explicit call-out of the phase-semantics shift vs the blueprint:
  night dim scene has a time window (default 23:00–07:00);
  evening/morning are lux- or sun-driven, not time-bounded. Explain
  why (sunset/sunrise drift through the year).

**Services documentation**

- `services.yaml` (new) declaring `override` and `cancel_override`
  with `fields:` blocks so the Developer Tools UI shows a form.
- README section documenting each service: parameters, defaults,
  re-press behaviour, use cases (wall button, dashboard button,
  voice).

**`info.md`** (HACS listing text)

- One-paragraph feature summary (parity + override + ambient lux).
- Screenshot placeholder or brief step-by-step for the config flow.
- Rollback note (disable the integration → re-enable the retired
  blueprint from `home-assistant-config` history if truly needed).

**Housekeeping**

- Close the infra intake issue (if one was opened) and any Forgejo
  issues opened during the plan with `Done: #N` trailers in the
  release commit.
- Update the [overview](0001-integration-stages.md) status if we
  add one — for now, the file's stage index is enough.

## Tests

No new behavioural tests here. Sanity check:

- Docs match the current constants in `const.py` — a small
  README-vs-const check script is optional; a manual scan is fine.
- `hassfest` + `hacs/action` + `pytest` still green on the `v1.0.0`
  commit.

## Exit criteria

- HACS UI offers `v1.0.0`.
- README lets a fresh user configure the integration without
  reading the source.
- All Forgejo issues connected to this plan closed.

## Post-release (out of scope for this plan)

Left as follow-up plans in `tasks/`:

- Per-scene transition timings.
- Per-sensor motion wait.
- Aggregation mode selector for lux (`median` / `min` / `max`).
- Multi-zone (multiple config entries controlling different
  outdoor areas).
