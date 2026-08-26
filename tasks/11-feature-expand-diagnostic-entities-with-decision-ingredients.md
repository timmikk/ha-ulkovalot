# Task: Expand diagnostic entities with decision ingredients

**Status:** pending
**Issue:** #11
**Type:** feature
**Complexity:** medium
**Version bump:** minor
**Created:** 2026-08-26
**Completed:** —

## Context

The `reason` sensor added in #10 reports a flat branch name — `night` — that collapses three
independent facts into one word: whether the sun says dark, whether lux says dark, and whether
the clock is inside the configured night window. None of the three is observable, so a wrong
scene can't be diagnosed from the UI. Every ingredient is already computed inside
`_apply_scene_impl`; it is simply discarded after the decision is made.

This task exposes each ingredient as its own entity, exposes the configured thresholds that gate
them (as attributes everywhere, and as real sensors for the four values worth overlaying on a
history graph), and fixes the missing options-reload path that would otherwise leave those
threshold sensors permanently stale.

No decision behaviour changes — `derive_phase`, `pick_scene`, and `selection_reason` keep their
exact current semantics.

---

## Work items

### 1. Split `is_dark` into observable ingredients
**Files:** `custom_components/ulkovalot/logic.py`

`is_dark()` currently returns a bare bool, discarding which of its four branches fired. Add an
enum for the deciding branch and three pure helpers for the individual ingredients. The helpers
must be *derived from the same thresholds* as `is_dark`, not a parallel reimplementation, so the
parity test in work item 7 can hold them to `is_dark`'s actual branch.

Semantics to preserve exactly (from the current `logic.py:77-92`):

| Condition | `is_dark` result | `DarknessSource` |
|---|---|---|
| `lux is None` | `elev < bright_ceiling` | `no_lux_fallback` |
| `elev <= dark_floor` | `True` | `sun_below_floor` |
| `elev >= bright_ceiling` | `False` | `sun_above_ceiling` |
| between, `last_dark` and `lux < lux_off_above` | `True` | `lux_hysteresis_hold` |
| between, `last_dark` and `lux >= lux_off_above` | `False` | `lux_threshold` |
| between, not `last_dark`, `lux <= lux_on_below` | `True` | `lux_threshold` |
| between, not `last_dark`, `lux > lux_on_below` | `False` | `lux_threshold` |

Note the asymmetry in the hysteresis band: `lux_hysteresis_hold` means "the previous dark state
was retained because lux sat inside the band"; `lux_threshold` means "lux crossed a threshold and
decided". Pin this in the tests so it can't silently drift.

- [ ] Add `class DarknessSource(str, Enum)` with members `SUN_BELOW_FLOOR = "sun_below_floor"`,
      `SUN_ABOVE_CEILING = "sun_above_ceiling"`, `LUX_THRESHOLD = "lux_threshold"`,
      `LUX_HYSTERESIS_HOLD = "lux_hysteresis_hold"`, `NO_LUX_FALLBACK = "no_lux_fallback"`
- [ ] Add `class SunDarkness(str, Enum)` with `DARK = "dark"`, `AMBIGUOUS = "ambiguous"`,
      `BRIGHT = "bright"`
- [ ] Add `class LuxDarkness(str, Enum)` with `DARK = "dark"`, `HOLD = "hold"`,
      `BRIGHT = "bright"`, `UNKNOWN = "unknown"`
- [ ] Change `is_dark()` to return `tuple[bool, DarknessSource]`, following the table above
- [ ] Add `sun_darkness(elev, cfg) -> SunDarkness` — `DARK` when `elev <= dark_floor`, `BRIGHT`
      when `elev >= bright_ceiling`, else `AMBIGUOUS`
- [ ] Add `lux_darkness(lux, cfg) -> LuxDarkness` — `UNKNOWN` when `lux is None`, `DARK` when
      `lux <= lux_on_below`, `BRIGHT` when `lux >= lux_off_above`, else `HOLD`. This is the
      *standalone* lux verdict; it deliberately ignores sun elevation, which is what makes it a
      separate ingredient from `is_dark`'s combined answer
- [ ] Add `in_night_window(now, cfg) -> bool` — extract the existing
      `t >= cfg.night_start or t < cfg.night_end` expression from `derive_phase` and have
      `derive_phase` call the new helper, so the two can never diverge

### 2. Carry the ingredients through the coordinator
**Files:** `custom_components/ulkovalot/coordinator.py`

`_read_sun` reads `rising` and returns it, but `_apply_scene_impl` only uses it as an argument to
`derive_phase` and never stores it. All five new facts are available at the point the snapshot is
built.

- [ ] Add fields to `DiagnosticsSnapshot`: `sun_darkness: SunDarkness`,
      `lux_darkness: LuxDarkness`, `darkness_source: DarknessSource`, `night_window: bool`,
      `rising: bool`
- [ ] Update the initial snapshot in `__init__` with sensible defaults matching the existing
      `phase=Phase.DAY, dark=False` shape — `sun_darkness=BRIGHT`, `lux_darkness=UNKNOWN`,
      `darkness_source=NO_LUX_FALLBACK`, `night_window=False`, `rising=False`
- [ ] In `_apply_scene_impl`, unpack the new `is_dark` tuple into `self.last_dark` and a local
      `darkness_source`, and compute `sun_darkness`, `lux_darkness`, `in_night_window` alongside
      it; populate the snapshot from those locals
- [ ] Extend the existing `_LOGGER.debug("Apply: ...")` line with `source=%s` so the log and the
      entities tell the same story

### 3. Reload the entry when options change
**Files:** `custom_components/ulkovalot/__init__.py`

`UlkovalotOptionsFlow` exists (`config_flow.py:335`) and writes merged options, but nothing in
the integration calls `entry.add_update_listener`, and `RuntimeConfig.from_entry` is snapshotted
once in `UlkovalotCoordinator.__init__`. Saving new thresholds therefore has no effect until HA
restarts. This is a pre-existing bug; the threshold sensors in work item 6 would surface it as
visibly wrong numbers on a graph, so fix it here.

- [ ] In `async_setup_entry`, register `entry.async_on_unload(entry.add_update_listener(_async_update_listener))`
- [ ] Add `async def _async_update_listener(hass, entry)` calling
      `await hass.config_entries.async_reload(entry.entry_id)`
- [ ] Confirm the reload path is clean: `async_unload_entry` already pops the coordinator and
      calls `coordinator.unload()`, which cancels every subscription and timer, so a reload
      rebuilds `RuntimeConfig` from the updated entry with no leaked listeners

### 4. Attributes on the existing nine entities
**Files:** `custom_components/ulkovalot/sensor.py`, `custom_components/ulkovalot/binary_sensor.py`

Values and states are unchanged. Read thresholds from `self.coordinator.config` (the
`RuntimeConfig`), not from the snapshot. Serialise the two `datetime.time` values with
`.isoformat()`.

- [ ] `IlluminanceSensor` — `lux_on_below`, `lux_off_above`
- [ ] `SunElevationSensor` — `sun_elev_dark_floor`, `sun_elev_bright_ceiling`
- [ ] `PhaseSensor` — `night_start`, `night_end`
- [ ] `CurrentSceneSensor` — `scene_key`, `transition`. Neither is in the snapshot today; add
      `scene_key: str` and `transition: float` to `DiagnosticsSnapshot` in work item 2 and
      populate them from the `pick_scene` result and the resolved `getattr(cfg, transition_key)`
- [ ] `MotionBinarySensor` — `no_motion_wait`
- [ ] Leave `OverrideActiveBinarySensor` (already has `scene` / `until`), `ReasonSensor`,
      `DarkBinarySensor`, `DisabledBinarySensor` without attributes

### 5. Six new ingredient entities
**Files:** `custom_components/ulkovalot/sensor.py`, `custom_components/ulkovalot/binary_sensor.py`

All `EntityCategory.DIAGNOSTIC` via the existing `_DiagnosticSensor` / `_DiagnosticBinarySensor`
base classes, so they inherit the device and the coordinator-listener wiring for free.

Sensors (`sensor.py`):

- [ ] `SunDarknessSensor` — key `sun_darkness`, name "Sun darkness", `SensorDeviceClass.ENUM`,
      options `["dark", "ambiguous", "bright"]`. Attributes: `elevation`, `dark_floor`,
      `bright_ceiling`
- [ ] `LuxDarknessSensor` — key `lux_darkness`, name "Lux darkness", `SensorDeviceClass.ENUM`,
      options `["dark", "hold", "bright", "unknown"]`. Attributes: `illuminance`,
      `lux_on_below`, `lux_off_above`
- [ ] `DarknessSourceSensor` — key `darkness_source`, name "Darkness source",
      `SensorDeviceClass.ENUM`, options `["sun_below_floor", "sun_above_ceiling",
      "lux_threshold", "lux_hysteresis_hold", "no_lux_fallback"]`
- [ ] `LastEvaluatedSensor` — key `last_evaluated`, name "Last evaluated",
      `SensorDeviceClass.TIMESTAMP`, value `diagnostics.updated_at`. No `state_class` — HA
      rejects a state class on a timestamp sensor
- [ ] Derive the enum option lists from the new `logic.py` enums
      (`[m.value for m in SunDarkness]`) rather than hand-typing string literals, matching what
      the existing `_PHASE_OPTIONS` does not do but should — a hand-typed list that drifts from
      the enum makes HA drop the state as invalid

Binary sensors (`binary_sensor.py`):

- [ ] `NightWindowBinarySensor` — key `night_window`, name "Night window",
      `diagnostics.night_window`. Attributes: `night_start`, `night_end`. Docstring must state
      that this is **time only** and does not feed `is_dark()` — it only splits an already-dark
      state into night vs. morning/evening
- [ ] `SunRisingBinarySensor` — key `sun_rising`, name "Sun rising", `diagnostics.rising`
- [ ] Register all six in the respective `async_setup_entry` lists

### 6. Four threshold sensors for graph overlays
**Files:** `custom_components/ulkovalot/sensor.py`

Real numeric entities so they can be plotted as threshold lines against the Illuminance and Sun
elevation curves. These read `RuntimeConfig`, not the per-cycle snapshot — but they still extend
`_DiagnosticSensor` so that a coordinator notification refreshes them, and work item 3's reload
gives them a fresh `RuntimeConfig` when options change.

- [ ] `LuxOnBelowSensor` — key `lux_on_below`, name "Lux on below", unit `lx`,
      `SensorStateClass.MEASUREMENT`, `SensorDeviceClass.ILLUMINANCE`
- [ ] `LuxOffAboveSensor` — key `lux_off_above`, name "Lux off above", same classes
- [ ] `SunElevDarkFloorSensor` — key `sun_elev_dark_floor`, name "Sun elevation dark floor",
      unit `°`, `SensorStateClass.MEASUREMENT`, no device class (HA has none for elevation —
      matches the existing `SunElevationSensor`)
- [ ] `SunElevBrightCeilingSensor` — key `sun_elev_bright_ceiling`, name "Sun elevation bright
      ceiling", same as above
- [ ] Use `LUX_UNIT` and `SUN_ELEV_UNIT` from `const.py` rather than repeating the literals
- [ ] Register all four in `async_setup_entry`

Explicitly **not** entities, per the design decision: `no_motion_wait`, `transition_time`,
`transition_time_motion`, `override_duration` (no curve to overlay against) and
`night_scene_start_time` / `night_scene_end_time` (not numeric). They remain attributes from
work item 4.

### 7. Parity guard for the darkness source
**Files:** `tests/test_parity.py`

The whole point of `DarknessSource` is that it names the branch `is_dark` actually took. A
hand-maintained mapping would rot. Add a property-style check that sweeps the input space and
asserts the reported source is consistent with the returned bool and the thresholds.

- [ ] Sweep elevation across `[dark_floor - 5, bright_ceiling + 5]` and lux across
      `[None, 0, lux_on_below, midpoint, lux_off_above, 10000]` for both `last_dark` values
- [ ] Assert: `source == SUN_BELOW_FLOOR` implies `dark is True` and `elev <= dark_floor` and
      `lux is not None`
- [ ] Assert: `source == SUN_ABOVE_CEILING` implies `dark is False` and `elev >= bright_ceiling`
      and `lux is not None`
- [ ] Assert: `source == NO_LUX_FALLBACK` implies `lux is None`
- [ ] Assert: the two `LUX_*` sources imply `dark_floor < elev < bright_ceiling` and
      `lux is not None`
- [ ] Assert: `source == LUX_HYSTERESIS_HOLD` implies `last_dark is True` and `dark is True`
- [ ] Update the existing trace-comparison helpers for the new `is_dark` tuple return

### 8. Changelog entry
**Files:** `CHANGELOG.md`

`.forgejo/workflows/release.yml` builds the GitHub Release body by awk-extracting this version's
section out of `CHANGELOG.md` (falling back to a bare `Release <tag>` line if the section is
empty). An entry under `[Unreleased]` is therefore the only thing that produces real release
notes — without it the release for this change ships with no description.

- [ ] Add an `### Added` entry under `[Unreleased]` covering the ten new diagnostic entities
      (six ingredients + four thresholds) and the threshold attributes on the existing nine.
      Match the prose style of the `0.10.0` entry: what became observable and why it matters,
      not a bare entity list
- [ ] Add a `### Fixed` entry under `[Unreleased]` for the options-reload bug from work item 3 —
      saving options in the UI previously had no effect until Home Assistant restarted. This is
      the user-visible behaviour change and must not be buried in the Added entry
- [ ] Leave the version heading alone — release tooling promotes `[Unreleased]` at bump time

---

## Rollout / state invalidation

n/a — fully server-side within Home Assistant, no client-cached shape.

Two operator-visible notes, both listed under "Definition of done":

- The ten new entities appear under the device's Diagnostics section after the integration
  reloads. Existing entities keep their unique ids (`{entry_id}-{key}`) and are untouched, so no
  history is lost and no entity is renamed.
- Work item 3 changes behaviour that users may have worked around: saving options now reloads the
  entry immediately instead of silently requiring an HA restart. Call this out in the release
  notes.

---

## Test updates

- [ ] `tests/test_logic.py` — `is_dark` cases updated for the tuple return; new
      `test_is_dark_source` covering all five `DarknessSource` members including both hysteresis
      directions; `test_sun_darkness` covering the two boundaries (`elev == dark_floor` → `DARK`,
      `elev == bright_ceiling` → `BRIGHT`) and the ambiguous middle; `test_lux_darkness` covering
      `None` → `UNKNOWN`, both inclusive boundaries, and the `HOLD` band;
      `test_in_night_window` covering the wrapping window (23:00→07:00: 23:30 true, 06:59 true,
      12:00 false) and asserting `derive_phase` agrees with it
- [ ] `tests/test_parity.py` — the darkness-source consistency sweep from work item 7, plus the
      tuple-return updates to the existing traces
- [ ] `tests/test_sensor.py` — state mapping for `SunDarknessSensor`, `LuxDarknessSensor`,
      `DarknessSourceSensor`, `LastEvaluatedSensor` and the four threshold sensors; assert every
      new sensor is `EntityCategory.DIAGNOSTIC`; assert each ENUM sensor's `native_value` is a
      member of its own `_attr_options` (catches enum/option drift); assert the new
      `extra_state_attributes` on `IlluminanceSensor`, `SunElevationSensor`, `PhaseSensor`,
      `CurrentSceneSensor`
- [ ] `tests/test_binary_sensor.py` — `NightWindowBinarySensor` and `SunRisingBinarySensor` state
      mapping; `MotionBinarySensor`'s new `no_motion_wait` attribute
- [ ] `tests/test_coordinator.py` — after an apply cycle, assert the snapshot carries all five
      new fields plus `scene_key` / `transition`, and that `darkness_source` matches what
      `is_dark` returns for the same inputs
- [ ] `tests/test_init.py` — updating `entry.options` on a set-up entry reloads the entry and the
      coordinator's `RuntimeConfig` reflects the new value; unloading removes the update listener
      without error
- [ ] `tests/test_lux_focus.py` — update for the tuple return if it calls `is_dark` directly

---

## Commit plan

| # | Scope | Files | Message |
|---|-------|-------|---------|
| 1 | logic | `logic.py`, `tests/test_logic.py` | `feat(logic): expose darkness source and per-ingredient verdicts` |
| 2 | logic | `tests/test_parity.py`, `tests/test_lux_focus.py` | `test(parity): guard darkness source against is_dark branches` |
| 3 | coordinator | `coordinator.py`, `tests/test_coordinator.py` | `feat(coordinator): carry decision ingredients into diagnostics` |
| 4 | init | `__init__.py`, `tests/test_init.py` | `fix(init): reload entry when options change` |
| 5 | sensor | `sensor.py`, `binary_sensor.py`, `tests/test_sensor.py`, `tests/test_binary_sensor.py` | `feat(sensor): add threshold attributes to existing diagnostics` |
| 6 | sensor | `sensor.py`, `binary_sensor.py`, `tests/test_sensor.py`, `tests/test_binary_sensor.py` | `feat(sensor): add ingredient and threshold diagnostic entities` |
| 7 | docs | `CHANGELOG.md` | `docs(changelog): record diagnostic ingredients and options reload` |
| 8 | wrap-up | rename to `tasks/done/11-feature-expand-diagnostic-entities-with-decision-ingredients-done.md`, set `Status: done` and `Completed: <date>` | `chore: mark expand-diagnostic-entities plan as done` |

---

## Definition of done

- [ ] All work items above are checked off
- [ ] Rollout / state invalidation reflected — marked n/a; the options-reload behaviour change
      from work item 3 is noted for the release notes
- [ ] Tests in "Test updates" added/updated
- [ ] No decision behaviour changed: the existing `test_parity.py` traces and every
      `pick_scene` / `derive_phase` / `selection_reason` case pass unmodified in substance
- [ ] Total diagnostic entity count is 19 — 9 existing (values unchanged, some with new
      attributes) + 6 ingredient entities + 4 threshold entities
- [ ] Every ENUM sensor's options list is derived from its `logic.py` enum, not hand-typed
- [ ] Saving options in the UI reloads the entry and the threshold sensors show the new values
      without an HA restart
- [ ] `CHANGELOG.md` `[Unreleased]` carries both an `### Added` and a `### Fixed` entry, so the
      release built from this section has real notes rather than the `Release <tag>` fallback
