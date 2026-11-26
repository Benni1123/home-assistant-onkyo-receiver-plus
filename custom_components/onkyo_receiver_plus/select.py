"""Receiver options exposed as select entities."""

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .extra_entity import OnkyoExtraEntity
from .extras import (
    ACCUEQ, DIGITAL_FILTER, DIMMER, MANUAL_EQ, NIGHT, OUTPUT, STEREO_ASSIGN, ReceiverExtras
)

if TYPE_CHECKING:
    from . import OnkyoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: OnkyoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if (extras := entry.runtime_data.extras) is not None:
        async_add_entities(
            OnkyoReceiverSelect(extras, key, values)
            for key, values in (
                ("dimmer", DIMMER), ("late_night", NIGHT), ("hdmi_output", OUTPUT),
                ("accueq", ACCUEQ), ("manual_eq", MANUAL_EQ),
                ("digital_filter", DIGITAL_FILTER), ("stereo_assign", STEREO_ASSIGN),
            )
        )


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
