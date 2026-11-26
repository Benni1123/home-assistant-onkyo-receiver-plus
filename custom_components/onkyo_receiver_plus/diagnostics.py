"""Diagnostics support for Onkyo."""

from typing import Any

from homeassistant.core import HomeAssistant

from . import OnkyoConfigEntry
from .const import (
    OPTION_AUTO_INPUT_NAMES,
    OPTION_INPUT_SOURCES,
    OPTION_LISTENING_MODES,
    OPTION_MAX_VOLUME,
    OPTION_SHOW_HDMI_PORTS,
    OPTION_VOLUME_MODE,
    OPTION_VOLUME_RESOLUTION,
    OPTION_VOLUME_STEP_DELAY,
)

SAFE_OPTIONS = (
    OPTION_AUTO_INPUT_NAMES,
    OPTION_MAX_VOLUME,
    OPTION_SHOW_HDMI_PORTS,
    OPTION_VOLUME_MODE,
    OPTION_VOLUME_RESOLUTION,
    OPTION_VOLUME_STEP_DELAY,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: OnkyoConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data
    manager = data.manager
    options = {
        key: entry.options[key] for key in SAFE_OPTIONS if key in entry.options
    }
    for key in (OPTION_INPUT_SOURCES, OPTION_LISTENING_MODES):
        if key in entry.options:
            options[key] = list(entry.options[key])

    return {
        "model_name": manager.info.model_name,
        "connected": manager.connected,
        "firmware_version": data.extras.firmware if data.extras is not None else None,
        "hdmi_ports": {source.value: port for source, port in manager.hdmi_ports.items()},
        "options": options,
        "channel_muting": {
            channel.value: param.name
            for channel, param in data.channel_muting_coordinator.data.items()
        },
    }
