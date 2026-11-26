"""Test the FM station book without touching a receiver."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aioonkyo import Code, Zone, command, status
from aioonkyo.instruction import RawInstruction
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.onkyo_receiver_plus.const import InputSource
from custom_components.onkyo_receiver_plus.fm import FmStations, normalize_frequency
from custom_components.onkyo_receiver_plus.media_player import (
    DATA_MP_ENTITIES,
    DATA_RADIO,
)
from custom_components.onkyo_receiver_plus.services import (
    _async_delete_fm_station,
    _async_save_fm_station,
)


class FakeStore:
    """In-memory stand-in for hass Store."""

    def __init__(self, hass, version, name):
        self.data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data


def make_manager(replies):
    """Manager whose write() answers from a matcher table and records writes."""

    async def write(message):
        manager.writes.append(message)
        for matcher, answer in replies:
            if matcher(message):
                for callback in list(manager.callbacks.update):
                    await callback(answer)
                return

    manager = SimpleNamespace(
        connected=True,
        write=write,
        writes=[],
        callbacks=SimpleNamespace(update=[], disconnect=[]),
    )
    return manager


def is_raw(code):
    return lambda message: (
        isinstance(message, RawInstruction) and message.raw_code == code
    )


def is_command(kind):
    return lambda message: isinstance(message, kind)


class FmStationsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        patcher = patch("custom_components.onkyo_receiver_plus.fm.Store", FakeStore)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_normalize_frequency_snaps_to_grid(self):
        self.assertEqual(normalize_frequency(94.449), 94.45)
        self.assertEqual(normalize_frequency(94.472), 94.45)
        self.assertEqual(normalize_frequency(87.5), 87.5)
        self.assertEqual(normalize_frequency(108.0), 108.0)
        for bad in (87.4, 108.1, 0):
            with self.assertRaises(ServiceValidationError):
                normalize_frequency(bad)

    async def test_save_replaces_by_name_and_persists(self):
        fm = FmStations(None, "entry", SimpleNamespace())
        await fm.async_save_station("  hr3 ", 94.449)
        await fm.async_save_station("hr3", 91.2)
        await fm.async_save_station("radio SAW", 89.0)
        self.assertEqual(
            fm.stations,
            [{"name": "hr3", "freq": 91.2}, {"name": "radio SAW", "freq": 89.0}],
        )
        with self.assertRaises(ServiceValidationError):
            await fm.async_save_station("   ", 90.0)
        with self.assertRaises(ServiceValidationError):
            await fm.async_save_station("x" * 65, 90.0)

    async def test_delete_requires_existing_name(self):
        fm = FmStations(None, "entry", SimpleNamespace())
        await fm.async_save_station("hr3", 91.2)
        await fm.async_delete_station("HR3 ")
        self.assertEqual(fm.stations, [])
        with self.assertRaises(ServiceValidationError):
            await fm.async_delete_station("hr3")

    async def test_play_switches_to_fm_and_verifies_tuning(self):
        fm = FmStations(None, "entry", make_manager([
            (is_command(command.InputSource), status.InputSource(Code.SLI, b"24", InputSource.FM)),
            (is_raw(b"TUN"), status.Raw(b"TUN", b"09445")),
            (is_raw(b"SLI"), status.InputSource(Code.SLI, b"2B", InputSource.NETWORK)),
        ]))
        manager = fm._manager
        await fm.async_save_station("radio SAW", 94.45)
        await fm.async_play(0)
        self.assertIn(command.InputSource(Zone.MAIN, InputSource.FM), manager.writes)
        self.assertIn(
            RawInstruction(b"TUN", b"09445"),
            manager.writes,
        )
        self.assertEqual(manager.writes[-1].raw_code, b"TUN")

    async def test_play_reports_wrong_frequency(self):
        fm = FmStations(None, "entry", make_manager([
            (is_command(command.InputSource), status.InputSource(Code.SLI, b"24", InputSource.FM)),
            (is_raw(b"TUN"), status.Raw(b"TUN", b"08900")),
            (is_raw(b"SLI"), status.InputSource(Code.SLI, b"2B", InputSource.NETWORK)),
        ]))
        await fm.async_save_station("hr3", 94.45)
        with patch("custom_components.onkyo_receiver_plus.fm.TUNE_CONFIRM_TIMEOUT", 0.02):
            with self.assertRaisesRegex(HomeAssistantError, "Last reported frequency: 89 MHz"):
                await fm.async_play(0)

    async def test_stale_frequency_before_correct_confirmation_is_ignored(self):
        manager = make_manager([
            (is_raw(b"SLI"), status.InputSource(Code.SLI, b"24", InputSource.FM)),
        ])
        original_write = manager.write

        async def write(message):
            if is_raw(b"TUN")(message):
                for frequency in (b"10140", b"N/A", b"08900"):
                    for callback in tuple(manager.callbacks.update):
                        await callback(status.Raw(b"TUN", frequency))
            else:
                await original_write(message)

        manager.write = write
        fm = FmStations(None, "entry", manager)
        await fm.async_save_station("89.0 RTL", 89)
        await fm.async_play(0)
        self.assertEqual(manager.callbacks.update, [])

    async def test_play_rejects_unknown_index(self):
        fm = FmStations(None, "entry", SimpleNamespace())
        await fm.async_save_station("hr3", 94.45)
        with self.assertRaises(HomeAssistantError):
            await fm.async_play(5)

    async def test_browse_and_search(self):
        fm = FmStations(None, "entry", SimpleNamespace())
        await fm.async_save_station("radio SAW", 89.0)
        await fm.async_save_station("hr3", 94.45)
        root = await fm.async_browse()
        self.assertEqual(
            [child.title for child in root.children],
            ["radio SAW (89 MHz)", "hr3 (94.45 MHz)"],
        )
        self.assertTrue(root.children[0].can_play)
        found = await fm.async_search("saw")
        self.assertEqual([child.title for child in found.children], ["radio SAW (89 MHz)"])

    async def test_services_route_to_the_stations_book(self):
        hass = SimpleNamespace(data={})
        hass.data[DATA_MP_ENTITIES] = {
            "entry": {Zone.MAIN: SimpleNamespace(entity_id="media_player.rx")}
        }
        fm = FmStations(None, "entry", SimpleNamespace())
        hass.data[DATA_RADIO] = {"entry": (fm, None)}
        await _async_save_fm_station(
            hass,
            SimpleNamespace(
                data={
                    "entity_id": ["media_player.rx"],
                    "name": "hr3",
                    "frequency": 94.45,
                }
            ),
        )
        self.assertEqual(fm.stations, [{"name": "hr3", "freq": 94.45}])
        await _async_delete_fm_station(
            hass,
            SimpleNamespace(data={"entity_id": ["media_player.rx"], "name": "hr3"}),
        )
        self.assertEqual(fm.stations, [])
