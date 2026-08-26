# Task: Add debug/diagnostic entities exposing coordinator state

**Status:** pending
**Issue:** #10
**Type:** feature
**Complexity:** medium
**Version bump:** minor
**Created:** 2026-08-26
**Completed:** —

## Context

The coordinator (`coordinator.py`) computes motion, aggregated illuminance, sun elevation, dark/bright state, time-of-day phase, override state, and the resolved scene on every evaluation cycle — but none of it is observable outside `_LOGGER.debug`. When the automatic scene choice looks wrong, there is no way to see *why* without turning on debug logging and reading raw event dumps. This adds a set of read-only diagnostic entities (`sensor` + `binary_sensor`) that expose the coordinator's evaluation snapshot, refreshed every time `_apply_scene_impl` runs — including cycles that don't change scene (disabled, no entity resolved), so those states are visible too.

Currently `const.PLATFORMS` is an empty list and no entity platform exists in this integration at all — this introduces the first ones.

## Entities

Confirmed with the user; the reason sensor's states mirror `pick_scene`'s branch order exactly, so it's directly traceable against `logic.py`.

**`binary_sensor`**
- `motion` — device_class `motion`, true when any configured motion sensor is active or within the no-motion wait window
- `dark` — true when `is_dark()` says dark (drives phase != DAY)
- `override_active` — true while an override is in effect; attributes `scene`, `until` (ISO timestamp)
- `disabled` — true when the configured disable-flag entity was `on` for this cycle

**`sensor`** (all `entity_category: diagnostic`)
- `illuminance` — device_class `illuminance`, unit `lx`, state_class `measurement`; aggregated median lux, or `None` if no valid readings
- `sun_elevation` — unit `°`, state_class `measurement`; last-read sun elevation
- `phase` — device_class `enum`, options `day|morning|evening|night`
- `reason` — device_class `enum`, options `disabled|override|day|morning|motion|evening|night`; mirrors the branch that `pick_scene`/`selection_reason` actually took
- `current_scene` — the scene entity id last dispatched via `scene.turn_on`, or `none` if nothing was resolved/dispatched this cycle

All entities group under one device (`DeviceInfo` keyed on `entry.entry_id`, name from `entry.title`) since this is a single-purpose coordinator integration.

---

## Work items

### 1. Pure `selection_reason` helper
**Files:** `custom_components/ulkovalot/logic.py`

Add a pure function next to `pick_scene` so the reason sensor's value is unit-testable in isolation and guaranteed to stay in lockstep with the actual scene-choice branches:

```python
def selection_reason(phase: Phase, motion: bool, override: bool, disabled: bool) -> str:
    if disabled:
        return "disabled"
    if override:
        return "override"
    if phase == Phase.DAY:
        return "day"
    if phase == Phase.MORNING:
        return "morning"
    if motion:
        return "motion"
    if phase == Phase.EVENING:
        return "evening"
    if phase == Phase.NIGHT:
        return "night"
    return "motion"
```

- [ ] Add `selection_reason` mirroring `pick_scene`'s branch order (with the extra `disabled` pre-check)
- [ ] Export it from the module (already covered by `from .logic import *`-style explicit imports elsewhere — just add to `coordinator.py`'s import list)

### 2. Diagnostics snapshot + listener mechanism on the coordinator
**Files:** `custom_components/ulkovalot/coordinator.py`

- [ ] Add a frozen `DiagnosticsSnapshot` dataclass: `motion: bool`, `dark: bool`, `illuminance: float | None`, `sun_elevation: float | None`, `phase: Phase`, `reason: str`, `override_active: bool`, `override_scene: str | None`, `override_until: datetime | None`, `disabled: bool`, `applied_scene: str | None`, `updated_at: datetime`
- [ ] Add `self.diagnostics: DiagnosticsSnapshot` initialized to a sensible zero-state in `__init__` (motion/dark/override_active/disabled `False`, others `None`/empty, `phase=Phase.DAY`, `reason="day"`, `updated_at=dt_util.utcnow()`)
- [ ] Add `self._listeners: list[Callable[[], None]] = []` in `__init__`
- [ ] Add `async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]` — appends and returns a remove closure (mirrors the `_unsubs` pattern already used elsewhere in this file)
- [ ] Add `_notify_listeners(self) -> None` — calls each listener; iterate over a copy since a listener can unsubscribe mid-callback
- [ ] Restructure `_apply_scene_impl` so the disable-flag check no longer early-returns before computing everything else: compute `disabled` as a bool up front, then always compute elev/lux/dark/phase/motion/override/reason, then only attempt `_resolve_scene_entity` + `scene.turn_on` when *not* disabled and an entity/service are available. Build the `DiagnosticsSnapshot` from those values (unconditionally) and call `_notify_listeners()` at the end of every cycle — including the disabled/no-entity/no-service paths, since those are exactly the states someone debugging the integration needs to see
- [ ] `unload()` should clear `self._listeners` too (entities remove themselves via their own unsub, but clearing defensively matches the existing teardown style)

### 3. Wire the new platforms into the entry lifecycle
**Files:** `custom_components/ulkovalot/const.py`, `custom_components/ulkovalot/__init__.py`

- [ ] Change `PLATFORMS: list[str] = []` to `PLATFORMS: list[str] = ["sensor", "binary_sensor"]`
- [ ] In `async_setup_entry`, after `store[entry.entry_id] = coordinator`, call `await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)`
- [ ] In `async_unload_entry`, unload platforms before popping/unloading the coordinator: `unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)`; only pop from `store` and call `coordinator.unload()` if `unload_ok`; return `unload_ok`

### 4. Shared entity base class
**Files:** `custom_components/ulkovalot/entity.py` (new)

- [ ] `UlkovalotEntity(Entity)` base: stores `coordinator`, `entry`; sets `_attr_has_entity_name = True`, `_attr_should_poll = False`; `device_info` property returning `DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, manufacturer="ulkovalot", model="Outdoor lights coordinator")`
- [ ] `async_added_to_hass` registers `coordinator.async_add_listener(self._handle_coordinator_update)` and stores the unsub for `async_will_remove_from_hass`
- [ ] `_handle_coordinator_update(self) -> None` default implementation calls `self.async_write_ha_state()` — subclasses read straight from `self.coordinator.diagnostics` in their `native_value`/`is_on` properties, so no extra state copying is needed

### 5. `sensor` platform
**Files:** `custom_components/ulkovalot/sensor.py` (new)

- [ ] `async_setup_entry` builds the five sensor entities (`illuminance`, `sun_elevation`, `phase`, `reason`, `current_scene`) from the coordinator stored in `hass.data[DOMAIN][entry.entry_id]`, `async_add_entities`
- [ ] Each entity: unique_id `f"{entry.entry_id}-<key>"`, `entity_category = EntityCategory.DIAGNOSTIC`, appropriate `device_class`/`native_unit_of_measurement`/`state_class`/`options` per the table above
- [ ] `current_scene` sensor returns `"none"` (not `None`) when `applied_scene` is unset, so the state is never `unknown` while the entity is otherwise healthy

### 6. `binary_sensor` platform
**Files:** `custom_components/ulkovalot/binary_sensor.py` (new)

- [ ] `async_setup_entry` builds the four binary sensor entities (`motion`, `dark`, `override_active`, `disabled`)
- [ ] `motion` sets `device_class = BinarySensorDeviceClass.MOTION`; others no device class
- [ ] `override_active` exposes `extra_state_attributes` with `scene` and `until` (ISO string or `None`) from `coordinator.diagnostics.override_scene` / `override_until`
- [ ] All four use `entity_category = EntityCategory.DIAGNOSTIC`

---

## Rollout / state invalidation

n/a — fully transparent to in-flight clients. New entities are created fresh on next integration reload/HA restart; there is no client-cached shape (cookies, localStorage, schema version) involved. Existing installs pick up the new platforms automatically on next `async_setup_entry` (HA restart or entry reload) since `PLATFORMS` changes are read at setup time.

---

## Test updates

- [ ] `tests/test_logic.py` — add cases for `selection_reason`: one per branch (`disabled` beats everything, `override` beats phase, `day`, `morning`, `motion` during evening/night, `evening` with no motion, `night` with no motion), asserting parity with `pick_scene`'s scene_key choice for the same inputs where applicable
- [ ] `tests/test_coordinator.py` — add cases asserting `coordinator.diagnostics` is populated correctly after `_apply_scene_impl` runs: normal cycle (motion/lux/elev/phase/reason match inputs), disabled-flag cycle (`diagnostics.disabled is True`, `applied_scene is None`, scene service *not* called), override cycle (`override_active is True`, `override_scene`/`override_until` populated)
- [ ] `tests/test_sensor.py` (new) — set up a `MockConfigEntry` + coordinator via the existing test helpers, drive a state change, assert each sensor's `native_value`/`state` reflects `coordinator.diagnostics`; assert unique_ids and `entity_category`
- [ ] `tests/test_binary_sensor.py` (new) — same pattern for the four binary sensors, including `override_active`'s `extra_state_attributes`
- [ ] `tests/test_init.py` — extend the smoke test (or add a case) asserting `async_setup_entry` forwards to `PLATFORMS` and `async_unload_entry` unloads them (e.g. entities are removed from the state machine after unload)

---

## Commit plan

| # | Scope | Files | Message |
|---|-------|-------|---------|
| 1 | logic | `custom_components/ulkovalot/logic.py`, `tests/test_logic.py` | `feat(logic): add selection_reason for debug diagnostics` |
| 2 | coordinator | `custom_components/ulkovalot/coordinator.py`, `tests/test_coordinator.py` | `feat(coordinator): track diagnostics snapshot and notify listeners` |
| 3 | entry | `custom_components/ulkovalot/const.py`, `custom_components/ulkovalot/__init__.py`, `tests/test_init.py` | `feat(init): forward sensor and binary_sensor platforms` |
| 4 | entity base | `custom_components/ulkovalot/entity.py` | `feat(entity): add shared diagnostic entity base class` |
| 5 | sensor | `custom_components/ulkovalot/sensor.py`, `tests/test_sensor.py` | `feat(sensor): add diagnostic sensors for coordinator state` |
| 6 | binary_sensor | `custom_components/ulkovalot/binary_sensor.py`, `tests/test_binary_sensor.py` | `feat(binary_sensor): add diagnostic binary sensors for coordinator state` |
| N | wrap-up | rename to `tasks/done/10-feature-add-debug-diagnostic-entities-done.md`, set `Status: done` and `Completed: <date>` | `chore: mark add-debug-diagnostic-entities plan as done` |

---

## Definition of done

- [ ] All work items above are checked off
- [ ] Rollout / state invalidation reflected (n/a, documented above)
- [ ] Tests in "Test updates" added/updated and passing
- [ ] Reloading the integration (or restarting HA) shows 5 new `sensor.*` and 4 new `binary_sensor.*` entities grouped under one device, and their states change on the next coordinator evaluation cycle
