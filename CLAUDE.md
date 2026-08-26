# ha-ulkovalot

Home Assistant custom component (HACS integration) that coordinates outdoor
lighting: scene decisions driven by lux/time, with manual override handling.
Domain: `ulkovalot`.

## Project structure

- `custom_components/ulkovalot/` — the integration itself
  - `__init__.py` — entry setup/unload lifecycle
  - `config_flow.py` — UI config flow
  - `const.py` — domain constants
  - `coordinator.py` — `DataUpdateCoordinator`, override state machine, scene-decision cycle
  - `logic.py` — pure decision logic (lux/time → scene), kept separate from HA glue for testability
  - `entity.py` — `UlkovalotEntity` base: device info + coordinator-listener wiring
  - `sensor.py` / `binary_sensor.py` — diagnostic entity platforms reading `coordinator.diagnostics`
  - `manifest.json`, `services.yaml` — HA integration metadata / service schema
- `tests/` — pytest suite, one `test_*.py` per source module plus `test_parity.py` (cross-checks logic vs. the `Ulkovalot 3` blueprint), `test_lux_focus.py`, and `test_override.py`; `conftest.py` holds shared fixtures
- `tasks/` — plan files for `/plan` and `/execute-task` (generic fallback flow — see below); completed plans move to `tasks/done/`
- `.forgejo/workflows/ci.yml` — CI: `hassfest` (HA manifest validation against a matching core checkout), `hacs` (HACS integration validation against the GitHub mirror), `pytest` (with coverage), `sonar` (SonarQube analysis, push-to-main only)
- `.forgejo/workflows/release.yml` — release automation
- `hacs.json` — HACS metadata (min HA version, etc.)
- `sonar-project.properties` — project key `ha-ulkovalot`; sources `custom_components/ulkovalot`, tests `tests/`

No `prompts/plan.md` or `prompts/execute-task.md` override exists here, so `/plan` and `/execute-task` use the generic fallback flow from `~/.claude/commands/`.

## Environment

- Python 3.12, local virtualenv at `.venv/` (create with `~/dev/dev-tools/scripts/bootstrap-ha-tests.sh` if missing — installs deps and writes the pytest asyncio config)
- Test deps pinned in `requirements_test.txt`: `pytest`, `pytest-cov`, `pytest-homeassistant-custom-component`, `freezegun`
- `pyproject.toml` sets `asyncio_mode = "auto"` — required for the `hass` fixture from `pytest-homeassistant-custom-component` to work at all

## Test commands

```bash
.venv/bin/python -m pytest -q
```

With coverage (matches CI):

```bash
.venv/bin/python -m pytest -q --cov=custom_components/ulkovalot --cov-branch \
  --cov-report=xml --cov-report=term-missing
```

This is the whole suite (133 tests, ~5s) — for this project's size, just run it all rather than filtering by package.

## CI / quality gates

- CI runs `hassfest`, `hacs`, `pytest`, and (push to `main` only) `sonar`. Check SonarQube quality gate after pushing to `main` (project key `ha-ulkovalot`) per the global SonarQube guidance.
- `manifest.json` `version` is bumped by release tooling, not during plan execution.
