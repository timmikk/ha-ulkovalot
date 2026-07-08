# Ulkovalot integration — overview & shared context

Migrate the `blueprints/automation/testi/ulkovalot.yaml` blueprint (and its
overlapping raw automations in the *Ulkovalot* group of
`home-assistant-config/automations.yaml`) into the `ulkovalot` custom
component. Final stage must reach behavioural parity with the blueprint
plus two new features (manual timed override + ambient lux sensing).

This file is the **shared context** for every stage plan. Individual
stages live in their own `tasks/000N-*.md` files and reference the
sections here (feature surface, dark/bright decision, phase derivation,
testing strategy, non-goals) rather than repeating them.

## Stage index

Execute in order; each stage is a self-contained, releasable increment
with its own commits, tests, and release tag. Version bumps: `0.1.0`
at Stage 2 (first useful behaviour), `1.0.0` at Stage 6 (parity +
cutover done).

| Stage | Issue | Plan file | Summary |
|---|---|---|---|
| 1 | [#1](https://git.clo.dy.fi/timo/ha-ulkovalot/issues/1) | [0001-feature-ulkovalot-config-flow.md](0001-feature-ulkovalot-config-flow.md) | Collect every input in the UI. No behaviour yet. |
| 2 | [#2](https://git.clo.dy.fi/timo/ha-ulkovalot/issues/2) | [0002-tech-ulkovalot-state-engine.md](0002-tech-ulkovalot-state-engine.md) | `logic.py` pure functions, 100 % unit-tested. |
| 2b | [#3](https://git.clo.dy.fi/timo/ha-ulkovalot/issues/3) | [0003-tech-ulkovalot-override-plumbing.md](0003-tech-ulkovalot-override-plumbing.md) | Coordinator override state machine + services, isolated tests. |
| 3 | [#4](https://git.clo.dy.fi/timo/ha-ulkovalot/issues/4) | [0004-feature-ulkovalot-coordinator-runtime.md](0004-feature-ulkovalot-coordinator-runtime.md) | Full HA subscriptions, `scene.turn_on`, `restart` semantics. |
| 4 | [#5](https://git.clo.dy.fi/timo/ha-ulkovalot/issues/5) | [0005-tech-ulkovalot-parity-and-lux-tests.md](0005-tech-ulkovalot-parity-and-lux-tests.md) | Sensor-less blueprint replay + lux/override/lock focused tests. |
| 5 | [#6](https://git.clo.dy.fi/timo/ha-ulkovalot/issues/6) | [0006-chore-ulkovalot-live-cutover.md](0006-chore-ulkovalot-live-cutover.md) | Live install, disable + observe + delete blueprint & automations. |
| 6 | [#7](https://git.clo.dy.fi/timo/ha-ulkovalot/issues/7) | [0007-docs-ulkovalot-release.md](0007-docs-ulkovalot-release.md) | `v1.0.0` tag, README config table, services docs, HACS blurb. |

## Reference

- Blueprint: `~/dev/home-assistant-config/blueprints/automation/testi/ulkovalot.yaml`
- Raw automations to retire: *sytytä illalla* / *sammuta yöksi* /
  *sytytä aamulla* / *sammuta päiväksi* / *Liiketunnistimet*
- Inventory row: `AUTOMATION-INVENTORY.md` → Ulkovalot section
- Component skeleton: `custom_components/ulkovalot/` (domain `ulkovalot`,
  config_flow=true, single-instance)
- Pipeline: infra `docs/ha-custom-components.md` (Forgejo → GitHub mirror
  → HACS)

## Feature surface (blueprint parity + new features)

Reproduces the blueprint's day/morning/evening/night/motion scene
coordination, and adds two new capabilities: a manual timed override
(button- or service-driven) and an ambient illuminance sensor that
takes over the dark/bright decision when present.

Inputs
- `night_scene_start_time` (time, default 23:00) — evening → night flip
- `night_scene_end_time` (time, default 07:00) — night → morning flip
- `illuminance_sensors` (list of `sensor` entities reporting lux, 0..N)
  — primary dark/bright signal when at least one is present + valid.
  Explicit list (not auto-derived from motion devices) so lux sources
  can be independent of motion sources.
- `lux_on_below` (lx, default 30) — dark trigger, drives lights on
- `lux_off_above` (lx, default 100) — bright trigger, drives lights off
  (hysteresis gap against `lux_on_below` prevents flicker)
- `sun_elev_dark_floor` (° sun elevation, default −3) — safety lock: if
  elev ≤ this, treat as dark regardless of lux
- `sun_elev_bright_ceiling` (° sun elevation, default +6) — safety lock:
  if elev ≥ this, treat as bright regardless of lux. Also used as the
  single fallback threshold when the lux sensor is missing/unavailable
  (matches blueprint semantics for sensor-less setups)
- `motion_sensors` (list of binary_sensor motion entities, 0..N —
  replaces the blueprint's fixed pair)
- `disable_flag` (optional entity selector, empty = unused — replaces
  the blueprint's free-text `automation_disable_flag`; bypass when `on`)
- `scene_day`, `scene_morning`, `scene_evening`, `scene_night`,
  `scene_motion`
- `no_motion_wait` (s, default 120)
- `transition_time` (s, default 10) — normal scene changes
- `transition_time_motion` (s, default 1) — motion-triggered
- `override_scene` (scene entity) — default target for manual override
- `override_duration` (s, default 7200 = 2 h) — default override length
- `override_trigger` (optional entity: `input_button`, `event`, or state
  change target) — a button that raises an override without a service call

Dark/bright decision
- Aggregate lux across `illuminance_sensors`:
  - Filter out `unknown` / `unavailable` / non-numeric readings.
  - `lux = median(valid_readings)` (odd count → middle value; even
    count → mean of the two middles). Median is robust to a single
    covered / dirty / mis-placed sensor.
  - If **no** valid readings remain (empty list, or all
    unavailable), lux is `None` — falls back to sun-only.
- If lux is available (at least one valid reading):
  - `elev ≤ sun_elev_dark_floor` → **dark** (locked, median ignored)
  - `elev ≥ sun_elev_bright_ceiling` → **bright** (locked, median
    ignored)
  - Otherwise: hysteresis on the median. Was-bright → dark when
    `median ≤ lux_on_below`. Was-dark → bright when
    `median ≥ lux_off_above`. Persist last state in memory so
    intermediate readings don't flip.
- If lux is `None` (no valid readings): single-threshold fallback using
  `sun_elev_bright_ceiling` — bright when `elev ≥ ceiling`, dark
  otherwise. Matches the blueprint's sun-only shape.

Phase derivation (from time-of-day + `sun.sun` `rising` + dark/bright)
- `bright` → **day**
- `dark` **and** (`now ≥ night_scene_start_time` **or**
  `now < night_scene_end_time`) → **night** (dim night scene window)
- `dark` **and** `rising` (sun.sun rising) → **morning**
- `dark` **and** `not rising` → **evening**

Note the semantic shift vs blueprint: **time no longer bounds evening
or morning**. Only the night dim scene has a time window. Evening
starts whenever it becomes dark before 23:00; morning starts at 07:00
if still dark and runs until lux/sun says bright. Sun elevation only
acts as a safety backstop against lux misreads, not as a phase driver.

Motion latching
- Per sensor: `is_motion_N or (now − last_changed_N) ≤ no_motion_wait`
- Combined: any sensor active or within wait window

Choose priority (first match wins)
1. `override_active` → `override_scene` (transition) — overrides
   everything, including day/night phases
2. `is_day_time` → `scene_day` (transition)
3. `is_morning` → `scene_morning` (transition)
4. `not is_day_time and is_motion` → `scene_motion` (transition_motion)
5. `is_evening` → `scene_evening` (transition)
6. `is_night` → `scene_night` (transition)
7. default → `scene_motion` (transition)

Manual override
- Two entry points that mean the same thing:
  - Service `ulkovalot.override` with optional `scene` (entity_id) and
    `duration` (seconds). Missing fields fall back to config defaults.
  - Firing the configured `override_trigger` entity (button press /
    event) uses config defaults.
- Also expose `ulkovalot.cancel_override` service for programmatic
  cancellation (dashboards, voice, etc.).
- Re-triggering while active **restarts the timer** at the new
  duration (or the default). Scene may change if a different one was
  passed — treat it as a fresh override.
- On timer expiry, clear override and re-run the normal `choose`
  against current state (so the transition back is a normal scene
  change, not a hard cut).

Trigger set (any of): motion on/off (with `for: no_motion_wait`), lux
state change on any configured `illuminance_sensors` entry, sun elevation crossings at
`sun_elev_dark_floor` and `sun_elev_bright_ceiling`, time triggers at
`night_scene_start_time` and `night_scene_end_time`, `homeassistant`
start, `automation_reloaded` / `scene_reloaded`, disable flag change,
override trigger/service. Mode `restart`, `max_exceeded: silent`.

## Non-goals

- No per-scene transition timing, no per-sensor motion wait, no dynamic
  wait — the two global values (`transition_time` /
  `transition_time_motion` / `no_motion_wait`) stay flat.
- No color-temperature or per-light brightness control — scenes remain
  the abstraction for what the lights actually do. Ambient lux only
  drives *which* scene, not light parameters directly.
- No dashboard / Lovelace helpers in this integration.
- No multi-zone / multi-instance coordination in the first release
  (single config entry per HA instance).

## Testing strategy

Tests are a first-class deliverable of each stage — no stage exits
without the tests it introduces going green. CI
(`.forgejo/workflows/ci.yml`) already runs `pytest` + `hassfest` +
`hacs/action` on every push; a red suite blocks the stage's release
tag.

**Layers**

1. **Unit** (`tests/test_logic.py`, no HA runtime) — pure functions from
   `logic.py`. Fast, deterministic, table-driven. This is where phase
   boundaries, lux hysteresis, motion latching, override precedence, and
   scene-picking priority are exhaustively covered. Target: **100 %
   line + branch coverage of `logic.py`**.
2. **Override plumbing** (`tests/test_override.py`) — `coordinator`
   override state machine with services mocked and `async_call_later`
   replaced by `pytest-homeassistant-custom-component`'s
   `async_fire_time_changed`. Covers timer restart, cancel path, scene
   swap on re-press, expiry re-evaluation.
3. **Runtime integration** (`tests/test_coordinator.py`) — full config
   entry loaded via `pytest-homeassistant-custom-component`
   `MockConfigEntry` + `hass` fixture. Uses fake `sun.sun`, mocked
   `scene.turn_on`, controlled clock via `async_fire_time_changed`, and
   `hass.states.async_set` for motion / lux / disable-flag entities.
   Each scenario: drive events, assert `scene.turn_on` calls (target
   entity + `transition` value + call count). Target: **≥ 90 %
   coverage of `coordinator.py`**.
4. **Config flow** (`tests/test_config_flow.py`) — user step happy
   path, single-instance abort, options-flow round trip, reconfigure
   flow, validation errors (bad lux thresholds, hysteresis inverted,
   etc.). Target: **≥ 90 % coverage of `config_flow.py`**.
5. **Parity + fallback** (`tests/test_parity.py`, Stage 4) — sensor-less
   trace replay against a re-implementation of the blueprint's
   `variables:` block. Covers the sun-only fallback path, override
   precedence over each phase, sun-elev floor/ceiling locks, and
   sensor-lost recovery. Documented divergences from strict blueprint
   parity assert the new behaviour instead.

**Shared fixtures** (`tests/conftest.py`)

- `mock_sun(hass, elevation, rising)` — sets `sun.sun` state +
  attributes.
- `mock_lux(hass, entity_id, value)` — sets an illuminance sensor
  entity; supports `None` / `unavailable` for the fallback path.
  Multi-sensor scenarios call this once per entity to build the
  aggregate.
- `mock_motion(hass, entity_id, state, last_changed)` — motion state
  with a precise `last_changed`.
- `advance(hass, seconds)` — wrap `async_fire_time_changed` +
  `await hass.async_block_till_done()` in one call.
- `installed(hass, overrides=None)` — set up a full config entry with
  sensible defaults, returning the coordinator; individual tests
  override specific fields.

**Clock control**

- Use `freezegun` (bring in as a test-only dep — add to
  `requirements_test.txt`) for wall-clock time inside `logic.py`
  unit tests where `datetime.now()` is called indirectly.
- Runtime tests use `async_fire_time_changed(hass, target_dt)` —
  HA's own advance mechanism — for scheduled callbacks and timeouts.

**Coverage measurement**

- Run `pytest --cov=custom_components/ulkovalot --cov-branch
  --cov-report=term-missing --cov-report=xml`.
- Add coverage summary to CI output; fail the CI job if total coverage
  drops below **90 %** or if `logic.py` drops below **100 %**.
- Wire `codecov` or upload the XML as a CI artefact for inspection.

**Regression guardrail**

- Every bug fix during Stages 5–6 (cutover / release) that came from
  observing real HA behaviour lands with a new test in the appropriate
  layer that would have caught it. No fix-forward without a test.

## Resolved decisions

- **Motion sensors**: list selector, 0..N. Motion latching iterates the
  list; empty list means "no motion source" (`is_motion` always false).
- **Disable flag**: optional entity selector; empty = unused. Wire
  format is `str | None`, not the blueprint's empty-string sentinel.

Parity harness (Stage 4) must account for these representation
differences: reference implementation reads a list + optional entity and
still matches the blueprint's per-event scene choice for equivalent
configs (2 sensors, non-empty flag).
