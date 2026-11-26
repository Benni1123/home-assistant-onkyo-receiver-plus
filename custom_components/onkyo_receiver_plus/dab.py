"""Browse the DAB+ services stored in the receiver by stepping its tuner.

The eISCP protocol has no command that returns the scanned DAB service list,
so this module enumerates it once by stepping `TUNUP` and reading `DSN`. The
receiver is muted for that pass and the previous mute state and source are
restored afterwards. The collected list is cached persistently so browsing
and searching never need to step again.
"""

import asyncio
import logging
import re
from urllib.parse import quote, unquote

from aioonkyo import Zone, command, status
from aioonkyo.instruction import RawInstruction

from homeassistant.components.media_player import BrowseMedia, MediaClass
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .const import DOMAIN, InputSource
from .receiver import ReceiverManager
from .source_names import parse_presets

_LOGGER = logging.getLogger(__name__)

DAB = InputSource.DAB
CONTENT_TYPE = "onkyo_dab"
ROOT_ID = "dab"
STORE_VERSION = 1
STEP_PAUSE = 1.0
STEP_TIMEOUT = 2.5
ENUMERATE_DEADLINE = 180
MAX_SERVICES = 256
CTRL_CODES = re.compile(r"[\x00-\x06\x80-\xa0]")
MAIN = Zone.MAIN


def _clean_name(raw: bytes) -> str:
    """Decode a DSN reply, dropping padding and display control codes."""
    return CTRL_CODES.sub("", raw.decode("utf-8", "replace")).strip()


class DabRadio:
    """Enumerate, cache, browse and play the receiver's DAB+ services."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, manager: ReceiverManager
    ) -> None:
        self._hass = hass
        self._manager = manager
        self._store: Store = Store(
            hass, STORE_VERSION, f"{DOMAIN}_{entry_id}_dab_services"
        )
        self._lock = asyncio.Lock()
        self.services: list[str] | None = None
        self.enumerating = False
        self.scan_task = None
        self.scan_status = "idle"
        self.listeners = []

    def _publish(self, value: str) -> None:
        self.scan_status = value
        for listener in tuple(self.listeners):
            listener()

    async def async_start_scan(self) -> None:
        """Run enumeration outside the UI action timeout, reporting progress."""
        if self.scan_task is not None and not self.scan_task.done():
            raise HomeAssistantError("The DAB list is already being read.")
        if not self._manager.connected:
            raise HomeAssistantError("The receiver is disconnected.")

        async def scan():
            try:
                await self.async_enumerate()
                self._publish(f"complete: {len(self.services or [])}")
            except HomeAssistantError as err:
                self._publish(f"error: {err}")
                _LOGGER.warning("DAB enumeration failed: %s", err)
            except asyncio.CancelledError:
                self._publish("cancelled")
                raise

        self._publish("starting")
        self.scan_task = self._manager.entry.async_create_background_task(
            self._hass, scan(), "dab_enumeration"
        )

    async def async_stop(self) -> None:
        if self.scan_task is not None and not self.scan_task.done():
            self.scan_task.cancel()
            await asyncio.gather(self.scan_task, return_exceptions=True)

    async def async_load(self) -> None:
        """Load the cached service list."""
        if (data := await self._store.async_load()) and isinstance(
            data.get("services"), list
        ):
            self.services = [str(name) for name in data["services"] if name]

    async def _request(
        self, message, matches, timeout: float = STEP_TIMEOUT
    ):
        if not self._manager.connected:
            raise HomeAssistantError("The receiver is not connected.")
        future = asyncio.get_running_loop().create_future()
        self._manager.callbacks.update.append(_pending := _Pending(matches, future))
        try:
            await self._manager.write(message)
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as err:
            raise HomeAssistantError("The receiver did not answer in time.") from err
        finally:
            _pending.remove(self._manager)

    async def _write(self, code: bytes, parameter: bytes) -> bytes | None:
        """Send one raw command and return its raw reply parameter, if any."""

        def matches(message) -> bool:
            return isinstance(message, status.Raw) and message.raw_code == code

        reply = await self._request(RawInstruction(code, parameter), matches)
        assert isinstance(reply, status.Raw)
        return reply.parameter

    async def _current_source(self) -> InputSource | None:
        def matches(message) -> bool:
            return isinstance(message, status.InputSource) and message.zone is MAIN

        reply = await self._request(RawInstruction(b"SLI", b"QSTN"), matches)
        assert isinstance(reply, status.InputSource)
        return reply.param

    async def _set_source(self, source: InputSource) -> None:
        def matches(message) -> bool:
            return (
                isinstance(message, status.InputSource)
                and message.zone is MAIN and message.param == source
            )

        await self._request(command.InputSource(MAIN, source), matches)

    async def _muted(self) -> bool:
        def matches(message) -> bool:
            if isinstance(message, status.Muting):
                return message.zone is MAIN
            return (isinstance(message, status.Raw) and message.raw_code == b"AMT"
                    and message.parameter in (b"00", b"01"))

        reply = await self._request(RawInstruction(b"AMT", b"QSTN"), matches)
        if isinstance(reply, status.Muting):
            return reply.param is status.Muting.Param.ON
        assert isinstance(reply, status.Raw)
        return reply.parameter == b"01"

    async def _set_muted(self, muted: bool) -> None:
        def matches(message) -> bool:
            if isinstance(message, status.Muting):
                return message.zone is MAIN and (
                    message.param is status.Muting.Param.ON
                ) is muted
            return (isinstance(message, status.Raw) and message.raw_code == b"AMT"
                    and message.parameter == (b"01" if muted else b"00"))

        await self._request(
            command.Muting(MAIN, command.Muting.Param.ON if muted else command.Muting.Param.OFF),
            matches,
        )

    async def _step(self, direction: bytes = b"UP") -> str:
        """Advance one DAB service and return its full reported name."""
        if direction not in (b"UP", b"DOWN"):
            raise ValueError("Invalid tuner direction")
        await self._manager.write(RawInstruction(b"TUN", direction))
        await asyncio.sleep(STEP_PAUSE)
        for _attempt in range(3):
            try:
                name = _clean_name(await self._write(b"DSN", b"QSTN") or b"")
                if name:
                    return name
            except HomeAssistantError:
                pass
            await asyncio.sleep(STEP_PAUSE)
        raise HomeAssistantError("The receiver did not report the DAB service name.")

    async def _current_name(self) -> str:
        name = _clean_name(await self._write(b"DSN", b"QSTN") or b"")
        if not name:
            raise HomeAssistantError("The receiver reported no DAB service name.")
        return name

    async def async_enumerate(self, deadline: float = ENUMERATE_DEADLINE) -> list[str]:
        """Step through all services once, muted, and cache the names."""
        async with self._lock:
            self.enumerating = True
            previous_source: InputSource | None = None
            previous_muted: bool | None = None
            collected: list[str] = []
            complete = False
            try:
                previous_source = await self._current_source()
                previous_muted = await self._muted()
                if not previous_muted:
                    await self._set_muted(True)
                if previous_source != DAB:
                    await self._set_source(DAB)
                    await asyncio.sleep(STEP_PAUSE)
                collected.append(await self._current_name())
                self._publish("reading: 1")
                loop = asyncio.get_running_loop()
                stop_at = loop.time() + deadline
                while len(collected) < MAX_SERVICES and loop.time() < stop_at:
                    name = await self._step()
                    if name == collected[0]:
                        _LOGGER.debug("DAB enumeration wrapped after %s", len(collected))
                        complete = True
                        break
                    if name not in collected:
                        collected.append(name)
                        self._publish(f"reading: {len(collected)}")
            except (HomeAssistantError, OSError) as err:
                raise HomeAssistantError(f"DAB list could not be read: {err}") from err
            finally:
                self.enumerating = False
                try:
                    if previous_source is not None and previous_source != DAB:
                        await self._set_source(previous_source)
                except (HomeAssistantError, OSError) as err:
                    _LOGGER.error("Could not restore source: %s", err)
                try:
                    # Restore mute independently of source restoration.
                    if previous_muted is False:
                        await self._set_muted(False)
                except (HomeAssistantError, OSError) as err:
                    _LOGGER.error("Could not restore mute state: %s", err)
            # Replace the cache on a complete pass, or when nothing (better)
            # was cached before. Partial runs keep a longer existing list.
            if not complete:
                raise HomeAssistantError("DAB enumeration did not finish; previous list kept.")
            if collected:
                self.services = collected
                await self._store.async_save({"services": collected})
            return self.services or []

    async def _ensure_dab(self) -> None:
        if await self._current_source() != DAB:
            await self._set_source(DAB)

    def _label(self, english: str, german: str) -> str:
        language = getattr(getattr(self._hass, "config", None), "language", "en")
        return german if language.startswith("de") else english

    async def _preset_items(self) -> list[BrowseMedia]:
        """Read actual hardware presets; never enumerate or modify stations."""
        reply = await self._request(
            RawInstruction(b"NRI", b"QSTN"),
            lambda msg: isinstance(msg, status.Raw) and msg.raw_code == b"NRI",
            timeout=6,
        )
        self._manager.presets = parse_presets(reply.parameter)
        return [
            BrowseMedia(
                media_class=MediaClass.MUSIC,
                media_content_id=f"{ROOT_ID}:preset:{number}",
                media_content_type=CONTENT_TYPE,
                title=f"{number:02d}: {preset['name'] or 'DAB'}",
                can_play=True, can_expand=False,
            )
            for number, preset in sorted(self._manager.presets.items())
            if preset.get("band") == "2"
        ]

    async def async_browse(self, value: str = ROOT_ID) -> BrowseMedia:
        """Separate the complete service cache from direct hardware presets."""
        if value in ("", ROOT_ID):
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id=ROOT_ID, media_content_type=CONTENT_TYPE,
                title="DAB+ Radio", can_play=False, can_expand=True, can_search=True,
                children=[
                    BrowseMedia(
                        media_class=MediaClass.DIRECTORY,
                        media_content_id=f"{ROOT_ID}:all", media_content_type=CONTENT_TYPE,
                        title=self._label("All stations", "Alle Sender"),
                        can_play=False, can_expand=True, can_search=True,
                    ),
                    BrowseMedia(
                        media_class=MediaClass.DIRECTORY,
                        media_content_id=f"{ROOT_ID}:presets", media_content_type=CONTENT_TYPE,
                        title="Presets", can_play=False, can_expand=True, can_search=True,
                    ),
                ],
            )
        if value == f"{ROOT_ID}:presets":
            return BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id=value, media_content_type=CONTENT_TYPE,
                title="DAB+ Presets", can_play=False, can_expand=True, can_search=True,
                children=await self._preset_items(),
            )
        if value != f"{ROOT_ID}:all":
            raise HomeAssistantError("Invalid DAB folder.")
        # Enumeration is explicitly started on the device page.
        children = [
            BrowseMedia(
                media_class=MediaClass.MUSIC,
                media_content_id=f"{ROOT_ID}:station:{quote(name, safe='')}",
                media_content_type=CONTENT_TYPE,
                title=name,
                can_play=True,
                can_expand=False,
            )
            for index, name in enumerate(self.services or [])
        ]
        children.append(BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=f"{ROOT_ID}:rescan",
            media_content_type=CONTENT_TYPE,
            title="Rescan services (muted)",
            can_play=True,
            can_expand=False,
        ))
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=f"{ROOT_ID}:all",
            media_content_type=CONTENT_TYPE,
            title=self._label("All DAB stations", "Alle DAB-Sender"),
            can_play=False,
            can_expand=True,
            can_search=True,
            children=children,
        )

    async def async_search(self, words: str, scope: str = ROOT_ID) -> BrowseMedia:
        """Filter the cached service names."""
        needle = words.strip().casefold()
        matches = [
            (index, name)
            for index, name in enumerate(self.services or [])
            if scope != f"{ROOT_ID}:presets" and needle in name.casefold()
        ]
        presets = []
        if scope in (ROOT_ID, "", f"{ROOT_ID}:presets"):
            presets = [
                item for item in await self._preset_items() if needle in item.title.casefold()
            ]
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=ROOT_ID,
            media_content_type=CONTENT_TYPE,
            title=f"DAB+: {words}",
            can_play=False,
            can_expand=True,
            children=presets + [
                BrowseMedia(
                    media_class=MediaClass.MUSIC,
                    media_content_id=f"{ROOT_ID}:station:{quote(name, safe='')}",
                    media_content_type=CONTENT_TYPE,
                    title=name,
                    can_play=True,
                    can_expand=False,
                )
                for index, name in matches
            ],
        )

    async def async_play(self, value: str) -> None:
        """Play a cached service by stepping to it, verified by name."""
        if value == "rescan":
            await self.async_start_scan()
            return
        if value.startswith("preset:"):
            try:
                number = int(value.removeprefix("preset:"))
            except ValueError as err:
                raise HomeAssistantError("Invalid DAB preset.") from err
            if not 1 <= number <= 40:
                raise HomeAssistantError("Invalid DAB preset.")
            async with self._lock:
                # A stored slot may have been replaced by an FM/AM preset.
                await self._preset_items()
                preset = self._manager.presets.get(number)
                if preset is None or preset.get("band") != "2":
                    raise HomeAssistantError("This slot is not a stored DAB preset. Refresh the list.")
                await self._ensure_dab()
                await self._manager.write(command.TunerPreset(MAIN, number))
                # The AVR may omit an unsolicited echo when this preset was
                # already selected. Explicitly query the actual selection.
                await self._request(
                    RawInstruction(b"PRS", b"QSTN"),
                    lambda msg: isinstance(msg, status.TunerPreset)
                    and msg.zone is MAIN and msg.param == number,
                    timeout=6,
                )
                await self._manager.write(RawInstruction(b"DSN", b"QSTN"))
            return
        if value.startswith("station:"):
            name = unquote(value.removeprefix("station:"))
            index = next((i for i, item in enumerate(self.services or []) if item == name), -1)
        else:
            try:
                index = int(value)
            except ValueError as err:
                raise HomeAssistantError("Invalid DAB service.") from err
        if not self.services or not 0 <= index < len(self.services):
            raise HomeAssistantError("This DAB service is not in the cached list.")
        target = self.services[index]
        async with self._lock:
            previous_muted = await self._muted()
            try:
                await self._set_muted(True)
                await self._ensure_dab()
                current = await self._current_name()
                for _ in range(len(self.services) + 1):
                    if current == target:
                        return
                    direction = b"UP"
                    if current in self.services:
                        current_index = self.services.index(current)
                        forward = (index - current_index) % len(self.services)
                        backward = (current_index - index) % len(self.services)
                        if backward < forward:
                            direction = b"DOWN"
                    current = await self._step(direction)
            finally:
                await self._set_muted(previous_muted)
            raise HomeAssistantError("Could not reach the requested DAB service.")


class _Pending:
    """Register one awaitable match against the receiver's update stream."""

    def __init__(self, matches, future) -> None:
        self._matches = matches
        self._future = future

    async def __call__(self, message) -> None:
        if not self._future.done() and self._matches(message):
            self._future.set_result(message)

    def remove(self, manager: ReceiverManager) -> None:
        try:
            manager.callbacks.update.remove(self)
        except ValueError:
            pass
