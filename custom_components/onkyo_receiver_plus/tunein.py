"""Browse the TuneIn directory exposed by the receiver's local eISCP session."""

import asyncio
from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
import json
import re
from xml.etree import ElementTree

from aioonkyo import Instruction, Status, Zone, command, status
from aioonkyo.instruction import RawInstruction
from homeassistant.components.media_player import BrowseMedia, MediaClass, SearchMedia
from homeassistant.exceptions import HomeAssistantError

from .const import InputSource
from .receiver import ReceiverManager

CONTENT_TYPE = "onkyo_tunein"
ROOT_ID = "tunein"
NET = InputSource("2B")
NETWORK_PAGE = 25
BROWSE_PAGE = 200
MAX_DEPTH = 16
MAX_XML = 65536
FOLDER_ICONS = {"29", "2b", "3b", "3c"}
PLAYABLE_ICONS = {"2d", "2f", "36", "3f", "41"}
ACCOUNT_ENTRIES = {"login", "log in", "sign in", "logout", "log out", "sign out"}
LIST_MODES = {b"0", b"5"}
ROOT_SEARCH_FOLDERS = {
    "local radio", "lokales radio", "my presets", "meine presets", "meine voreinstellungen",
}


@dataclass(frozen=True)
class View:
    """Receiver list header (NLT)."""

    service: bytes
    mode: bytes
    depth: int
    total: int
    title: str

    @property
    def is_root(self) -> bool:
        return self.service == b"0E" and self.mode in LIST_MODES and self.depth == 1

    @property
    def key(self) -> tuple[bytes, bytes, int, str]:
        return (self.service, self.mode, self.depth, self.title)


@dataclass(frozen=True)
class Item:
    """A row in a specific receiver list."""

    index: int
    title: str
    kind: str


def parse_view(data: bytes) -> View | None:
    """Decode a TuneIn-compatible list header."""
    if len(data) < 22 or not re.fullmatch(rb"[0-9A-Fa-f]{10}", data[4:14]):
        return None
    return View(
        data[:2].upper(),
        data[2:3],
        int(data[12:14], 16),
        int(data[8:12], 16),
        data[22:].decode("utf-8", "replace").strip(),
    )


def parse_items(data: bytes, offset: int, requested: int) -> tuple[Item, ...]:
    """Decode a successful NLA XML page, preserving original row indices."""
    marker = data.find(b"<")
    if len(data) > MAX_XML or not data.startswith(b"S") or marker < 0:
        raise HomeAssistantError("The receiver did not return a valid TuneIn list.")
    payload = data[marker:]
    if b"\0" in payload or b"<!" in payload:
        raise HomeAssistantError("Unsupported TuneIn list format.")
    try:
        xml = ElementTree.fromstring(payload)
        items = xml.find("items")
        if xml.tag != "response" or xml.get("status") != "ok" or items is None:
            raise ValueError
        raw_offset = items.get("offset", f"{offset:X}")
        if (
            (not raw_offset.isdecimal() or int(raw_offset) != offset)
            and int(raw_offset, 16) != offset
        ):
            raise ValueError
        rows = items.findall("item")
        if len(rows) > requested:
            raise ValueError
    except (ElementTree.ParseError, ValueError, LookupError) as err:
        raise HomeAssistantError("The receiver returned an invalid TuneIn page.") from err
    results = []
    for i, row in enumerate(rows, offset):
        title = row.get("title", "").strip()
        icon = row.get("iconid", "").lower()
        item_type = row.get("icontype", "")
        if (
            not title or title.casefold() in ACCOUNT_ENTRIES | {"anmelden", "abmelden"}
            or row.get("selectable") == "0"
        ):
            continue
        if icon in FOLDER_ICONS or item_type == "F":
            results.append(Item(i, title, "folder"))
        elif icon in PLAYABLE_ICONS or item_type == "T":
            results.append(Item(i, title, "station"))
    return tuple(results)


def media_id(path: tuple[Item, ...], offset: int = 0) -> str:
    """Encode a receiver route without including stream URLs or credentials."""
    if not path and not offset:
        return ROOT_ID
    data = json.dumps(
        [offset, [[item.index, item.title, item.kind] for item in path]],
        ensure_ascii=False, separators=(",", ":"),
    ).encode()
    return f"{ROOT_ID}:{urlsafe_b64encode(data).decode().rstrip('=')}"


def parse_media_id(value: str | None) -> tuple[tuple[Item, ...], int]:
    """Validate every part of a route received from Home Assistant."""
    if value in (None, "", ROOT_ID):
        return (), 0
    try:
        if not value.startswith(f"{ROOT_ID}:") or len(value) > 12000:
            raise ValueError
        token = value[len(ROOT_ID) + 1 :]
        if not re.fullmatch(r"[\w-]+", token, re.ASCII):
            raise ValueError
        offset, rows = json.loads(urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        if type(offset) is not int or not 0 <= offset <= 65535:
            raise ValueError
        if not isinstance(rows, list) or len(rows) > MAX_DEPTH:
            raise ValueError
        path = []
        for index, title, kind in rows:
            if (
                type(index) is not int or not 0 <= index < 65535
                or not isinstance(title, str) or not 0 < len(title) <= 512
                or kind not in ("folder", "station")
            ):
                raise ValueError
            path.append(Item(index, title, kind))
    except (ValueError, TypeError, Base64Error, UnicodeError) as err:
        raise HomeAssistantError("Invalid TuneIn media item.") from err
    if any(item.kind != "folder" for item in path[:-1]):
        raise HomeAssistantError("Invalid TuneIn list path.")
    return tuple(path), offset


def media_item(path: tuple[Item, ...], item: Item) -> BrowseMedia:
    folder = item.kind == "folder"
    return BrowseMedia(
        media_class=MediaClass.DIRECTORY if folder else MediaClass.MUSIC,
        media_content_id=media_id((*path, item)),
        media_content_type=CONTENT_TYPE,
        title=item.title,
        can_play=not folder,
        can_expand=folder,
        can_search=folder,
    )


class TuneIn:
    """Serialize stateful directory navigation on the receiver's main zone."""

    def __init__(
        self, manager: ReceiverManager, title_callback: Callable[[str | None], None]
    ) -> None:
        self._manager = manager
        self._title_callback = title_callback
        self._lock = asyncio.Lock()
        self._sequence = count(1)
        self._pending: tuple[Callable[[Status], bool], asyncio.Future[Status]] | None = None
        self._source: InputSource | None = None
        self._view: View | None = None
        self._active: tuple[tuple[Item, ...], tuple[bytes, bytes, int, str]] | None = None
        self._station: str | None = None
        manager.callbacks.update.append(self._receive)
        manager.callbacks.disconnect.append(self._disconnect)

    def _set_title(self, title: str | None) -> None:
        if title != self._station:
            self._station = title
            self._title_callback(title)

    async def _query_title_status(self, code: bytes) -> None:
        """Ask for existing playback metadata without changing the receiver menu."""
        if self._manager.connected:
            try:
                await self._manager.write(RawInstruction(code, b"QSTN"))
            except OSError:
                return  # Normal disconnect handling clears the reported title.

    async def _receive(self, message: Status) -> None:
        metadata_query = None
        if isinstance(message, status.InputSource) and message.zone is Zone.MAIN:
            previous = self._source
            self._source = message.param
            if self._source != NET:
                self._view = self._active = None
                self._set_title(None)
            elif previous != NET:
                metadata_query = (
                    b"NTI" if self._view and self._view.service == b"0E" else b"NLT"
                )
        elif isinstance(message, status.Power) and message.zone is Zone.MAIN:
            if message.param is status.Power.Param.STANDBY:
                self._view = self._active = None
                self._set_title(None)
        elif isinstance(message, status.Raw):
            if message.raw_code == b"NLT":
                previous_view = self._view
                self._view = parse_view(message.parameter)
                if self._view is None or self._view.service != b"0E":
                    self._set_title(None)
                elif self._source == NET and (
                    previous_view is None
                    or previous_view.service != b"0E"
                    or (self._view.mode == b"2" and previous_view.mode != b"2")
                ):
                    metadata_query = b"NTI"
            elif (
                message.raw_code == b"NTI"
                and self._source == NET
                and self._view is not None
                and self._view.service == b"0E"
            ):
                self._set_title(message.parameter.decode("utf-8", "replace").strip() or None)
        if self._pending is not None:
            matches, future = self._pending
            if not future.done() and matches(message):
                future.set_result(message)
        if metadata_query is not None:
            await self._query_title_status(metadata_query)

    async def _disconnect(self) -> None:
        self._source = self._view = self._active = None
        self._set_title(None)
        if self._pending is not None:
            _, future = self._pending
            if not future.done():
                future.set_exception(OSError("Receiver disconnected."))

    async def _request(
        self, message: Instruction, matches: Callable[[Status], bool], timeout: float = 5
    ) -> Status:
        if not self._manager.connected:
            raise HomeAssistantError("The receiver is not connected.")
        future = asyncio.get_running_loop().create_future()
        self._pending = (matches, future)
        try:
            await self._manager.write(message)
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as err:
            raise HomeAssistantError("The receiver did not confirm the TuneIn request.") from err
        except OSError as err:
            raise HomeAssistantError("The receiver disconnected during the TuneIn request.") from err
        finally:
            self._pending = None
            if not future.done():
                future.cancel()

    async def _list_view(
        self,
        instruction: Instruction | None = None,
        validate: Callable[[View], bool] = lambda _view: True,
    ) -> View:
        def matches(message: Status) -> bool:
            return (
                isinstance(message, status.Raw)
                and message.raw_code == b"NLT"
                and (view := parse_view(message.parameter)) is not None
                and validate(view)
            )

        result = await self._request(
            instruction or RawInstruction(b"NLT", b"QSTN"), matches, timeout=8
        )
        assert isinstance(result, status.Raw)
        parsed = parse_view(result.parameter)
        assert parsed is not None
        return parsed

    async def _page(self, view: View, offset: int, length: int) -> tuple[Item, ...]:
        sequence = f"{next(self._sequence) & 0xFFFF:04X}".encode()
        reply_prefix = b"X" + sequence
        parameter = b"L" + sequence + f"{view.depth:02X}{offset:04X}{length:04X}".encode()
        reply = await self._request(
            RawInstruction(b"NLA", parameter),
            lambda msg: isinstance(msg, status.Raw)
            and msg.raw_code == b"NLA" and msg.parameter.startswith(reply_prefix),
        )
        assert isinstance(reply, status.Raw)
        return parse_items(reply.parameter[len(reply_prefix):], offset, length)

    async def _rows(
        self, view: View, offset: int, limit: int
    ) -> tuple[Item, ...]:
        end = min(view.total, offset + limit)
        result = []
        for page in range(offset, end, NETWORK_PAGE):
            result.extend(await self._page(view, page, min(end - page, NETWORK_PAGE)))
        return tuple(result)

    async def _verify_row(self, view: View, item: Item) -> None:
        if item.index >= view.total or item not in await self._page(view, item.index, 1):
            raise HomeAssistantError("The TuneIn list changed. Browse for the item again.")
        if self._source != NET or (self._view and self._view.key != view.key):
            raise HomeAssistantError("The receiver menu changed while browsing TuneIn.")

    @staticmethod
    def _select_row(item: Item) -> RawInstruction:
        # NLA offsets are zero-based; the NLSI selection index is one-based.
        return RawInstruction(b"NLS", f"I{item.index + 1:05d}".encode())

    async def _open(self, path: tuple[Item, ...]) -> View:
        if self._source != NET:
            await self._request(
                command.InputSource(Zone.MAIN, NET),
                lambda msg: isinstance(msg, status.InputSource)
                and msg.zone is Zone.MAIN and msg.param == NET,
            )
        try:
            view = await self._list_view() if self._view is not None else None
        except HomeAssistantError:
            view = None
        current: tuple[Item, ...] = ()
        if (
            view is not None and view.service == b"0E" and view.mode in LIST_MODES
            and self._active is not None
            and self._active[1] == view.key
            and path[: len(self._active[0])] == self._active[0]
        ):
            current = self._active[0]
        elif view is None or not view.is_root:
            view = await self._list_view(
                RawInstruction(b"NSV", b"0E0"), lambda candidate: candidate.is_root
            )
        assert view is not None
        self._active = current, view.key
        for folder in path[len(current):]:
            await self._verify_row(view, folder)
            expected_depth = view.depth + 1
            view = await self._list_view(
                self._select_row(folder),
                lambda candidate: candidate.service == b"0E" and candidate.mode in LIST_MODES
                # NLT titles may differ from the verified NLA row, e.g.
                # "Dance " for "Dance & Electronic". Require the actual
                # child layer instead of waiting for an impossible name.
                and candidate.depth == expected_depth,
            )
            current = (*current, folder)
            self._active = current, view.key
        return view

    @staticmethod
    def root() -> BrowseMedia:
        """Show the TuneIn entry without waking or switching the receiver."""
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id="",
            media_content_type=MediaClass.DIRECTORY,
            title="Onkyo",
            can_play=False,
            can_expand=True,
            children=[BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id=ROOT_ID,
                media_content_type=CONTENT_TYPE,
                title="TuneIn Radio",
                can_play=False,
                can_expand=True,
                can_search=True,
            )],
        )

    async def browse(self, value: str) -> BrowseMedia:
        path, offset = parse_media_id(value)
        if path and path[-1].kind != "folder":
            raise HomeAssistantError("This TuneIn item is not a folder.")
        async with self._lock:
            view = await self._open(path)
            items = await self._rows(view, offset, BROWSE_PAGE)
        children = [media_item(path, item) for item in items]
        if (next_page := offset + BROWSE_PAGE) < view.total:
            children.append(BrowseMedia(
                media_class=MediaClass.DIRECTORY,
                media_content_id=media_id(path, next_page),
                media_content_type=CONTENT_TYPE,
                title=f"More stations ({next_page + 1}–{min(next_page + BROWSE_PAGE, view.total)})",
                can_play=False,
                can_expand=True,
                can_search=True,
            ))
        return BrowseMedia(
            media_class=MediaClass.DIRECTORY,
            media_content_id=media_id(path, offset),
            media_content_type=CONTENT_TYPE,
            title=path[-1].title if path else "TuneIn Radio",
            can_play=False,
            can_expand=True,
            can_search=True,
            children=children,
        )

    async def search(self, value: str | None, words: str) -> SearchMedia:
        path, _ = parse_media_id(value)
        needle = words.strip().casefold()
        if not needle:
            return SearchMedia(result=[])
        if path and path[-1].kind != "folder":
            path = path[:-1]
        results = []
        try:
            async with self._lock, asyncio.timeout(25):
                view = await self._open(path)
                if not path:
                    root_items = await self._rows(view, 0, BROWSE_PAGE)
                    results.extend(media_item(path, item) for item in root_items
                                   if needle in item.title.casefold())
                    for folder in root_items:
                        if len(results) >= 100:
                            break
                        if folder.kind == "folder" and folder.title.casefold() in ROOT_SEARCH_FOLDERS:
                            section = (folder,)
                            await self._search_section(
                                section, await self._open(section), needle, results
                            )
                else:
                    await self._search_section(path, view, needle, results)
        except TimeoutError as err:
            raise HomeAssistantError("Search timed out. Open a narrower TuneIn category.") from err
        return SearchMedia(result=results)

    async def _search_section(
        self, path: tuple[Item, ...], view: View, needle: str, results: list[BrowseMedia]
    ) -> None:
        for offset in range(0, view.total, NETWORK_PAGE):
            for item in await self._page(view, offset, min(NETWORK_PAGE, view.total - offset)):
                if needle in item.title.casefold():
                    results.append(media_item(path, item))
                    if len(results) >= 100:
                        return

    async def play(self, value: str) -> None:
        path, offset = parse_media_id(value)
        if offset or not path or path[-1].kind != "station":
            raise HomeAssistantError("Select a TuneIn station to play.")
        station = path[-1]
        async with self._lock:
            view = await self._open(path[:-1])
            await self._verify_row(view, station)
            self._active = None
            # The receiver can report playback before the new title; the title
            # or playback view may also differ from the menu's genre suffix.
            await self._request(
                self._select_row(station),
                lambda msg: isinstance(msg, status.Raw) and (
                    (
                        msg.raw_code == b"NLT" and msg.parameter[:3] == b"0E2"
                    ) or (
                        msg.raw_code == b"NTI"
                        and msg.parameter.decode("utf-8", "replace").strip().casefold()
                        == station.title.casefold()
                    )
                ),
                timeout=12,
            )
