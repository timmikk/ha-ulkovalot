"""Pytest configuration."""

from datetime import datetime, timezone
from typing import Any

import pytest

from custom_components.ulkovalot.coordinator import DiagnosticsSnapshot
from custom_components.ulkovalot.logic import (
    DarknessSource,
    LuxDarkness,
    Phase,
    SunDarkness,
)


def make_snapshot(**overrides: Any) -> DiagnosticsSnapshot:
    """Build a ``DiagnosticsSnapshot`` with a bright-midday default.

    Shared by the sensor and binary-sensor suites so a new snapshot field
    only has to be defaulted in one place.
    """
    base = dict(
        motion=False,
        dark=False,
        illuminance=5000.0,
        sun_elevation=30.0,
        phase=Phase.DAY,
        reason="day",
        override_active=False,
        override_scene=None,
        override_until=None,
        disabled=False,
        applied_scene="scene.day",
        updated_at=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc),
        sun_darkness=SunDarkness.BRIGHT,
        lux_darkness=LuxDarkness.BRIGHT,
        darkness_source=DarknessSource.SUN_ABOVE_CEILING,
        night_window=False,
        rising=False,
        scene_key="scene_day",
        transition=10.0,
    )
    base.update(overrides)
    return DiagnosticsSnapshot(**base)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations in every test."""
    yield


@pytest.fixture(autouse=True)
async def utc_time_zone(hass):
    """Pin HA's local timezone to UTC so wall-clock phase decisions match
    the frozen ``freezegun`` times the tests configure — the default test
    zone (``US/Pacific``) would silently shift phase boundaries."""
    await hass.config.async_set_time_zone("UTC")
