"""Expose the receiver's network remote in Home Assistant."""

import asyncio
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from aioonkyo import Status, Zone, command, query, status
from aioonkyo.instruction import RawInstruction

from homeassistant.components.remote import (
    ATTR_DELAY_SECS,
    ATTR_HOLD_SECS,
    ATTR_NUM_REPEATS,
    DEFAULT_DELAY_SECS,
    DEFAULT_NUM_REPEATS,
    RemoteEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .media_player import DATA_MP_ENTITIES, OnkyoMediaPlayer
from .receiver import ReceiverManager
from .source_names import DEVICE_INFO_CODE, parse_remote_menu_keys

if TYPE_CHECKING:
    from . import OnkyoConfigEntry

KEYS = {
    "up": (b"OSD", b"UP"),
    "down": (b"OSD", b"DOWN"),
    "left": (b"OSD", b"LEFT"),
    "right": (b"OSD", b"RIGHT"),
    "ok": (b"OSD", b"ENTER"),
    "back": (b"OSD", b"EXIT"),
    "setup": (b"OSD", b"MENU"),
    "quick_menu": (b"OSD", b"QUICK"),
    "mute": (b"AMT", b"TG"),
    "play": (b"NTC", b"PLAY"),
    "pause": (b"NTC", b"PAUSE"),
    "play_pause": (b"NTC", b"P/P"),
    "stop": (b"NTC", b"STOP"),
    "next_track": (b"NTC", b"TRUP"),
    "previous_track": (b"NTC", b"TRDN"),
}
ALIASES = {"enter": "ok", "exit": "back", "menu": "setup", "quick": "quick_menu"}
POWER_KEYS = {"power_on", "power_off"}
MEDIA_PLAYER_KEYS = {"volume_up", "volume_down", "input"}
MAX_SEQUENCE_LENGTH = 32
MIN_DELAY = 0.12
MAX_DELAY = 10


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnkyoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Expose the main-zone remote for the configured eISCP receiver."""
    manager = entry.runtime_data.manager
    async_add_entities([OnkyoRemote(manager)])


class OnkyoRemote(RemoteEntity):
    """A virtual remote using the same connection as the AVR entities."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_translation_key = "network_remote"
    _attr_icon = "mdi:remote"

    def __init__(self, manager: ReceiverManager) -> None:
        self._manager = manager
        self._attr_unique_id = f"{manager.info.identifier}_remote"
        self._attr_device_info = manager.device_info
        self._command_lock = asyncio.Lock()
        self._menu_keys: dict[str, bytes] = {}

    @property
    def available(self) -> bool:
        return self._manager.connected

    @property
    def extra_state_attributes(self) -> dict[str, list[str]]:
        return {
            "commands": sorted(KEYS.keys() | POWER_KEYS | (MEDIA_PLAYER_KEYS - {"input"}))
            + ["input:<name>"]
        }

    async def async_added_to_hass(self) -> None:
        for callbacks, handler in (
            (self._manager.callbacks.update, self._on_update),
            (self._manager.callbacks.disconnect, self._on_disconnect),
        ):
            callbacks.append(handler)
            self.async_on_remove(
                lambda callbacks=callbacks, handler=handler: (
                    callbacks.remove(handler) if handler in callbacks else None
                )
            )
        if self.available:
            await self._manager.write(query.Power(Zone.MAIN))

    async def _on_update(self, message: Status) -> None:
        if isinstance(message, status.Raw) and message.raw_code == DEVICE_INFO_CODE:
            if keys := parse_remote_menu_keys(message.parameter):
                self._menu_keys = keys
            return
        if isinstance(message, status.Power) and message.zone is Zone.MAIN:
            is_on = message.param is status.Power.Param.ON
            if self._attr_is_on != is_on:
                self._attr_is_on = is_on
                self.async_write_ha_state()

    async def _on_disconnect(self) -> None:
        self._attr_is_on = None
        self.async_write_ha_state()

    def _main_player(self) -> OnkyoMediaPlayer | None:
        players = self.hass.data[DATA_MP_ENTITIES].get(self._manager.entry.entry_id, {})
        return players.get(Zone.MAIN)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self.available:
            raise HomeAssistantError("Receiver is not connected.")
        await self._manager.write(command.Power(Zone.MAIN, command.Power.Param.ON))

    async def async_turn_off(self, **kwargs: Any) -> None:
        if not self.available:
            raise HomeAssistantError("Receiver is not connected.")
        if (player := self._main_player()) is not None:
            await player.async_turn_off()
        else:
            await self._manager.write(command.Power(Zone.MAIN, command.Power.Param.STANDBY))

    async def async_send_command(
        self, command: Iterable[str] | str | None = None, **kwargs: Any
    ) -> None:
        """Validate the whole sequence before sending any network key."""
        # HA calls this entity service with keyword arguments from the service
        # data, so `command` (singular) arrives as a keyword by default.
        if command is None:
            command = kwargs.get("command")
        if kwargs.get(ATTR_HOLD_SECS):
            raise ServiceValidationError("Use num_repeats instead of hold_secs for this remote.")
        parsed: list[tuple[str, str | None]] = []
        if command is None:
            command = ()
        if isinstance(command, str):
            commands: Iterable[str] = (command,)
        else:
            commands = command
        for item in commands:
            key, colon, argument = item.strip().partition(":")
            key = key.strip().lower()
            key = ALIASES.get(key, key)
            argument = argument.strip()
            if (key == "input" and not argument) or (
                key != "input" and (colon or key not in KEYS.keys() | POWER_KEYS | MEDIA_PLAYER_KEYS)
            ):
                raise ServiceValidationError(f"Unknown receiver remote key: {key!r}.")
            parsed.append((key, argument if colon else None))
        repeats = kwargs.get(ATTR_NUM_REPEATS, DEFAULT_NUM_REPEATS)
        if not parsed or not 1 <= repeats or repeats * len(parsed) > MAX_SEQUENCE_LENGTH:
            raise ServiceValidationError(f"Send between 1 and {MAX_SEQUENCE_LENGTH} remote keys.")
        delay = kwargs.get(ATTR_DELAY_SECS, DEFAULT_DELAY_SECS)
        if not 0 <= delay <= MAX_DELAY:
            raise ServiceValidationError(f"Delay must be between 0 and {MAX_DELAY} seconds.")
        delay = max(MIN_DELAY, delay)
        async with self._command_lock:
            for index, (key, argument) in enumerate(parsed * repeats):
                if index:
                    await asyncio.sleep(delay)
                await self._send_key(key, argument)

    async def _send_key(self, key: str, argument: str | None) -> None:
        if not self.available:
            raise HomeAssistantError("Receiver is not connected.")
        if key == "power_on":
            await self.async_turn_on()
        elif key == "power_off":
            await self.async_turn_off()
        elif self.is_on is not True:
            raise HomeAssistantError("Turn on the receiver before sending remote keys.")
        elif key in MEDIA_PLAYER_KEYS:
            player = self._main_player()
            if player is None or not player.enabled:
                raise HomeAssistantError("Enable the receiver's main media player first.")
            if key == "volume_up":
                await player.async_volume_up()
            elif key == "volume_down":
                await player.async_volume_down()
            elif argument is not None:
                await player.async_select_source(argument)
        else:
            code, parameter = KEYS[key]
            await self._manager.write(
                RawInstruction(code, self._menu_keys.get(key, parameter))
            )
