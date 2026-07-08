"""Config, reconfigure, and options flows for ulkovalot."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TimeSelector,
)

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
    DATA_KEYS,
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
    DOMAIN,
    ERROR_LUX_HYSTERESIS,
    ERROR_SUN_ELEV_RANGE,
    LUX_MAX,
    LUX_MIN,
    LUX_STEP,
    LUX_UNIT,
    OPTION_KEYS,
    OVERRIDE_DURATION_MAX,
    OVERRIDE_DURATION_MIN,
    OVERRIDE_DURATION_STEP,
    OVERRIDE_DURATION_UNIT,
    SUN_ELEV_MAX,
    SUN_ELEV_MIN,
    SUN_ELEV_STEP,
    SUN_ELEV_UNIT,
    TRANSITION_MAX,
    TRANSITION_MIN,
    TRANSITION_STEP,
    TRANSITION_UNIT,
    WAIT_MAX,
    WAIT_MIN,
    WAIT_STEP,
    WAIT_UNIT,
)


def _lux_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=LUX_MIN,
            max=LUX_MAX,
            step=LUX_STEP,
            unit_of_measurement=LUX_UNIT,
            mode=NumberSelectorMode.BOX,
        )
    )


def _sun_elev_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=SUN_ELEV_MIN,
            max=SUN_ELEV_MAX,
            step=SUN_ELEV_STEP,
            unit_of_measurement=SUN_ELEV_UNIT,
            mode=NumberSelectorMode.BOX,
        )
    )


def _wait_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=WAIT_MIN,
            max=WAIT_MAX,
            step=WAIT_STEP,
            unit_of_measurement=WAIT_UNIT,
            mode=NumberSelectorMode.BOX,
        )
    )


def _transition_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=TRANSITION_MIN,
            max=TRANSITION_MAX,
            step=TRANSITION_STEP,
            unit_of_measurement=TRANSITION_UNIT,
            mode=NumberSelectorMode.BOX,
        )
    )


def _override_duration_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=OVERRIDE_DURATION_MIN,
            max=OVERRIDE_DURATION_MAX,
            step=OVERRIDE_DURATION_STEP,
            unit_of_measurement=OVERRIDE_DURATION_UNIT,
            mode=NumberSelectorMode.BOX,
        )
    )


def _data_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema for identity fields (sensors, scenes, triggers)."""

    def _default(key: str, fallback: Any = vol.UNDEFINED) -> Any:
        if key in defaults and defaults[key] is not None:
            return defaults[key]
        return fallback

    return vol.Schema(
        {
            vol.Required(
                CONF_MOTION_SENSORS,
                default=_default(CONF_MOTION_SENSORS, []),
            ): EntitySelector(
                EntitySelectorConfig(domain="binary_sensor", multiple=True)
            ),
            vol.Required(
                CONF_ILLUMINANCE_SENSORS,
                default=_default(CONF_ILLUMINANCE_SENSORS, []),
            ): EntitySelector(EntitySelectorConfig(domain="sensor", multiple=True)),
            vol.Optional(
                CONF_DISABLE_FLAG,
                default=_default(CONF_DISABLE_FLAG, vol.UNDEFINED),
            ): EntitySelector(EntitySelectorConfig()),
            vol.Required(
                CONF_SCENE_DAY, default=_default(CONF_SCENE_DAY)
            ): EntitySelector(EntitySelectorConfig(domain="scene")),
            vol.Required(
                CONF_SCENE_MORNING, default=_default(CONF_SCENE_MORNING)
            ): EntitySelector(EntitySelectorConfig(domain="scene")),
            vol.Required(
                CONF_SCENE_EVENING, default=_default(CONF_SCENE_EVENING)
            ): EntitySelector(EntitySelectorConfig(domain="scene")),
            vol.Required(
                CONF_SCENE_NIGHT, default=_default(CONF_SCENE_NIGHT)
            ): EntitySelector(EntitySelectorConfig(domain="scene")),
            vol.Required(
                CONF_SCENE_MOTION, default=_default(CONF_SCENE_MOTION)
            ): EntitySelector(EntitySelectorConfig(domain="scene")),
            vol.Required(
                CONF_OVERRIDE_SCENE, default=_default(CONF_OVERRIDE_SCENE)
            ): EntitySelector(EntitySelectorConfig(domain="scene")),
            vol.Optional(
                CONF_OVERRIDE_TRIGGER,
                default=_default(CONF_OVERRIDE_TRIGGER, vol.UNDEFINED),
            ): EntitySelector(EntitySelectorConfig()),
        }
    )


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema for runtime-tunable fields (thresholds, times, waits)."""

    def _d(key: str, fallback: Any) -> Any:
        return defaults.get(key, fallback)

    return vol.Schema(
        {
            vol.Required(
                CONF_NIGHT_SCENE_START_TIME,
                default=_d(CONF_NIGHT_SCENE_START_TIME, DEFAULT_NIGHT_SCENE_START_TIME),
            ): TimeSelector(),
            vol.Required(
                CONF_NIGHT_SCENE_END_TIME,
                default=_d(CONF_NIGHT_SCENE_END_TIME, DEFAULT_NIGHT_SCENE_END_TIME),
            ): TimeSelector(),
            vol.Required(
                CONF_LUX_ON_BELOW,
                default=_d(CONF_LUX_ON_BELOW, DEFAULT_LUX_ON_BELOW),
            ): _lux_selector(),
            vol.Required(
                CONF_LUX_OFF_ABOVE,
                default=_d(CONF_LUX_OFF_ABOVE, DEFAULT_LUX_OFF_ABOVE),
            ): _lux_selector(),
            vol.Required(
                CONF_SUN_ELEV_DARK_FLOOR,
                default=_d(CONF_SUN_ELEV_DARK_FLOOR, DEFAULT_SUN_ELEV_DARK_FLOOR),
            ): _sun_elev_selector(),
            vol.Required(
                CONF_SUN_ELEV_BRIGHT_CEILING,
                default=_d(
                    CONF_SUN_ELEV_BRIGHT_CEILING, DEFAULT_SUN_ELEV_BRIGHT_CEILING
                ),
            ): _sun_elev_selector(),
            vol.Required(
                CONF_NO_MOTION_WAIT,
                default=_d(CONF_NO_MOTION_WAIT, DEFAULT_NO_MOTION_WAIT),
            ): _wait_selector(),
            vol.Required(
                CONF_TRANSITION_TIME,
                default=_d(CONF_TRANSITION_TIME, DEFAULT_TRANSITION_TIME),
            ): _transition_selector(),
            vol.Required(
                CONF_TRANSITION_TIME_MOTION,
                default=_d(
                    CONF_TRANSITION_TIME_MOTION, DEFAULT_TRANSITION_TIME_MOTION
                ),
            ): _transition_selector(),
            vol.Required(
                CONF_OVERRIDE_DURATION,
                default=_d(CONF_OVERRIDE_DURATION, DEFAULT_OVERRIDE_DURATION),
            ): _override_duration_selector(),
        }
    )


def _full_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Combined schema for the initial user step."""
    return _data_schema(defaults).extend(_options_schema(defaults).schema)


def _validate_thresholds(values: dict[str, Any]) -> dict[str, str]:
    """Return a mapping of field → error key for invalid combinations."""
    errors: dict[str, str] = {}
    lux_on = values.get(CONF_LUX_ON_BELOW)
    lux_off = values.get(CONF_LUX_OFF_ABOVE)
    if lux_on is not None and lux_off is not None and lux_off <= lux_on:
        errors[CONF_LUX_OFF_ABOVE] = ERROR_LUX_HYSTERESIS

    floor = values.get(CONF_SUN_ELEV_DARK_FLOOR)
    ceiling = values.get(CONF_SUN_ELEV_BRIGHT_CEILING)
    if floor is not None and ceiling is not None and ceiling <= floor:
        errors[CONF_SUN_ELEV_BRIGHT_CEILING] = ERROR_SUN_ELEV_RANGE
    return errors


def _split(values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split submitted values into (data, options) buckets."""
    data = {k: values[k] for k in DATA_KEYS if k in values}
    options = {k: values[k] for k in OPTION_KEYS if k in values}
    return data, options


class UlkovalotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config + reconfigure flow for ulkovalot."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Initial user step — collects full config."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate_thresholds(user_input)
            if not errors:
                data, options = _split(user_input)
                return self.async_create_entry(
                    title="Outdoor lights coordinator",
                    data=data,
                    options=options,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_full_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure step — edit the initial identity + option set."""
        entry = self._get_reconfigure_entry()
        defaults = {**entry.data, **entry.options}
        if user_input is not None:
            merged = {**defaults, **user_input}
            errors = _validate_thresholds(merged)
            if not errors:
                data, options = _split(merged)
                return self.async_update_reload_and_abort(
                    entry,
                    data=data,
                    options=options,
                )
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=_full_schema({**defaults, **user_input}),
                errors=errors,
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_full_schema(defaults),
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow handler."""
        return UlkovalotOptionsFlow()


class UlkovalotOptionsFlow(OptionsFlow):
    """Options flow — runtime-tunable subset only."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Present the options schema."""
        defaults = dict(self.config_entry.options)
        if user_input is not None:
            merged = {**defaults, **user_input}
            errors = _validate_thresholds(merged)
            if not errors:
                return self.async_create_entry(title="", data=merged)
            return self.async_show_form(
                step_id="init",
                data_schema=_options_schema(merged),
                errors=errors,
            )
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(defaults),
        )
