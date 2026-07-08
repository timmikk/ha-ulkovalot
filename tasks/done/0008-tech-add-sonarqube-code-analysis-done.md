# Task: add SonarQube code analysis to CI

**Status:** done
**Issue:** #8
**Type:** tech
**Complexity:** small
**Version bump:** patch
**Created:** 2026-07-08
**Completed:** 2026-07-08

## Context

The self-hosted SonarQube at `http://192.168.16.16:9000` is the shared
code-quality gate for every repo in the fleet (`vihko/{backend,client}`,
`aamusankari`, `infra`). `ha-ulkovalot` is the only actively-developed
Python project not yet reporting to it, so new-code quality issues (bugs,
smells, security hotspots, duplication, coverage regressions) currently
land silently. Wire the same scanner-based flow used by the sibling repos:
run pytest with coverage, publish results to Sonar on push-to-main, and
gate future releases on the quality gate.

The overview at
[0000-overview-integration-stages.md](0000-overview-integration-stages.md)
already commits to `pytest --cov=custom_components/ulkovalot --cov-branch
--cov-report=xml` with a 90 % floor (100 % for `logic.py`). This task
wires the XML report into Sonar and adds nothing to that testing contract.

---

## Work items

### 1. Sonar project descriptor
**Files:** `sonar-project.properties` (new)

Root-level scanner config, mirroring `vihko/backend/sonar-project.properties`
but scoped to the single Python package. Coverage input is the
`coverage.xml` produced by `pytest-cov`.

- [ ] Create `sonar-project.properties` with:
  - `sonar.projectKey=ha-ulkovalot`
  - `sonar.projectName=ha-ulkovalot`
  - `sonar.sources=custom_components/ulkovalot`
  - `sonar.tests=tests`
  - `sonar.python.version=3.12` (matches CI + HA)
  - `sonar.python.coverage.reportPaths=coverage.xml`
  - `sonar.exclusions=**/__pycache__/**,**/.venv/**,.dev/**`
  - `sonar.coverage.exclusions=tests/**,custom_components/ulkovalot/__init__.py` (module bootstrap only — real coverage is measured on `logic.py`, `coordinator.py`, `config_flow.py`)
  - `sonar.sourceEncoding=UTF-8`

### 2. Emit coverage XML from pytest
**Files:** `requirements_test.txt`, `pyproject.toml`

Sonar's Python plugin only reads `coverage.xml` in the Cobertura shape.
`pytest-cov` already emits it, but it's not a declared dependency and
the invocation in CI is `pytest -q` with no coverage flags.

- [ ] Add `pytest-cov>=5.0` to `requirements_test.txt`.
- [ ] In `pyproject.toml`, keep `[tool.pytest.ini_options]` addopts terse
  (`-ra`) — do NOT bake `--cov` flags in globally, since local runs
  shouldn't pay the instrumentation cost. Coverage flags stay in the CI
  invocation.

### 3. Wire coverage + Sonar into CI
**Files:** `.forgejo/workflows/ci.yml`

Two changes to the existing `pytest` job, plus a new `sonar` job that
runs only on `push` to `main` (matches the vihko pattern — PRs from
forks can't see the token, and Sonar's "new code" metric is anchored to
the main branch anyway).

- [ ] In the `pytest` job, replace `pytest -q` with:
  ```
  pytest -q --cov=custom_components/ulkovalot --cov-branch \
    --cov-report=xml --cov-report=term-missing
  ```
- [ ] `actions/upload-artifact@v4` step to upload `coverage.xml` from the
  `pytest` job (name: `coverage-xml`).
- [ ] New `sonar` job, `needs: [pytest]`, `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`. Steps:
  1. `actions/checkout@v4` with `fetch-depth: 0` (Sonar needs full history for blame/new-code detection).
  2. `actions/download-artifact@v4` for `coverage-xml` into repo root.
  3. Install sonar-scanner CLI (same curl-and-unzip block as
     `vihko/.forgejo/workflows/ci-backend.yml`, kept inline — no shared
     action available).
  4. Run `sonar-scanner`, passing
     `SONAR_HOST_URL` and `SONAR_TOKEN` via the Forgejo repo secrets.
- [ ] Do NOT add a coverage floor in CI — Sonar's quality gate owns that
  threshold. Local runs still print `term-missing` for visibility.

### 4. Register the Forgejo secret
**Files:** none (external — noted in Definition of done)

`SONAR_TOKEN` is a per-project token created in Sonar and pushed to the
Forgejo repo's secret store. This isn't a code change but the workflow
above fails without it.

- [ ] Confirm operator step is documented in Definition of done (below).

### 5. Create the Sonar project + quality gate
**Files:** none (external)

Sonar project `ha-ulkovalot` doesn't exist yet (verified via
`/api/projects/search?q=ulkovalot` → `total: 0`). Provisioning is
required before the first scanner run has anywhere to report to.

- [ ] Operator step in Definition of done: create project via
  `POST /api/projects/create` with `project=ha-ulkovalot` and
  `name=ha-ulkovalot`, then attach the default "Sonar way" quality gate.
  New-code period defaults to "previous version" — leave as-is; the
  overview's 90 % / 100 % floors already act as the hard gate in CI.

### 6. README pointer
**Files:** `README.md`

One line under "Development" so future readers know where the quality
signal lives. Match the tone of the existing SonarQube blurb in the
user's global `CLAUDE.md`.

- [ ] Add a `Code quality` sub-section:
  `SonarQube analysis runs on push to main; results at
  http://192.168.16.16:9000/dashboard?id=ha-ulkovalot. Quality gate is
  enforced by CI.`

---

## Rollout / state invalidation

n/a — fully transparent to in-flight clients. This changes CI only; no
runtime code paths in the HA integration are touched, no config schema
changes, no cached state on any client.

---

## Test updates

No new pytest tests. The existing suite is what Sonar measures. Verify
the pipeline end-to-end by observing the first push to main after the
workflow lands:

- [ ] `pytest` job produces `coverage.xml` at repo root and uploads it as
  the `coverage-xml` artifact.
- [ ] `sonar` job downloads the artifact, runs `sonar-scanner`, and the
  Sonar dashboard shows a first analysis with a coverage number > 0.
- [ ] Quality gate status is queryable via
  `curl -sS -u "$SONAR_TOKEN:" "$SONAR_HOST_URL/api/qualitygates/project_status?projectKey=ha-ulkovalot"`
  and returns `OK` (or `ERROR` with a real reason — not "project not
  found").

---

## Commit plan

| # | Scope | Files | Message |
|---|-------|-------|---------|
| 1 | sonar config | `sonar-project.properties` | `chore(sonar): add project descriptor for ha-ulkovalot` |
| 2 | test deps | `requirements_test.txt` | `chore(tests): add pytest-cov for coverage.xml output` |
| 3 | ci | `.forgejo/workflows/ci.yml` | `ci: emit coverage.xml and add sonar job on push-to-main` |
| 4 | docs | `README.md` | `docs(readme): note sonarqube quality gate` |
| 5 | wrap-up | rename to `tasks/done/0008-tech-add-sonarqube-code-analysis-done.md`, set `Status: done` and `Completed: <date>` | `chore: mark sonarqube ci plan as done` |

---

## Definition of done

- [ ] All work items above are checked off
- [ ] Rollout / state invalidation reflected (n/a — recorded above)
- [ ] Operator: Sonar project `ha-ulkovalot` created and attached to the
  default quality gate (work item 5)
- [ ] Operator: `SONAR_TOKEN` secret added to the Forgejo repo settings
  for `timo/ha-ulkovalot` (work item 4)
- [ ] First push-to-main after merge triggers the `sonar` job green and
  the dashboard shows a non-empty coverage measurement
- [ ] `curl` against `/api/qualitygates/project_status?projectKey=ha-ulkovalot`
  returns a real status (not "component not found")

## Actual commits

- d7098ba chore(sonar): add project descriptor for ha-ulkovalot
- 21c22ab chore(tests): add pytest-cov for coverage.xml output
- e188078 ci: emit coverage.xml and add sonar job on push-to-main
- c86b8f9 docs(readme): note sonarqube quality gate
