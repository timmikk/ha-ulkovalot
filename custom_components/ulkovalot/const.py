"""Constants for ulkovalot."""

from __future__ import annotations

DOMAIN = "ulkovalot"

PLATFORMS: list[str] = []

# --- Config keys -----------------------------------------------------------
# entry.data (immutable identity — sensors, scenes, trigger targets)
CONF_ILLUMINANCE_SENSORS = "illuminance_sensors"
CONF_MOTION_SENSORS = "motion_sensors"
CONF_DISABLE_FLAG = "disable_flag"
CONF_SCENE_DAY = "scene_day"
CONF_SCENE_MORNING = "scene_morning"
CONF_SCENE_EVENING = "scene_evening"
CONF_SCENE_NIGHT = "scene_night"
CONF_SCENE_MOTION = "scene_motion"
CONF_OVERRIDE_SCENE = "override_scene"
CONF_OVERRIDE_TRIGGER = "override_trigger"

# entry.options (runtime-tunable — thresholds, times, waits, transitions)
CONF_NIGHT_SCENE_START_TIME = "night_scene_start_time"
CONF_NIGHT_SCENE_END_TIME = "night_scene_end_time"
CONF_LUX_ON_BELOW = "lux_on_below"
CONF_LUX_OFF_ABOVE = "lux_off_above"
CONF_SUN_ELEV_DARK_FLOOR = "sun_elev_dark_floor"
CONF_SUN_ELEV_BRIGHT_CEILING = "sun_elev_bright_ceiling"
CONF_NO_MOTION_WAIT = "no_motion_wait"
CONF_TRANSITION_TIME = "transition_time"
CONF_TRANSITION_TIME_MOTION = "transition_time_motion"
CONF_OVERRIDE_DURATION = "override_duration"

DATA_KEYS: tuple[str, ...] = (
    CONF_ILLUMINANCE_SENSORS,
    CONF_MOTION_SENSORS,
    CONF_DISABLE_FLAG,
    CONF_SCENE_DAY,
    CONF_SCENE_MORNING,
    CONF_SCENE_EVENING,
    CONF_SCENE_NIGHT,
    CONF_SCENE_MOTION,
    CONF_OVERRIDE_SCENE,
    CONF_OVERRIDE_TRIGGER,
)

OPTION_KEYS: tuple[str, ...] = (
    CONF_NIGHT_SCENE_START_TIME,
    CONF_NIGHT_SCENE_END_TIME,
    CONF_LUX_ON_BELOW,
    CONF_LUX_OFF_ABOVE,
    CONF_SUN_ELEV_DARK_FLOOR,
    CONF_SUN_ELEV_BRIGHT_CEILING,
    CONF_NO_MOTION_WAIT,
    CONF_TRANSITION_TIME,
    CONF_TRANSITION_TIME_MOTION,
    CONF_OVERRIDE_DURATION,
)

# --- Defaults --------------------------------------------------------------
DEFAULT_NIGHT_SCENE_START_TIME = "23:00:00"
DEFAULT_NIGHT_SCENE_END_TIME = "07:00:00"
DEFAULT_LUX_ON_BELOW = 30
DEFAULT_LUX_OFF_ABOVE = 100
DEFAULT_SUN_ELEV_DARK_FLOOR = -3
DEFAULT_SUN_ELEV_BRIGHT_CEILING = 6
DEFAULT_NO_MOTION_WAIT = 120
DEFAULT_TRANSITION_TIME = 10
DEFAULT_TRANSITION_TIME_MOTION = 1
DEFAULT_OVERRIDE_DURATION = 7200

# --- Ranges & units --------------------------------------------------------
LUX_MIN = 0
LUX_MAX = 10000
LUX_STEP = 1
LUX_UNIT = "lx"

SUN_ELEV_MIN = -20
SUN_ELEV_MAX = 20
SUN_ELEV_STEP = 0.1
SUN_ELEV_UNIT = "°"

WAIT_MIN = 0
WAIT_MAX = 3600
WAIT_STEP = 1
WAIT_UNIT = "s"

TRANSITION_MIN = 0
TRANSITION_MAX = 300
TRANSITION_STEP = 1
TRANSITION_UNIT = "s"

OVERRIDE_DURATION_MIN = 1
OVERRIDE_DURATION_MAX = 86400
OVERRIDE_DURATION_STEP = 1
OVERRIDE_DURATION_UNIT = "s"

# --- Error keys ------------------------------------------------------------
ERROR_LUX_HYSTERESIS = "lux_hysteresis_invalid"
ERROR_SUN_ELEV_RANGE = "sun_elev_range_invalid"
