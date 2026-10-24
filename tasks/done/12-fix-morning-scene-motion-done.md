# Task: Fix morning scene motion trigger

**Status:** done
**Issue:** #12
**Type:** fix
**Complexity:** small
**Version bump:** patch
**Created:** 2026-10-24
**Completed:** 2026-10-24

## Context

When outdoor lighting is in the `morning` phase (dark, sun rising, outside night window), detecting motion does not switch to the bright motion scene (`scene_motion`). In contrast, during the `night` and `evening` phases, motion correctly switches to `scene_motion`.

## Investigation Findings

The root cause was in `custom_components/ulkovalot/logic.py` in `pick_scene` and `selection_reason`:

```python
def pick_scene(
    phase: Phase,
    motion: bool,
    override: bool,
) -> tuple[str, str]:
    if override:
        return ("override_scene", "transition_time")
    if phase == Phase.DAY:
        return ("scene_day", "transition_time")
    if phase == Phase.MORNING:
        return ("scene_morning", "transition_time")
    if motion:
        return ("scene_motion", "transition_time_motion")
    if phase == Phase.EVENING:
        return ("scene_evening", "transition_time")
    if phase == Phase.NIGHT:
        return ("scene_night", "transition_time")
    return ("scene_motion", "transition_time")
```

1. **Branch Priority Flaw:**
   `if phase == Phase.MORNING:` was evaluated before `if motion:`. When `phase == Phase.MORNING`, the function matched immediately and returned `("scene_morning", "transition_time")`, ignoring `motion` completely.

2. **Contrast with Evening and Night:**
   `if phase == Phase.EVENING:` and `if phase == Phase.NIGHT:` were evaluated *after* `if motion:`. When `motion` was `True` in those phases, `if motion:` fired first, returning `("scene_motion", "transition_time_motion")`. When motion cleared, the evaluation fell through to `Phase.EVENING` or `Phase.NIGHT`.

3. **Origin:**
   This branch ordering was inherited from the legacy `Ulkovalot 3` blueprint (`testi/ulkovalot.yaml`) and was documented in `tasks/0000-overview-integration-stages.md` (lines 116-125), which mistakenly listed `is_morning` before `not is_day_time and is_motion`.

4. **Required Behavior:**
   During daylight (`Phase.DAY`), motion should not activate lights (`Phase.DAY` takes precedence over `motion`).
   However, during all dark phases (`Phase.MORNING`, `Phase.EVENING`, `Phase.NIGHT`), active motion must trigger `scene_motion` with `transition_time_motion`. When motion clears, the coordinator must return to the underlying ambient scene (`scene_morning`, `scene_evening`, or `scene_night`) with `transition_time`.

---

## Work items

### 1. Update pure decision logic
**Files:** `custom_components/ulkovalot/logic.py`

In `custom_components/ulkovalot/logic.py`:
- In `pick_scene`: Move `if motion:` above `if phase == Phase.MORNING:`.
  The evaluation order becomes:
  1. `override` → `("override_scene", "transition_time")`
  2. `phase == Phase.DAY` → `("scene_day", "transition_time")`
  3. `motion` → `("scene_motion", "transition_time_motion")`
  4. `phase == Phase.MORNING` → `("scene_morning", "transition_time")`
  5. `phase == Phase.EVENING` → `("scene_evening", "transition_time")`
  6. `phase == Phase.NIGHT` → `("scene_night", "transition_time")`
  7. default → `("scene_motion", "transition_time")`

- In `selection_reason`: Move `if motion:` above `if phase == Phase.MORNING:` to maintain lockstep parity with `pick_scene`:
  1. `disabled` → `"disabled"`
  2. `override` → `"override"`
  3. `phase == Phase.DAY` → `"day"`
  4. `motion` → `"motion"`
  5. `phase == Phase.MORNING` → `"morning"`
  6. `phase == Phase.EVENING` → `"evening"`
  7. `phase == Phase.NIGHT` → `"night"`
  8. default → `"motion"`

- [x] Reorder branches in `pick_scene`
- [x] Reorder branches in `selection_reason`

### 2. Update logic unit tests
**Files:** `tests/test_logic.py`

Update tests in `tests/test_logic.py` to assert the new behavior:
- In `test_pick_scene`:
  - Change `(Phase.MORNING, True, False)` expected result to `("scene_motion", "transition_time_motion")`.
  - Add explicit test case `(Phase.MORNING, False, False)` expecting `("scene_morning", "transition_time")`.
- In `test_selection_reason`:
  - Change `(Phase.MORNING, True, False, False)` expected result to `"motion"`.
  - Add explicit test case `(Phase.MORNING, False, False, False)` expecting `"morning"`.
- In `test_selection_reason_parity_with_pick_scene`:
  - Simplify condition to `elif motion and phase != Phase.DAY:` asserting `scene_key == "scene_motion" and reason == "motion"`.
  - Add `(Phase.MORNING, False, False)` to the parametrized inputs.

- [x] Update `test_pick_scene` cases
- [x] Update `test_selection_reason` cases
- [x] Update `test_selection_reason_parity_with_pick_scene`

### 3. Update parity harness and document divergence
**Files:** `tests/test_parity.py`

In `tests/test_parity.py`:
- In the module docstring under "Documented, deliberate divergences between the component and the raw blueprint", document divergence 5:
  The legacy blueprint placed `is_morning` before `is_motion`, preventing motion scenes from activating during morning darkness. The integration deliberately prioritizes motion over morning (matching evening and night).
- Update the reference `_blueprint_scene` function in `tests/test_parity.py` to evaluate `is_motion` before `is_morning` so the synthetic 24-hour trace replay (which includes an 08:00 morning motion pulse) verifies the intended motion behavior across all seasons.

- [x] Add divergence 5 documentation to docstring
- [x] Update `_blueprint_scene` branch ordering

### 4. Add coordinator integration tests for morning motion
**Files:** `tests/test_coordinator.py`

Add tests verifying coordinator runtime behavior in the morning phase:
- `test_motion_pulse_in_morning_fires_scene_motion`: In morning conditions (dark, rising, after `night_end`), a motion sensor going `on` fires `scene.motion` with `transition_time_motion`.
- `test_motion_timeout_in_morning_refires_scene_morning`: When motion turns `off` and the `no_motion_wait` timer elapses in morning conditions, coordinator refires `scene.morning` with `transition_time`.

- [x] Add `test_motion_pulse_in_morning_fires_scene_motion`
- [x] Add `test_motion_timeout_in_morning_refires_scene_morning`

### 5. Update overview documentation
**Files:** `tasks/0000-overview-integration-stages.md`

Update the "Choose priority (first match wins)" list in `tasks/0000-overview-integration-stages.md`:
1. `override_active` → `override_scene` (transition)
2. `is_day_time` → `scene_day` (transition)
3. `not is_day_time and is_motion` → `scene_motion` (transition_motion)
4. `is_morning` → `scene_morning` (transition)
5. `is_evening` → `scene_evening` (transition)
6. `is_night` → `scene_night` (transition)
7. default → `scene_motion` (transition)

- [x] Update choose priority list in `0000-overview-integration-stages.md`

---

## Security considerations

None — pure state decision logic and internal coordinator event handling. No external network endpoints, secrets, or credential handling.

---

## Out-of-repo changes

None. (The legacy blueprint `~/dev/home-assistant-config/blueprints/automation/testi/ulkovalot.yaml` is scheduled for retirement in live cutover Stage 5 / task #6).

---

## Validation

- [x] Run full test suite: `.venv/bin/python -m pytest -q`
- [x] Run test suite with coverage: `.venv/bin/python -m pytest -q --cov=custom_components/ulkovalot --cov-branch --cov-report=xml --cov-report=term-missing`
- [x] Verify 100% test pass rate with no regressions

---

## Documentation updates

- [x] Update `tasks/0000-overview-integration-stages.md` choose priority documentation
- [x] Update `CHANGELOG.md` under `[Unreleased]`

---

## Commit plan

| # | Scope | Files | Message |
|---|-------|-------|---------|
| 1 | logic | `custom_components/ulkovalot/logic.py`, `tests/test_logic.py`, `tests/test_parity.py` | `fix(logic): prioritize motion over morning scene when dark` |
| 2 | coordinator | `tests/test_coordinator.py` | `test(coordinator): add morning motion pulse and timeout tests` |
| 3 | docs | `tasks/0000-overview-integration-stages.md`, `CHANGELOG.md` | `docs: record morning scene motion priority fix` |
| 4 | wrap-up | `tasks/done/12-fix-morning-scene-motion-done.md` | `chore: mark task #12 as done` |

---

## Definition of done

- [x] All work items checked off
- [x] Security review passed
- [x] Full pytest suite passes with coverage
- [x] Documentation updated
