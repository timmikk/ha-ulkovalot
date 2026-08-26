"""Ulkovalot coordinator — Stage 3 scope: full runtime wiring.

Subscribes to motion / illuminance / disable-flag state changes, sun
elevation crossings, night-window time triggers, HA start, and
automation/scene reload events. On every event, re-evaluates via
``logic.py`` and dispatches ``scene.turn_on`` with the resolved
transition. The override state machine composes with the runtime hook.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
from typing import Callable

from homeassistant.components.automation import EVENT_AUTOMATION_RELOADED
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DISABLE_FLAG,
    CONF_ILLUMINANCE_SENSORS,
    CONF_LUX_OFF_ABOVE,
    CONF_LUX_ON_BELOW,
    CONF_MOTION_SENSORS,
    CONF_NIGHT_SCENE_END_TIME,
    CONF_NIGHT_SCENE_START_TIME,
    CONF_NO_MOTION_WAIT,
    CONF_OVERRIDE_DURATION,
    CONF_OVERRIDE_SCENE,
    CONF_OVERRIDE_TRIGGER,
    CONF_SCENE_DAY,
    CONF_SCENE_EVENING,
    CONF_SCENE_MORNING,
    CONF_SCENE_MOTION,
    CONF_SCENE_NIGHT,
    CONF_SUN_ELEV_BRIGHT_CEILING,
    CONF_SUN_ELEV_DARK_FLOOR,
    CONF_TRANSITION_TIME,
    CONF_TRANSITION_TIME_MOTION,
    DEFAULT_LUX_OFF_ABOVE,
    DEFAULT_LUX_ON_BELOW,
    DEFAULT_NIGHT_SCENE_END_TIME,
    DEFAULT_NIGHT_SCENE_START_TIME,
    DEFAULT_NO_MOTION_WAIT,
    DEFAULT_OVERRIDE_DURATION,
    DEFAULT_SUN_ELEV_BRIGHT_CEILING,
    DEFAULT_SUN_ELEV_DARK_FLOOR,
    DEFAULT_TRANSITION_TIME,
    DEFAULT_TRANSITION_TIME_MOTION,
)
from .logic import (
    LogicConfig,
    MotionSample,
    Phase,
    aggregate_lux,
    derive_phase,
    is_dark,
    motion_active,
    override_active,
    pick_scene,
    selection_reason,
)

_LOGGER = logging.getLogger(__name__)

SUN_ENTITY = "sun.sun"
SCENE_DOMAIN = "scene"
SCENE_SERVICE_TURN_ON = "turn_on"
OVERRIDE_SCENE_KEY = "override_scene"


ApplyScene = Callable[[], None]


def _noop_apply() -> None:
    """Fallback used before ``async_start`` wires the real runtime hook."""


def _parse_time(raw: str | dtime) -> dtime:
    """Accept both the string form persisted by TimeSelector and a real time."""
    if isinstance(raw, dtime):
        return raw
    return dtime.fromisoformat(raw)


def _crossed(old: float | None, new: float, threshold: float) -> bool:
    """True when the elevation moved across ``threshold`` (either direction).

    A missing ``old`` counts as a crossing so the first sun event after
    setup always triggers re-evaluation.
    """
    if old is None:
        return True
    if old <= threshold < new:
        return True
    if new <= threshold < old:
        return True
    return False


@dataclass(frozen=True)
class RuntimeConfig:
    """Snapshot of ``entry.data`` + ``entry.options`` resolved to typed values."""

    motion_sensors: tuple[str, ...]
    illuminance_sensors: tuple[str, ...]
    disable_flag: str | None
    scene_day: str
    scene_morning: str
    scene_evening: str
    scene_night: str
    scene_motion: str
    override_scene_default: str | None
    override_trigger: str | None
    night_start: dtime
    night_end: dtime
    lux_on_below: float
    lux_off_above: float
    sun_elev_dark_floor: float
    sun_elev_bright_ceiling: float
    no_motion_wait: float
    transition_time: float
    transition_time_motion: float
    override_duration: int

    @classmethod
    def from_entry(cls, entry: ConfigEntry) -> "RuntimeConfig":
        d = entry.data
        o = entry.options
        return cls(
            motion_sensors=tuple(d.get(CONF_MOTION_SENSORS) or ()),
            illuminance_sensors=tuple(d.get(CONF_ILLUMINANCE_SENSORS) or ()),
            disable_flag=d.get(CONF_DISABLE_FLAG) or None,
            scene_day=d[CONF_SCENE_DAY],
            scene_morning=d[CONF_SCENE_MORNING],
            scene_evening=d[CONF_SCENE_EVENING],
            scene_night=d[CONF_SCENE_NIGHT],
            scene_motion=d[CONF_SCENE_MOTION],
            override_scene_default=d.get(CONF_OVERRIDE_SCENE),
            override_trigger=d.get(CONF_OVERRIDE_TRIGGER) or None,
            night_start=_parse_time(
                o.get(CONF_NIGHT_SCENE_START_TIME, DEFAULT_NIGHT_SCENE_START_TIME)
            ),
            night_end=_parse_time(
                o.get(CONF_NIGHT_SCENE_END_TIME, DEFAULT_NIGHT_SCENE_END_TIME)
            ),
            lux_on_below=float(o.get(CONF_LUX_ON_BELOW, DEFAULT_LUX_ON_BELOW)),
            lux_off_above=float(o.get(CONF_LUX_OFF_ABOVE, DEFAULT_LUX_OFF_ABOVE)),
            sun_elev_dark_floor=float(
                o.get(CONF_SUN_ELEV_DARK_FLOOR, DEFAULT_SUN_ELEV_DARK_FLOOR)
            ),
            sun_elev_bright_ceiling=float(
                o.get(
                    CONF_SUN_ELEV_BRIGHT_CEILING, DEFAULT_SUN_ELEV_BRIGHT_CEILING
                )
            ),
            no_motion_wait=float(
                o.get(CONF_NO_MOTION_WAIT, DEFAULT_NO_MOTION_WAIT)
            ),
            transition_time=float(
                o.get(CONF_TRANSITION_TIME, DEFAULT_TRANSITION_TIME)
            ),
            transition_time_motion=float(
                o.get(
                    CONF_TRANSITION_TIME_MOTION, DEFAULT_TRANSITION_TIME_MOTION
                )
            ),
            override_duration=int(
                o.get(CONF_OVERRIDE_DURATION, DEFAULT_OVERRIDE_DURATION)
            ),
        )

    @property
    def logic(self) -> LogicConfig:
        return LogicConfig(
            night_start=self.night_start,
            night_end=self.night_end,
            lux_on_below=self.lux_on_below,
            lux_off_above=self.lux_off_above,
            sun_elev_dark_floor=self.sun_elev_dark_floor,
            sun_elev_bright_ceiling=self.sun_elev_bright_ceiling,
        )


@dataclass(frozen=True)
class DiagnosticsSnapshot:
    """Read-only snapshot of one evaluation cycle, for diagnostic entities."""

    motion: bool
    dark: bool
    illuminance: float | None
    sun_elevation: float | None
    phase: Phase
    reason: str
    override_active: bool
    override_scene: str | None
    override_until: datetime | None
    disabled: bool
    applied_scene: str | None
    updated_at: datetime


class UlkovalotCoordinator:
    """Runtime coordinator: subscriptions, override state, scene dispatch."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config = RuntimeConfig.from_entry(entry)
        self.override_scene: str | None = None
        self.override_until: datetime | None = None
        self.last_dark: bool = False
        self._cancel_timer: Callable[[], None] | None = None
        self._cancel_trigger: Callable[[], None] | None = None
        self._unsubs: list[Callable[[], None]] = []
        self._motion_timeouts: list[Callable[[], None]] = []
        self._pending_task: asyncio.Task | None = None
        self._last_sun_elev: float | None = None
        self.apply_scene: ApplyScene = _noop_apply
        self.diagnostics = DiagnosticsSnapshot(
            motion=False,
            dark=False,
            illuminance=None,
            sun_elevation=None,
            phase=Phase.DAY,
            reason="day",
            override_active=False,
            override_scene=None,
            override_until=None,
            disabled=False,
            applied_scene=None,
            updated_at=dt_util.utcnow(),
        )
        self._listeners: list[Callable[[], None]] = []

    # -- Diagnostics listeners ------------------------------------------------

    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback fired after every diagnostics update."""
        self._listeners.append(update_callback)

        def _remove() -> None:
            self._listeners.remove(update_callback)

        return _remove

    def _notify_listeners(self) -> None:
        for listener in self._listeners[:]:
            listener()

    # -- Override state machine ---------------------------------------------

    @property
    def _default_scene(self) -> str | None:
        return self.config.override_scene_default

    @property
    def _default_duration(self) -> int:
        return self.config.override_duration

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
        _LOGGER.info(
            "Override started: scene=%s until=%s",
            self.override_scene,
            self.override_until,
        )
        self._cancel_timer = async_call_later(self.hass, secs, self._on_expiry)
        self.apply_scene()

    def cancel_override(self) -> None:
        """Explicit cancel — clears state and re-evaluates immediately."""
        self._cancel_pending_timer()
        self._clear_override_state()
        _LOGGER.info("Override cancelled")
        self.apply_scene()

    # -- Lifecycle ----------------------------------------------------------

    async def async_start(self) -> None:
        """Wire runtime subscriptions and bind the apply-scene hook."""
        self.apply_scene = self._schedule_apply
        self.wire_trigger()
        self._register_subscriptions()

    def wire_trigger(self) -> None:
        """Subscribe to the optional override trigger entity, if configured."""
        trigger = self.config.override_trigger
        if not trigger:
            return
        _LOGGER.debug("Subscribed override trigger: %s", trigger)
        self._cancel_trigger = async_track_state_change_event(
            self.hass, [trigger], self._on_trigger_event
        )

    def unload(self) -> None:
        """Cancel every subscription, timer, and in-flight apply task."""
        self._cancel_pending_timer()
        if self._cancel_trigger is not None:
            self._cancel_trigger()
            self._cancel_trigger = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        for cancel in self._motion_timeouts:
            cancel()
        self._motion_timeouts.clear()
        if self._pending_task is not None and not self._pending_task.done():
            self._pending_task.cancel()
        self._pending_task = None
        self.apply_scene = _noop_apply
        self._listeners.clear()

    # -- Subscriptions ------------------------------------------------------

    def _register_subscriptions(self) -> None:
        cfg = self.config
        watched: list[str] = [*cfg.motion_sensors, *cfg.illuminance_sensors]
        if cfg.disable_flag:
            watched.append(cfg.disable_flag)
        if watched:
            self._unsubs.append(
                async_track_state_change_event(
                    self.hass, watched, self._on_watched_state
                )
            )
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, [SUN_ENTITY], self._on_sun_state
            )
        )
        for t in (cfg.night_start, cfg.night_end):
            self._unsubs.append(
                async_track_time_change(
                    self.hass,
                    self._on_time_trigger,
                    hour=t.hour,
                    minute=t.minute,
                    second=t.second,
                )
            )
        for event_name in (
            EVENT_HOMEASSISTANT_STARTED,
            EVENT_AUTOMATION_RELOADED,
        ):
            self._unsubs.append(
                self.hass.bus.async_listen(event_name, self._on_bus_event)
            )
        if self.hass.is_running:
            # Fire once so a running HA gets its first scene without waiting
            # for an unrelated trigger.
            self._schedule_apply()

    # -- Event handlers -----------------------------------------------------

    @callback
    def _on_watched_state(self, event: Event) -> None:
        entity_id = event.data.get("entity_id") or ""
        new = event.data.get("new_state")
        _LOGGER.debug(
            "Watched entity changed: %s -> %s", entity_id, new.state if new else None
        )
        if (
            entity_id in self.config.motion_sensors
            and new is not None
            and new.state == "off"
        ):
            # Re-fire after the wait window so latched motion drops back out.
            cancel = async_call_later(
                self.hass,
                self.config.no_motion_wait,
                self._on_motion_timeout,
            )
            self._motion_timeouts.append(cancel)
        self._schedule_apply()

    @callback
    def _on_sun_state(self, event: Event) -> None:
        new = event.data.get("new_state")
        if new is None:
            return
        try:
            new_elev = float(new.attributes.get("elevation"))
        except (TypeError, ValueError):
            return
        old_elev = self._last_sun_elev
        self._last_sun_elev = new_elev
        cfg = self.config
        if _crossed(old_elev, new_elev, cfg.sun_elev_dark_floor) or _crossed(
            old_elev, new_elev, cfg.sun_elev_bright_ceiling
        ):
            old_repr = "None" if old_elev is None else f"{old_elev:.1f}"
            _LOGGER.debug(
                "Sun elevation crossed threshold: %s -> %.1f", old_repr, new_elev
            )
            self._schedule_apply()

    @callback
    def _on_time_trigger(self, _now: datetime) -> None:
        self._schedule_apply()

    @callback
    def _on_bus_event(self, _event: Event) -> None:
        self._schedule_apply()

    @callback
    def _on_motion_timeout(self, _now: datetime) -> None:
        self._schedule_apply()

    @callback
    def _on_trigger_event(self, _event: Event) -> None:
        self.start_override()

    @callback
    def _on_expiry(self, _now: datetime) -> None:
        self._cancel_timer = None
        _LOGGER.info("Override expired")
        self._clear_override_state()
        self.apply_scene()

    # -- Apply --------------------------------------------------------------

    @callback
    def _schedule_apply(self) -> None:
        """Restart semantics: cancel any pending apply and queue a fresh one.

        Uses ``eager_start=False`` so cancellation actually preempts the
        coroutine body — eager tasks would run their synchronous prefix
        before ``cancel()`` gets a chance to land.
        """
        if self._pending_task is not None and not self._pending_task.done():
            self._pending_task.cancel()
        self._pending_task = self.hass.async_create_task(
            self._async_apply(), eager_start=False
        )

    async def _async_apply(self) -> None:
        try:
            await self._apply_scene_impl()
        except asyncio.CancelledError:
            _LOGGER.debug("apply_scene cancelled by a newer trigger")
            raise

    async def _apply_scene_impl(self) -> None:
        cfg = self.config
        disabled = False
        if cfg.disable_flag:
            state = self.hass.states.get(cfg.disable_flag)
            disabled = state is not None and state.state == "on"

        elev, rising = self._read_sun()
        lux_readings = [
            (
                self.hass.states.get(sid).state
                if self.hass.states.get(sid) is not None
                else None
            )
            for sid in cfg.illuminance_sensors
        ]
        lux = aggregate_lux(lux_readings)
        self.last_dark = is_dark(elev, lux, self.last_dark, cfg.logic)
        now_local = dt_util.now()
        phase = derive_phase(now_local, rising, self.last_dark, cfg.logic)
        motion_samples: list[MotionSample] = []
        for sid in cfg.motion_sensors:
            state = self.hass.states.get(sid)
            if state is None:
                continue
            motion_samples.append(
                MotionSample(state=state.state, last_changed=state.last_changed)
            )
        now_utc = dt_util.utcnow()
        motion = motion_active(now_utc, motion_samples, cfg.no_motion_wait)
        override = override_active(now_utc, self.override_until)
        reason = selection_reason(phase, motion, override, disabled)
        scene_key, transition_key = pick_scene(phase, motion, override)
        _LOGGER.debug(
            "Apply: elev=%.1f lux=%s dark=%s phase=%s motion=%s override=%s "
            "disabled=%s -> %s",
            elev,
            lux,
            self.last_dark,
            phase,
            motion,
            override,
            disabled,
            scene_key,
        )

        applied_scene: str | None = None
        if disabled:
            _LOGGER.debug("Disabled via %s — skipping apply", cfg.disable_flag)
        else:
            entity = self._resolve_scene_entity(scene_key)
            if not entity:
                _LOGGER.debug("No scene entity resolved for key %s", scene_key)
            elif not self.hass.services.has_service(
                SCENE_DOMAIN, SCENE_SERVICE_TURN_ON
            ):
                _LOGGER.debug("scene.turn_on not available yet — skipping dispatch")
            else:
                transition = getattr(cfg, transition_key)
                _LOGGER.debug(
                    "Dispatching scene.turn_on entity=%s transition=%s",
                    entity,
                    transition,
                )
                await self.hass.services.async_call(
                    SCENE_DOMAIN,
                    SCENE_SERVICE_TURN_ON,
                    {"entity_id": entity, "transition": transition},
                    blocking=False,
                )
                applied_scene = entity

        self.diagnostics = DiagnosticsSnapshot(
            motion=motion,
            dark=self.last_dark,
            illuminance=lux,
            sun_elevation=elev,
            phase=phase,
            reason=reason,
            override_active=override,
            override_scene=self.override_scene,
            override_until=self.override_until,
            disabled=disabled,
            applied_scene=applied_scene,
            updated_at=now_utc,
        )
        self._notify_listeners()

    def _read_sun(self) -> tuple[float, bool]:
        state = self.hass.states.get(SUN_ENTITY)
        if state is None:
            return 0.0, False
        try:
            elev = float(state.attributes.get("elevation"))
        except (TypeError, ValueError):
            elev = 0.0
        rising = bool(state.attributes.get("rising", False))
        return elev, rising

    def _resolve_scene_entity(self, scene_key: str) -> str | None:
        if scene_key == OVERRIDE_SCENE_KEY:
            return self.override_scene or self.config.override_scene_default
        return getattr(self.config, scene_key, None)

    # -- Helpers ------------------------------------------------------------

    def _cancel_pending_timer(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None

    def _clear_override_state(self) -> None:
        self.override_scene = None
        self.override_until = None
