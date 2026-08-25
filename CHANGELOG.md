# Changelog

All notable changes to this project will be documented in this file. Format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.0] - 2026-08-25

Pre-cutover release candidate for the live migration (Stage 5) off the
`testi/ulkovalot.yaml` blueprint and the raw *Ulkovalot* automations in
`home-assistant-config`.

### Added

- Config flow covering the full input surface: night scene window,
  illuminance sensors, lux thresholds, sun elevation floor/ceiling,
  motion sensors, disable flag, scenes, waits/transitions, and
  override defaults. Options flow + reconfigure round-trip.
- Pure state engine (`logic.py`): lux aggregation with hysteresis, sun
  elevation floor/ceiling safety locks, phase derivation
  (day/morning/evening/night), motion latching, and scene priority
  selection. 100% line + branch covered.
- Manual timed override: `ulkovalot.override` / `ulkovalot.cancel_override`
  services plus an optional trigger entity, with restart-on-re-trigger
  and expiry re-evaluation semantics.
- Full runtime coordinator: HA state subscriptions, `scene.turn_on`
  dispatch with per-path transition times, and `restart` mode
  matching the blueprint's re-trigger behaviour.
- Blueprint parity trace: a synthetic 24h replay against an independent
  Python port of the blueprint's `variables:` block, plus focused tests
  for lux storms, dawn/dusk hysteresis, sensor-lost fallback, and the
  floor/ceiling safety locks.

### Changed

- CI: run `hassfest` as a Python module against a shallow
  `home-assistant/core` clone instead of the docker-based
  `home-assistant/actions/hassfest`. The docker action can't mount the
  workspace under Forgejo Actions (docker CLI in the job container
  reaches the host daemon, so `$GITHUB_WORKSPACE` isn't a valid host
  path). Job moves off `image-builder` back to `ubuntu-latest`. Infra
  task #222.
- CI: fix `hacs:` job 401s by wiring the mirror PAT and the public
  GitHub repo name as `hacs/action` **inputs**
  (`with: github_token:` / `with: repository:`) instead of a
  step-level `GITHUB_TOKEN` env var the action never reads. Infra
  task #223.

## [0.0.1] - 2026-07-05

- Initial scaffold via infra task #200 (`scripts/setup-ha-component-repo.sh`).
  Empty `async_setup` shell; not yet functional.
