# Changelog

All notable changes to this project will be documented in this file. Format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
