"""Ulkovalot coordinator — Stage 2b scope: override state machine only.

Sun / motion / lux subscriptions and the actual ``scene.turn_on`` dispatch
land in Stage 3. Tests exercise this module by stubbing the ``apply_scene``
hook so override behaviour can be verified without a full runtime.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_OVERRIDE_DURATION,
    CONF_OVERRIDE_SCENE,
    CONF_OVERRIDE_TRIGGER,
    DEFAULT_OVERRIDE_DURATION,
)


ApplyScene = Callable[[], None]


def _noop_apply() -> None:
    """Default re-evaluation hook — Stage 3 replaces this."""


class UlkovalotCoordinator:
    """Holds override state and the timer that expires it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.override_scene: str | None = None
        self.override_until: datetime | None = None
        self._cancel_timer: Callable[[], None] | None = None
        self._cancel_trigger: Callable[[], None] | None = None
        self.apply_scene: ApplyScene = _noop_apply

    @property
    def _default_scene(self) -> str | None:
        return self.entry.data.get(CONF_OVERRIDE_SCENE)

    @property
    def _default_duration(self) -> int:
        return self.entry.options.get(
            CONF_OVERRIDE_DURATION, DEFAULT_OVERRIDE_DURATION
        )

    def start_override(
        self,
        scene: str | None = None,
        duration: int | None = None,
    ) -> None:
        """Start or restart the override — cancels any pending expiry timer."""
        self._cancel_pending_timer()
        self.override_scene = scene if scene is not None else self._default_scene
        secs = duration if duration is not None else self._default_duration
        self.override_until = dt_util.utcnow() + timedelta(seconds=secs)
        self._cancel_timer = async_call_later(self.hass, secs, self._on_expiry)
        self.apply_scene()

    def cancel_override(self) -> None:
        """Explicit cancel — clears state and re-evaluates immediately."""
        self._cancel_pending_timer()
        self._clear_override_state()
        self.apply_scene()

    def wire_trigger(self) -> None:
        """Subscribe to the optional trigger entity, if configured."""
        trigger = self.entry.data.get(CONF_OVERRIDE_TRIGGER)
        if not trigger:
            return
        self._cancel_trigger = async_track_state_change_event(
            self.hass, [trigger], self._on_trigger_event
        )

    def unload(self) -> None:
        """Cancel pending timer + trigger subscription."""
        self._cancel_pending_timer()
        if self._cancel_trigger is not None:
            self._cancel_trigger()
            self._cancel_trigger = None

    @callback
    def _on_expiry(self, _now: datetime) -> None:
        self._cancel_timer = None
        self._clear_override_state()
        self.apply_scene()

    @callback
    def _on_trigger_event(self, _event: Event) -> None:
        self.start_override()

    def _cancel_pending_timer(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    def _clear_override_state(self) -> None:
        self.override_scene = None
        self.override_until = None
