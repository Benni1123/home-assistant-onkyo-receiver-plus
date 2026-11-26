"""Read-only receiver feature status."""

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .extra_entity import OnkyoExtraEntity

if TYPE_CHECKING:
    from . import OnkyoConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: OnkyoConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    if (extras := entry.runtime_data.extras) is not None:
        async_add_entities(
            OnkyoDiagnosticFlag(extras, key)
            for key in ("network_standby", "dts_dialog_supported")
        )


class OnkyoDiagnosticFlag(OnkyoExtraEntity, BinarySensorEntity):
    """Show whether a receiver feature is active or available."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        value = self._extras.values.get(self._key)
        return value if isinstance(value, bool) else None
