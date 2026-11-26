"""Onkyo receiver."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
import contextlib
from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING

import aioonkyo
from aioonkyo import Instruction, Receiver, ReceiverInfo, Status, connect, query
from aioonkyo.instruction import RawInstruction

from homeassistant.components import network
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DEVICE_DISCOVERY_TIMEOUT, DEVICE_INTERVIEW_TIMEOUT, DOMAIN, ZONES, InputSource
from .source_names import (
    DEVICE_INFO_CODE,
    HDMI_ASSIGNMENT_CODE,
    HDMI_ASSIGNMENT_QUERY,
    parse_hdmi_assignments,
    parse_input_names,
)

if TYPE_CHECKING:
    from . import OnkyoConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass
class Callbacks:
    """Receiver callbacks."""

    connect: list[Callable[[bool], Awaitable[None]]] = field(default_factory=list)
    disconnect: list[Callable[[], Awaitable[None]]] = field(default_factory=list)
    update: list[Callable[[Status], Awaitable[None]]] = field(default_factory=list)

    def clear(self) -> None:
        """Clear all callbacks."""
        self.connect.clear()
        self.disconnect.clear()
        self.update.clear()


class ReceiverManager:
    """Receiver manager."""

    hass: HomeAssistant
    entry: OnkyoConfigEntry
    info: ReceiverInfo
    receiver: Receiver | None = None
    connected: bool = False
    callbacks: Callbacks

    _started: asyncio.Event

    def __init__(
        self, hass: HomeAssistant, entry: OnkyoConfigEntry, info: ReceiverInfo
    ) -> None:
        """Init receiver manager."""
        self.hass = hass
        self.entry = entry
        self.info = info
        self.callbacks = Callbacks()
        self._started = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.input_names: dict[InputSource, str] = {}
        self.hdmi_ports: dict[InputSource, int] = {}
        self.presets: dict[int, dict[str, str | int]] = {}

    @property
    def device_info(self) -> DeviceInfo:
        """Identify one physical receiver for every zone and platform."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.info.identifier)},
            manufacturer="Onkyo",
            model=self.info.model_name,
            name=self.info.model_name,
        )

    async def start(self) -> Awaitable[None] | None:
        """Start the receiver manager run.

        Returns `None`, if everything went fine.
        Returns an awaitable with exception set, if something went wrong.
        """
        manager_task = self.entry.async_create_background_task(
            self.hass, self._run(), "run_connection"
        )
        self._task = manager_task
        wait_for_started_task = asyncio.create_task(self._started.wait())
        done, _ = await asyncio.wait(
            (manager_task, wait_for_started_task), return_when=asyncio.FIRST_COMPLETED
        )
        if manager_task in done:
            # Something went wrong, so let's return the manager task,
            # so that it can be awaited to error out
            wait_for_started_task.cancel()
            await asyncio.wait((wait_for_started_task,))
            return manager_task

        return None

    async def _run(self) -> None:
        """Run the connection to the receiver."""
        reconnect = False
        while True:
            try:
                async with connect(self.info, retry=reconnect) as self.receiver:
                    self.connected = True
                    if not reconnect:
                        self._started.set()
                    else:
                        _LOGGER.info("Reconnected: %s", self.info)

                    await self.on_connect(reconnect=reconnect)

                    while message := await self.receiver.read():
                        await self.on_update(message)

            except (OSError, TimeoutError):
                if not self._started.is_set():
                    raise
                _LOGGER.warning("Receiver connection lost; retrying", exc_info=True)
            finally:
                self.connected = False
                _LOGGER.info("Disconnected: %s", self.info)
                await self.on_disconnect()
            reconnect = True
            await asyncio.sleep(2)

    async def on_connect(self, reconnect: bool) -> None:
        """Receiver (re)connected."""

        # Discover what zones are available for the receiver by querying the power.
        # If we get a response for the specific zone, it means it is available.
        for zone in ZONES:
            await self.write(query.Power(zone))

        for callback in self.callbacks.connect:
            await callback(reconnect)

    async def on_disconnect(self) -> None:
        """Receiver disconnected."""
        for callback in tuple(self.callbacks.disconnect):
            try:
                await callback()
            except Exception:
                _LOGGER.exception("Receiver disconnect callback failed")

    async def on_update(self, message: Status) -> None:
        """New message from the receiver."""
        for callback in tuple(self.callbacks.update):
            try:
                await callback(message)
            except Exception:
                _LOGGER.exception("Receiver update callback failed: %r", callback)

    async def write(self, message: Instruction) -> None:
        """Write message to the receiver."""
        if not self.connected or self.receiver is None:
            raise OSError("Receiver is disconnected")
        await self.receiver.write(message)

    async def async_stop(self) -> None:
        """Close and await the old socket task before a reload creates another."""
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        self.connected = False
        self.receiver = None
        self.callbacks.clear()

    def start_unloading(self) -> None:
        """Start unloading."""
        self.callbacks.clear()


async def async_interview(host: str) -> ReceiverInfo:
    """Interview the receiver."""
    async with asyncio.timeout(DEVICE_INTERVIEW_TIMEOUT):
        return await aioonkyo.interview(host)


async def async_read_input_catalog(
    info: ReceiverInfo,
) -> tuple[dict[InputSource, str], dict[InputSource, int]]:
    """Read the real input names and HDMI ports during initial setup."""
    names: dict[InputSource, str] = {}
    ports: dict[InputSource, int] | None = None
    expect_ports = info.model_name.upper() == "TX-NR6050"
    try:
        async with asyncio.timeout(3), connect(info) as receiver:
            await receiver.write(RawInstruction(DEVICE_INFO_CODE, b"QSTN"))
            if expect_ports:
                await receiver.write(RawInstruction(HDMI_ASSIGNMENT_CODE, HDMI_ASSIGNMENT_QUERY))
            while message := await receiver.read():
                match getattr(message, "raw_code", None):
                    case b"NRI":
                        names = parse_input_names(message.parameter)
                    case b"sHI":
                        ports = parse_hdmi_assignments(message.parameter)
                if names and (ports is not None or not expect_ports):
                    break
    except OSError as err:
        _LOGGER.debug("Input catalog was only partially available: %s", err)
    return names, ports or {}


async def async_discover(hass: HomeAssistant) -> Iterable[ReceiverInfo]:
    """Discover receivers."""
    all_infos: dict[str, ReceiverInfo] = {}

    async def collect_infos(address: str) -> None:
        with contextlib.suppress(asyncio.TimeoutError):
            async with asyncio.timeout(DEVICE_DISCOVERY_TIMEOUT):
                async for info in aioonkyo.discover(address):
                    all_infos.setdefault(info.identifier, info)

    broadcast_addrs = await network.async_get_ipv4_broadcast_addresses(hass)
    tasks = [collect_infos(str(address)) for address in broadcast_addrs]

    await asyncio.gather(*tasks)

    return all_infos.values()
