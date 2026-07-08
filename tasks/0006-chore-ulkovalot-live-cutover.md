# Task: ulkovalot live cutover in home-assistant-config (Stage 5)

**Status:** pending
**Issue:** #6
**Type:** chore
**Complexity:** small
**Version bump:** patch
**Created:** 2026-07-08
**Completed:** —

## Context

Stage 5 of the [Ulkovalot integration plan](0000-overview-integration-stages.md).
Deploys the component on the live HA instance via HACS, disables (not
deletes) the old blueprint and the five raw *Ulkovalot* automations in
`home-assistant-config/automations.yaml`, observes ≥ 48 h, then
deletes the retired artefacts and updates
`AUTOMATION-INVENTORY.md`. No code changes in this repo; this is
purely a deployment + cleanup stage in the sibling config repo.

---

Read the [overview](0000-overview-integration-stages.md) for the
reference to the retired blueprint + raw automations and the
inventory row that tracks migration state.

## Goal

The deployed HA instance runs the `ulkovalot` component, not the
`testi/ulkovalot.yaml` blueprint or the five *Ulkovalot* raw
automations. The old artefacts are disabled first, observed, and then
deleted only after we're confident.

## Deliverables

Steps executed against `~/dev/home-assistant-config` (repo
`timo/home-assistant-config`) and the live HA instance:

1. **Release a pre-cutover build**
   - Tag a `v0.9.0` (or similar `-rc`) on `ha-ulkovalot` so HACS
     surfaces a specific version, not the moving `main`.
2. **Install via HACS on live**
   - Add the integration in the UI.
   - Populate the config entry to mirror the current blueprint
     instance: same times, same motion sensors, same scenes, same
     disable flag, same waits/transitions.
   - Leave `illuminance_sensors` empty for the first day — proves
     the sun fallback path works on the live instance before we add
     the new sensor plumbing.
3. **Disable overlapping automations (do not delete)**
   - Blueprint automation `Ulkovalojen ohjaus`: set `initial_state:
     false` in `automations.yaml` (or the UI equivalent).
   - Five raw *Ulkovalot* automations: same treatment.
   - Commit the change to `home-assistant-config` referencing this
     plan (`Ref: ha-ulkovalot#0007-stage-5-cutover`).
4. **Observe ≥ 48 h**
   - Motion, dawn, dusk, night dim all fire correctly.
   - Disable flag still bypasses.
   - No `scene.turn_on` storms in the log.
   - If anything is wrong: **re-enable the old automations**,
     disable the component, fix forward with a new stage-3 or
     stage-4 test, ship a new tag, retry.
5. **Add lux sensors (optional smoke)**
   - Reconfigure the entry to include the actual illuminance
     sensor(s) from the deployment.
   - Watch for one full dark→bright cycle before declaring done.
6. **Delete the retired artefacts**
   - Remove the six automations from `automations.yaml`.
   - Delete `blueprints/automation/testi/ulkovalot.yaml`.
   - Update `AUTOMATION-INVENTORY.md`: all six Ulkovalot rows →
     `Status: migrated` / `Target: component:ha-ulkovalot`.
   - Commit as a single `chore:` in `home-assistant-config`.

## Rollback plan

If anything goes wrong at any step:

- Re-enable the disabled automations in `automations.yaml` (git
  revert the disable commit is fine).
- Remove the `ulkovalot` config entry in the HA UI or set the
  integration to disabled.
- Open a Forgejo issue on `ha-ulkovalot` describing what broke, and
  file a follow-up test in the appropriate stage's suite so the
  regression is caught next time.

## Exit criteria

- Only the component controls the outdoor lights on the live
  instance for ≥ 48 h without incidents.
- The six retired automations and the blueprint file are deleted
  from `home-assistant-config` on `main`.
- `AUTOMATION-INVENTORY.md` reflects the migration.

## Out of scope

- Documentation + `v1.0.0` release — Stage 6.
