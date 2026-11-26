"""Switch platform."""

import logging
from typing import TYPE_CHECKING, Any, override

from aioonkyo import command, status

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Channel, ChannelMutingCoordinator
from .extra_entity import OnkyoExtraEntity
from .extras import ReceiverExtras

if TYPE_CHECKING:
    from . import OnkyoConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnkyoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switch platform for config entry."""
    if (extras := entry.runtime_data.extras) is not None:
        async_add_entities(
            OnkyoReceiverSwitch(extras, key)
            for key in ("music_optimizer", "hdmi_cec", "hdmi_audio_out", "arc", "cinema_filter")
        )

    @callback
    def async_add_channel_muting_entities(
        coordinator: ChannelMutingCoordinator,
    ) -> None:
        """Add channel muting switch entities."""
        async_add_entities(
            OnkyoChannelMutingSwitch(coordinator, channel) for channel in Channel
        )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass,
            f"{DOMAIN}_{entry.entry_id}_channel_muting",
            async_add_channel_muting_entities,
        )
    )


class OnkyoReceiverSwitch(OnkyoExtraEntity, SwitchEntity):
    """Simple on/off receiver setting."""

    def __init__(self, extras: ReceiverExtras, key: str) -> None:
        super().__init__(extras, key)
        if key in ("hdmi_cec", "hdmi_audio_out", "arc"):
            self._attr_entity_registry_enabled_default = False

    @property
    def is_on(self) -> bool | None:
        value = self._extras.values.get(self._key)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._extras.set(self._key, b"01")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._extras.set(self._key, b"00")


class OnkyoChannelMutingSwitch(
    CoordinatorEntity[ChannelMutingCoordinator], SwitchEntity
):
    """Onkyo Receiver Channel Muting Switch (one per channel)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ChannelMutingCoordinator,
        channel: Channel,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(coordinator)

        self._channel = channel

        channel_name = channel.replace("_", " ")
        identifier = coordinator.manager.info.identifier
        self._attr_device_info = coordinator.manager.device_info
        self._attr_name = f"Mute {channel_name}"
        self._attr_unique_id = f"{identifier}-channel_muting-{channel}"

    @property
    @override
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.manager.connected

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Mute the channel."""
        await self.coordinator.async_send_command(
            self._channel, command.ChannelMuting.Param.ON
        )

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unmute the channel."""
        await self.coordinator.async_send_command(
            self._channel, command.ChannelMuting.Param.OFF
        )

    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        value = self.coordinator.data.get(self._channel)
        self._attr_is_on = (
            None if value is None else value is status.ChannelMuting.Param.ON
        )
        super()._handle_coordinator_update()
