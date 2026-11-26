"""Replay the TX-NR6050 TuneIn directory protocol without changing a receiver."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from xml.sax.saxutils import quoteattr

from aioonkyo import Code, command, status
from aioonkyo.instruction import RawInstruction
from homeassistant.exceptions import HomeAssistantError

from custom_components.onkyo_receiver_plus.tunein import (
    NET,
    ROOT_ID,
    Item,
    TuneIn,
    media_id,
    parse_items,
    parse_media_id,
)


class TuneInTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.writes = []
        self.menu = "root"
        self.root_rows = [
            ("My Presets", "29", "1"),
            ("Local Radio", "29", "1"),
            ("By Location", "29", "1"),
            ("Login", "29", "1"),
        ]
        self.local_rows = [("Stations", "ff", "0")] + [
            (f"Station {index}", "2d", "1") for index in range(1, 250)
        ]
        self.local_rows[150] = ("Example FM (Local Radio)", "2d", "1")
        self.manager = SimpleNamespace(
            connected=True,
            write=self.write,
            callbacks=SimpleNamespace(update=[], disconnect=[]),
        )
        self.title = Mock()
        self.tunein = TuneIn(self.manager, self.title)

    async def emit(self, code, value):
        await self.tunein._receive(status.Raw(code, value))

    async def list_header(self):
        rows, depth, title = {
            "root": (self.root_rows, 1, "TuneIn Radio"),
            "local": (self.local_rows, 2, "Local Radio"),
            "presets": ([("Example Favorite", "2d", "1")], 2, "My Presets"),
            "location": ([("Europe", "29", "1")], 2, "By Location"),
            "europe": ([("Europe FM", "2d", "1")], 3, "Europe"),
        }[self.menu]
        depth_flag = "1" if depth == 1 else "2"
        await self.emit(
            b"NLT", f"0E0{depth_flag}0000{len(rows):04X}{depth:02X}00FF0E00{title}".encode()
        )
        return rows

    async def write(self, message):
        self.writes.append(message)
        if isinstance(message, command.InputSource):
            await self.tunein._receive(status.InputSource(Code.SLI, b"2B", NET))
            return
        code, arg = message.raw_code, message.parameter
        if code == b"NSV":
            self.assertEqual(arg, b"0E0")
            self.menu = "root"
            await self.list_header()
        elif code == b"NLT":
            await self.list_header()
        elif code == b"NLA":
            rows = await self.list_header()
            offset, size = int(arg[7:11], 16), int(arg[11:15], 16)
            xml = "".join(
                f'<item title={quoteattr(title)} iconid="{icon}" selectable="{selectable}"/>'
                for title, icon, selectable in rows[offset:offset + size]
            )
            await self.emit(
                b"NLA",
                b"X" + arg[1:5] + f'S000<response status="ok"><items offset="{offset}">'
                f"{xml}</items></response>".encode(),
            )
        elif code == b"NLS":
            index = int(arg[1:]) - 1
            if self.menu == "root":
                self.menu = ["presets", "local", "location"][index]
                await self.list_header()
            elif self.menu == "location":
                self.assertEqual(index, 0)
                self.menu = "europe"
                await self.list_header()
            else:
                rows = await self.list_header()
                await self.emit(b"NTI", rows[index][0].encode())
                await self.emit(b"NLT", b"0E22000000000200000E00")

    async def test_browse_paginates_and_can_play_any_row(self):
        root = self.tunein.root()
        self.assertEqual(root.children[0].media_content_id, ROOT_ID)
        self.assertFalse(self.writes)
        services = await self.tunein.browse(ROOT_ID)
        self.assertEqual([node.title for node in services.children], [
            "My Presets", "Local Radio", "By Location",
        ])
        local = services.children[1]
        stations = await self.tunein.browse(local.media_content_id)
        station = next(node for node in stations.children if node.title.startswith("Example FM"))
        next_page = stations.children[-1]
        self.assertTrue(next_page.can_expand)
        more = await self.tunein.browse(next_page.media_content_id)
        self.assertEqual(more.children[0].title, "Station 200")
        await self.tunein.play(station.media_content_id)
        self.assertIn(RawInstruction(b"NLS", b"I00151"), self.writes)
        self.title.assert_called_with("Example FM (Local Radio)")
        self.assertFalse(any(
            isinstance(write, RawInstruction) and write.parameter == b"QSTN"
            and write.raw_code == b"NSV" for write in self.writes
        ))

    async def test_root_search_finds_late_station_and_favorite(self):
        results = await self.tunein.search(ROOT_ID, "example")
        self.assertEqual({item.title for item in results.result}, {
            "Example Favorite", "Example FM (Local Radio)",
        })

    async def test_nested_categories_work(self):
        root = await self.tunein.browse(ROOT_ID)
        location = await self.tunein.browse(root.children[-1].media_content_id)
        europe = await self.tunein.browse(location.children[0].media_content_id)
        self.assertEqual(europe.children[0].title, "Europe FM")
        self.assertTrue(europe.children[0].can_play)

    async def test_folder_header_may_shorten_dance_and_electronic(self):
        self.root_rows[1] = ("Dance & Electronic", "29", "1")
        original_emit = self.emit

        async def emit(code, value):
            if code == b"NLT" and value.endswith(b"Local Radio"):
                value = value[:-len(b"Local Radio")] + b"Dance "
            await original_emit(code, value)

        self.emit = emit
        root = await self.tunein.browse(ROOT_ID)
        folder = root.children[1]
        stations = await self.tunein.browse(folder.media_content_id)
        self.assertEqual(stations.title, "Dance & Electronic")
        station = next(item for item in stations.children if item.can_play)
        await self.tunein.play(station.media_content_id)
        self.assertTrue(any(
            isinstance(message, RawInstruction) and message.raw_code == b"NLS"
            for message in self.writes
        ))

    async def test_receiver_playing_outside_ha_requests_title_without_switching(self):
        async def loaded(message):
            self.writes.append(message)
            if message.raw_code == b"NLT":
                await self.emit(b"NLT", b"0E22000000000200000E00")
            elif message.raw_code == b"NTI":
                await self.emit(b"NTI", b"Existing station")

        self.manager.write = loaded
        await self.tunein._receive(status.InputSource(Code.SLI, b"2B", NET))
        self.assertEqual(self.writes, [
            RawInstruction(b"NLT", b"QSTN"), RawInstruction(b"NTI", b"QSTN"),
        ])
        self.title.assert_called_once_with("Existing station")

    async def test_stale_index_does_not_play_another_station(self):
        root = await self.tunein.browse(ROOT_ID)
        rows = await self.tunein.browse(root.children[1].media_content_id)
        station_id = next(row.media_content_id for row in rows.children if row.title.startswith("Example FM"))
        self.local_rows[150] = ("Different Station", "2d", "1")
        with self.assertRaisesRegex(HomeAssistantError, "list changed"):
            await self.tunein.play(station_id)
        self.assertNotIn(RawInstruction(b"NLS", b"I00151"), self.writes)

    def test_media_id_and_xml_validation(self):
        path = (Item(1, "Überregionale Sender", "folder"),)
        self.assertEqual(parse_media_id(media_id(path, 200)), (path, 200))
        with self.assertRaises(HomeAssistantError):
            parse_media_id("tunein:???")
        with self.assertRaises(HomeAssistantError):
            parse_items(b'S000<!DOCTYPE response><response/>', 0, 1)
