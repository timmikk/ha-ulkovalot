"""Pytest configuration."""

import pytest


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
