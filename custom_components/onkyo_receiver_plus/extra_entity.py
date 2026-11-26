"""Base for the auxiliary entities belonging to one Onkyo receiver."""

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .extras import ReceiverExtras


class OnkyoExtraEntity(Entity):
    """Expose auxiliary data using the shared push connection."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, extras: ReceiverExtras, key: str) -> None:
        self._extras = extras
        self._key = key
        self._attr_translation_key = key
        self._attr_unique_id = f"{extras.manager.info.identifier}_{key}"
        self._attr_device_info = extras.manager.device_info

    @property
    def available(self) -> bool:
        return self._extras.available(self._key)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, self._extras.signal, self.async_write_ha_state
            )
        )
