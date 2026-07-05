"""Config flow for ulkovalot."""

from __future__ import annotations

from homeassistant import config_entries

from .const import DOMAIN


class UlkovalotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Minimal config flow — one entry, no options yet."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(title="Outdoor lights coordinator", data={})
