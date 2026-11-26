"""Test the DAB service enumeration without touching a receiver."""

from types import SimpleNamespace
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from aioonkyo import Code, Zone, command, status
from aioonkyo.instruction import RawInstruction
from homeassistant.exceptions import HomeAssistantError

from custom_components.onkyo_receiver_plus.const import InputSource
from custom_components.onkyo_receiver_plus.dab import DabRadio


class FakeStore:
    """In-memory stand-in for hass Store."""

    def __init__(self, hass, version, name):
        self.data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data


def is_raw(code):
    return lambda message: (
        isinstance(message, RawInstruction) and message.raw_code == code
    )


def is_command(kind):
    return lambda message: isinstance(message, kind)


def make_manager(replies, dsn_names):
    """Receiver stub: matcher replies plus a queue of DSN names.

    An answer may be a callable receiving the written message, so commands
    can be echoed like the real receiver does.
    """
    pending_names = list(dsn_names)

    async def write(message):
        manager.writes.append(message)
        if is_raw(b"DSN")(message):
            answer = status.Raw(b"DSN", f"{pending_names.pop(0):<15}".encode())
        else:
            for matcher, candidate in replies:
                if matcher(message):
                    answer = candidate(message) if callable(candidate) else candidate
                    break
            else:
                return
        for callback in list(manager.callbacks.update):
            await callback(answer)

    manager = SimpleNamespace(
        connected=True,
        write=write,
        writes=[],
        callbacks=SimpleNamespace(update=[], disconnect=[]),
    )
    return manager


def enumeration_replies():
    """Answers for source, mute and tuner-step commands."""
    return [
        (
            is_command(command.Muting),
            lambda message: status.Muting(Code.AMT, message.param.value.encode(), message.param),
        ),
        (
            is_command(command.InputSource),
            lambda message: status.InputSource(
                Code.SLI,
                b"33" if message.param == InputSource.DAB else b"2B",
                message.param,
            ),
        ),
        (is_raw(b"TUN"), status.Raw(b"TUN", b"00000")),
        (is_raw(b"AMT"), status.Raw(b"AMT", b"00")),
        (
            is_raw(b"SLI"),
            status.InputSource(Code.SLI, b"2B", InputSource.NETWORK),
        ),
    ]


class DabRadioTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        store_patcher = patch(
            "custom_components.onkyo_receiver_plus.dab.Store", FakeStore
        )
        store_patcher.start()
        self.addCleanup(store_patcher.stop)
        pause_patcher = patch(
            "custom_components.onkyo_receiver_plus.dab.STEP_PAUSE", 0
        )
        pause_patcher.start()
        self.addCleanup(pause_patcher.stop)

    def make_radio(self, dsn_names):
        radio = DabRadio(None, "entry", make_manager(enumeration_replies(), dsn_names))
        return radio

    async def test_enumerate_mutes_steps_and_restores(self):
        radio = self.make_radio(["Beta", "Gamma", "Alpha", "Beta"])
        services = await radio.async_enumerate()
        # The current service is read first, then the tuner steps.
        self.assertEqual(services, ["Beta", "Gamma", "Alpha"])
        manager = radio._manager
        # Muted before switching, source restored, mute restored.
        self.assertIn(
            command.Muting(Zone.MAIN, command.Muting.Param.ON), manager.writes
        )
        self.assertIn(
            command.InputSource(Zone.MAIN, InputSource.DAB), manager.writes
        )
        self.assertIn(
            command.InputSource(Zone.MAIN, InputSource.NETWORK), manager.writes
        )
        self.assertIn(
            command.Muting(Zone.MAIN, command.Muting.Param.OFF), manager.writes
        )
        # The list was cached.
        self.assertEqual(radio._store.data, {"services": ["Beta", "Gamma", "Alpha"]})
        self.assertFalse(radio.enumerating)

    async def test_browse_uses_cache_without_stepping(self):
        radio = self.make_radio([])
        radio.services = ["Alpha", "Beta"]
        root = await radio.async_browse("dab:all")
        self.assertEqual(
            [child.title for child in root.children],
            ["Alpha", "Beta", "Rescan services (muted)"],
        )
        self.assertEqual(radio._manager.writes, [])
        self.assertTrue(root.children[0].can_play)

    async def test_empty_browse_offers_explicit_read_without_tuning(self):
        radio = self.make_radio(["Only One", "Only One"])
        root = await radio.async_browse("dab:all")
        self.assertEqual(
            [child.title for child in root.children],
            ["Rescan services (muted)"],
        )
        self.assertEqual(radio._manager.writes, [])

    async def test_search_filters_cached_names(self):
        radio = self.make_radio([])
        radio.services = ["radio SAW", "MDR JUMP", "SAW MD"]
        found = await radio.async_search("saw", "dab:all")
        self.assertEqual(
            [child.title for child in found.children], ["radio SAW", "SAW MD"]
        )

    async def test_play_steps_until_name_matches(self):
        radio = self.make_radio(["Gamma", "Beta"])
        radio.services = ["Alpha", "Beta", "Gamma"]
        await radio.async_play("1")
        manager = radio._manager
        # Selecting a service also steps silently.
        self.assertIn(
            command.Muting(Zone.MAIN, command.Muting.Param.ON), manager.writes
        )
        self.assertIn(RawInstruction(b"TUN", b"DOWN"), manager.writes)
        self.assertEqual(sum(
            isinstance(message, RawInstruction) and message.raw_code == b"TUN"
            for message in manager.writes
        ), 1)

    async def test_play_uses_forward_when_shorter_without_enumerating(self):
        radio = self.make_radio(["Alpha", "Beta"])
        radio.services = ["Alpha", "Beta", "Gamma"]
        radio.async_enumerate = AsyncMock(side_effect=AssertionError("Must not scan"))
        await radio.async_play("station:Beta")
        self.assertIn(RawInstruction(b"TUN", b"UP"), radio._manager.writes)
        self.assertNotIn(RawInstruction(b"TUN", b"DOWN"), radio._manager.writes)
        radio.async_enumerate.assert_not_awaited()

    async def test_play_rejects_unknown_service(self):
        radio = self.make_radio([])
        radio.services = ["Alpha"]
        with self.assertRaises(HomeAssistantError):
            await radio.async_play("3")
        with self.assertRaises(HomeAssistantError):
            await radio.async_play("rescan-is-not-an-index" if False else "xyz")

    async def test_root_has_all_stations_and_presets_without_network_requests(self):
        radio = self.make_radio([])
        root = await radio.async_browse()
        self.assertEqual([c.media_content_id for c in root.children], ["dab:all", "dab:presets"])
        self.assertEqual(radio._manager.writes, [])

    def make_preset_radio(self):
        nri = (
            b'<response status="ok"><device><presetlist>'
            b'<preset id="0e" band="2" freq="0" name="SPUTNIK   "/>'
            b'<preset id="0f" band="0" freq="8900" name="FM station"/>'
            b'<preset id="14" band="0" freq="0" name=""/>'
            b'</presetlist></device></response>'
        )
        replies = [
            (is_raw(b"NRI"), status.Raw(b"NRI", nri)),
            (is_command(command.TunerPreset), status.TunerPreset(Code.PRS, b"0E", 14)),
            (is_raw(b"PRS"), status.TunerPreset(Code.PRS, b"0E", 14)),
            *enumeration_replies(),
        ]
        return DabRadio(None, "entry", make_manager(replies, ["SPUTNIK"]))

    async def test_presets_read_hex_slot_and_filter_other_bands(self):
        radio = self.make_preset_radio()
        root = await radio.async_browse("dab:presets")
        self.assertEqual([c.title for c in root.children], ["14: SPUTNIK"])
        self.assertEqual(root.children[0].media_content_id, "dab:preset:14")
        found = await radio.async_search("sputnik", "dab:presets")
        self.assertEqual([c.title for c in found.children], ["14: SPUTNIK"])

    async def test_preset_14_is_selected_directly_without_steps_or_mute(self):
        radio = self.make_preset_radio()
        radio.async_enumerate = AsyncMock(side_effect=AssertionError("No scan"))
        await radio.async_play("preset:14")
        self.assertIn(command.TunerPreset(Zone.MAIN, 14), radio._manager.writes)
        self.assertFalse(any(
            isinstance(message, command.Muting)
            or (isinstance(message, RawInstruction) and message.raw_code == b"TUN")
            for message in radio._manager.writes
        ))
        radio.async_enumerate.assert_not_awaited()

    async def test_fm_slot_cannot_be_selected_as_dab_preset(self):
        radio = self.make_preset_radio()
        with self.assertRaisesRegex(HomeAssistantError, "not a stored DAB preset"):
            await radio.async_play("preset:15")
        self.assertFalse(any(
            isinstance(message, command.TunerPreset) for message in radio._manager.writes
        ))

    async def test_failed_mute_never_steps_and_reports_actual_error(self):
        radio = self.make_radio(["Alpha"])
        radio._set_muted = AsyncMock(side_effect=HomeAssistantError("mute not confirmed"))
        with self.assertRaisesRegex(HomeAssistantError, "mute not confirmed"):
            await radio.async_enumerate()
        self.assertNotIn(RawInstruction(b"TUN", b"UP"), radio._manager.writes)
        self.assertFalse(radio.enumerating)

    async def test_aborted_read_keeps_previous_cache_and_restores_mute(self):
        radio = self.make_radio(["Alpha"])
        radio.services = ["Old station"]
        radio._step = AsyncMock(side_effect=HomeAssistantError("connection lost"))
        with self.assertRaisesRegex(HomeAssistantError, "connection lost"):
            await radio.async_enumerate()
        self.assertEqual(radio.services, ["Old station"])
        self.assertIn(
            command.Muting(Zone.MAIN, command.Muting.Param.OFF), radio._manager.writes
        )

    async def test_play_rescan_reenumerates(self):
        radio = self.make_radio(["Neu", "Neu"])
        radio.services = ["Alt"]
        radio._manager.entry = SimpleNamespace(
            async_create_background_task=lambda _hass, coro, _name: asyncio.create_task(coro)
        )
        await radio.async_play("rescan")
        await radio.scan_task
        self.assertEqual(radio.services, ["Neu"])
