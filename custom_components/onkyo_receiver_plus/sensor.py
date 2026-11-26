"""Audio, video and display information from the receiver."""

from typing import TYPE_CHECKING

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .extra_entity import OnkyoExtraEntity
from .extras import ReceiverExtras

if TYPE_CHECKING:
    from . import OnkyoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: OnkyoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if (extras := entry.runtime_data.extras) is not None:
        async_add_entities(
            OnkyoReceiverSensor(extras, key)
            for key in ("audio_signal", "audio_input_channels", "audio_output_channels",
                        "video_signal", "video_hdr", "display", "firmware_version",
                        "speaker_configuration", "receiver_temperature", "hdmi_routing")
        )


class OnkyoReceiverSensor(OnkyoExtraEntity, SensorEntity):
    """Expose a confirmed field from AVR metadata."""

    def __init__(self, extras: ReceiverExtras, key: str) -> None:
        super().__init__(extras, key)
        if key == "display":
            self._attr_entity_registry_enabled_default = False
        if key in ("firmware_version", "speaker_configuration", "receiver_temperature", "hdmi_routing"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if key == "receiver_temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self) -> str | int | None:
        if self._key == "firmware_version":
            return self._extras.firmware
        value = self._extras.values.get(self._key)
        if self._key == "receiver_temperature":
            return value if type(value) is int else None
        return value if isinstance(value, str) else None

    @property
    def extra_state_attributes(self) -> dict[str, str | int] | None:
        if self._key == "audio_signal":
            return self._extras.audio
        if self._key == "video_signal":
            return self._extras.video
        if self._key == "speaker_configuration":
            return self._extras.speakers
        if self._key == "hdmi_routing":
            return self._extras.hdmi_routing
        return None
