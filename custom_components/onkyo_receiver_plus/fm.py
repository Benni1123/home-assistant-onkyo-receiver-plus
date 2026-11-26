"""A Home Assistant maintained FM station book.

The receiver only offers 40 shared tuner presets and does not expose them
reliably over eISCP, so this module keeps an independent, persistent list of
FM stations with user-chosen names. Playing an entry selects the FM input and
tunes the stored frequency; the receiver's own presets are not modified.
"""

import asyncio
import logging
from urllib.parse import quote, unquote

from aioonkyo import Zone, command, status
from aioonkyo.instruction import RawInstruction

from homeassistant.components.media_player import BrowseMedia, MediaClass
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store

from .const import DOMAIN, InputSource
from .receiver import ReceiverManager

_LOGGER = logging.getLogger(__name__)

FM = InputSource.FM
CONTENT_TYPE = "onkyo_fm"
ROOT_ID = "fm"
STORE_VERSION = 1
MIN_FREQUENCY = 87.5
MAX_FREQUENCY = 108.0
FREQUENCY_STEP = 0.05
MAX_STATIONS = 60
MAX_NAME_LENGTH = 64
TUNE_CONFIRM_TIMEOUT = 5
MAIN = Zone.MAIN


def normalize_frequency(frequency: float) -> float:
    """Validate and snap an FM frequency to the 50 kHz grid."""
    if not MIN_FREQUENCY <= frequency <= MAX_FREQUENCY:
        raise ServiceValidationError(
            f"FM frequency must be between {MIN_FREQUENCY} and {MAX_FREQUENCY} MHz."
        )
    return round(round(frequency / FREQUENCY_STEP) * FREQUENCY_STEP, 2)


class FmStations:
    """Persistent FM station book with browsing and direct tuning."""

    def __init__(
        self, hass: HomeAssistant, entry_id: str, manager: ReceiverManager
    ) -> None:
        self._hass = hass
        self._manager = manager
        self._store: Store = Store(
            hass, STORE_VERSION, f"{DOMAIN}_{entry_id}_fm_stations"
        )
        self.stations: list[dict[str, str | float]] = []
        self.edit_name = ""
        self.edit_frequency = 89.0
        self.listeners = []
        self._play_lock = asyncio.Lock()

    def notify(self) -> None:
        """Refresh device controls after station-book changes."""
        for listener in tuple(self.listeners):
            listener()

    async def async_load(self) -> None:
        """Load the saved stations."""
        if (data := await self._store.async_load()) and isinstance(
            data.get("stations"), list
        ):
            self.stations = [
                entry
                for entry in data["stations"]
                if isinstance(entry, dict)
                and isinstance(entry.get("name"), str)
                and isinstance(entry.get("freq"), (int, float))
            ]

    async def async_save_station(self, name: str, frequency: float) -> None:
        """Add or replace a station; the name is the unique key."""
        clean = name.strip()
        if not clean or len(clean) > MAX_NAME_LENGTH:
            raise ServiceValidationError(
                f"Station name must be 1 to {MAX_NAME_LENGTH} characters."
            )
        freq = normalize_frequency(frequency)
        for entry in self.stations:
            if str(entry["name"]).casefold() == clean.casefold():
                entry["freq"] = freq
                break
        else:
            if len(self.stations) >= MAX_STATIONS:
                raise ServiceValidationError(
                    f"At most {MAX_STATIONS} FM stations are supported."
                )
            self.stations.append({"name": clean, "freq": freq})
        await self._store.async_save({"stations": self.stations})
        self.notify()

    async def async_delete_station(self, name: str) -> None:
        """Remove a station by name."""
        clean = name.strip().casefold()
        for index, entry in enumerate(self.stations):
            if str(entry["name"]).casefold() == clean:
                self.stations.pop(index)
                await self._store.async_save({"stations": self.stations})
                self.notify()
                return
        raise ServiceValidationError(f"No FM station named {name!r} is saved.")

    async def _write(self, message, matches, timeout: float = 3):
        if not self._manager.connected:
            raise HomeAssistantError("The receiver is not connected.")
        future = asyncio.get_running_loop().create_future()

        async def callback(incoming) -> None:
            if not future.done() and matches(incoming):
                future.set_result(incoming)

        self._manager.callbacks.update.append(callback)
        try:
            await self._manager.write(message)
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as err:
            raise HomeAssistantError("The receiver did not answer in time.") from err
        finally:
            try:
                self._manager.callbacks.update.remove(callback)
            except ValueError:
                pass

    async def _ensure_fm(self) -> None:
        def source_matches(message) -> bool:
            return (
                isinstance(message, status.InputSource)
                and message.zone is MAIN and message.param == FM
            )

        reply = await self._write(
            RawInstruction(b"SLI", b"QSTN"),
            lambda message: (
                isinstance(message, status.InputSource) and message.zone is MAIN
            ),
        )
        assert isinstance(reply, status.InputSource)
        if reply.param != FM:
            await self._write(command.InputSource(MAIN, FM), source_matches)

    async def async_play(self, index: int | str) -> None:
        """Tune a saved station; the frequency is verified afterwards."""
        if isinstance(index, str):
            name = unquote(index.removeprefix("station:"))
            index = next(
                (i for i, station in enumerate(self.stations) if station["name"] == name), -1
            )
        if not 0 <= index < len(self.stations):
            raise HomeAssistantError("This FM station is not saved anymore.")
        entry = self.stations[index]
        target = float(entry["freq"])
        expected = round(target * 100)
        async with self._play_lock:
            await self._ensure_fm()
            # Source switching and parallel status queries may still report the
            # old frequency. Only the requested frequency confirms this tune.
            last_frequency = None

            def tuned(message):
                nonlocal last_frequency
                if not isinstance(message, status.Raw) or message.raw_code != b"TUN":
                    return False
                if not message.parameter.isdigit():
                    return False
                last_frequency = int(message.parameter)
                return last_frequency == expected

            try:
                await self._write(
                    RawInstruction(b"TUN", f"{expected:05d}".encode()),
                    tuned,
                    timeout=TUNE_CONFIRM_TIMEOUT,
                )
            except HomeAssistantError as err:
                detail = (
                    f" Last reported frequency: {last_frequency / 100:g} MHz."
                    if last_frequency is not None else ""
                )
                raise HomeAssistantError(
                    f"The receiver did not confirm FM {target:g} MHz.{detail}"
                ) from err

    async def async_browse(self) -> BrowseMedia:
        """List the saved stations."""
        children = [
            BrowseMedia(
                media_class=MediaClass.MUSIC,
                media_content_id=f"{ROOT_ID}:station:{quote(str(entry['name']), safe='')}",
                media_content_type=CONTENT_TYPE,
                title=f"{entry['name']} ({float(entry['freq']):g} MHz)",
                can_play=True,
                can_expand=False,
            )
            for index, entry in enumerate(self.stations)
        ]
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=ROOT_ID,
            media_content_type=CONTENT_TYPE,
            title="FM Radio (own list)",
            can_play=False,
            can_expand=True,
            can_search=bool(children),
            children=children,
        )

    async def async_search(self, words: str) -> BrowseMedia:
        """Filter saved stations by name."""
        needle = words.strip().casefold()
        matches = [
            (index, entry)
            for index, entry in enumerate(self.stations)
            if needle in str(entry["name"]).casefold()
        ]
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=ROOT_ID,
            media_content_type=CONTENT_TYPE,
            title=f"FM: {words}",
            can_play=False,
            can_expand=True,
            children=[
                BrowseMedia(
                    media_class=MediaClass.MUSIC,
                    media_content_id=f"{ROOT_ID}:station:{quote(str(entry['name']), safe='')}",
                    media_content_type=CONTENT_TYPE,
                    title=f"{entry['name']} ({float(entry['freq']):g} MHz)",
                    can_play=True,
                    can_expand=False,
                )
                for index, entry in matches
            ],
        )
