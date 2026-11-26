"""Receiver options exposed as select entities."""

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .extra_entity import OnkyoExtraEntity
from .radio_controls import FmEditSelection
from .extras import (
    ACCUEQ,
    DIGITAL_FILTER,
    DIMMER,
    MANUAL_EQ,
    NIGHT,
    OUTPUT,
    STEREO_ASSIGN,
    TUNER_SOURCES,
    ReceiverExtras,
)

if TYPE_CHECKING:
    from . import OnkyoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: OnkyoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if getattr(entry.runtime_data, "fm", None) is not None:
        async_add_entities([FmEditSelection(entry.runtime_data)])
    if (extras := entry.runtime_data.extras) is not None:
        async_add_entities(
            OnkyoReceiverSelect(extras, key, values)
            for key, values in (
                ("dimmer", DIMMER), ("late_night", NIGHT), ("hdmi_output", OUTPUT),
                ("accueq", ACCUEQ), ("manual_eq", MANUAL_EQ),
                ("digital_filter", DIGITAL_FILTER), ("stereo_assign", STEREO_ASSIGN),
            )
        )
        async_add_entities([OnkyoTunerPresetSelect(extras)])


class OnkyoTunerPresetSelect(OnkyoExtraEntity, SelectEntity):
    """Tuner presets carrying the names reported by the receiver."""

    _attr_translation_key = "tuner_preset"

    def __init__(self, extras: ReceiverExtras) -> None:
        super().__init__(extras, "tuner_preset")
        self._attr_unique_id = f"{extras.manager.info.identifier}_tuner_preset_select"

    @property
    def available(self) -> bool:
        """Preset selection needs an active tuner input, like the AVR remote."""
        extras = self._extras
        return (
            extras.manager.connected and extras.powered and extras.source in TUNER_SOURCES
        )

    @property
    def options(self) -> list[str]:
        """Only slots the receiver has stored, prefixed by their number."""
        labels = []
        for index, preset in sorted(self._extras.manager.presets.items()):
            name = str(preset.get("name") or "").strip()
            labels.append(f"{index:02d}" + (f": {name}" if name else ""))
        return labels

    @property
    def current_option(self) -> str | None:
        value = self._extras.values.get("tuner_preset")
        if not isinstance(value, int) or not 1 <= value <= 40:
            return None
        for label in self.options:
            if label.startswith(f"{value:02d}"):
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        """Recall a stored preset; the band follows the stored preset."""
        if option not in self.options:
            raise ServiceValidationError("That tuner preset is not stored on the receiver.")
        await self._extras.set("tuner_preset", f"{int(option[:2]):02X}".encode())


class OnkyoReceiverSelect(OnkyoExtraEntity, SelectEntity):
    """An enumerated receiver setting."""

    def __init__(self, extras: ReceiverExtras, key: str, values: dict[str, bytes]) -> None:
        super().__init__(extras, key)
        self._values = values

    @property
    def options(self) -> list[str]:
        if self._key == "stereo_assign":
            return [
                name for name in self._values
                if name == "front" or self._extras.speakers.get(name) in ("small", "large")
                or name == self.current_option
            ]
        return list(self._values)

    @property
    def current_option(self) -> str | None:
        value = self._extras.values.get(self._key)
        return value if isinstance(value, str) and value in self._values else None

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError("Receiver option is not supported.")
        await self._extras.set(self._key, self._values[option])
