"""Test the new setup labels, device identity and extra controls."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aioonkyo import Code, query, status

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from homeassistant.exceptions import ServiceValidationError

from custom_components.onkyo_receiver_plus.config_flow import receiver_input_selector
from custom_components.onkyo_receiver_plus.const import InputSource
from custom_components.onkyo_receiver_plus.select import OnkyoTunerPresetSelect
from custom_components.onkyo_receiver_plus.util import get_meaning


class TunerPresetSelectTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.extras = SimpleNamespace(
            manager=SimpleNamespace(
                info=SimpleNamespace(identifier="receiver"),
                device_info={"identifiers": {("onkyo_receiver_plus", "receiver")}},
                connected=True,
                presets={
                    1: {"band": "0", "freq": 9830, "name": "hr3"},
                    3: {"band": "2", "freq": 0, "name": "DAB Rock"},
                    5: {"band": "0", "freq": 0, "name": ""},
                },
            ),
            values={"tuner_preset": 3},
            powered=True,
            source=InputSource("24"),
            set=AsyncMock(),
        )
        self.select = OnkyoTunerPresetSelect(self.extras)

    def test_options_use_receiver_names_and_current_preset(self):
        self.assertEqual(self.select.options, ["01: hr3", "03: DAB Rock", "05"])
        self.assertEqual(self.select.current_option, "03: DAB Rock")
        self.assertTrue(self.select.available)

    def test_unavailable_off_tuner(self):
        self.extras.source = InputSource("2B")
        self.assertFalse(self.select.available)

    async def test_select_sends_preset_number(self):
        await self.select.async_select_option("01: hr3")
        self.extras.set.assert_awaited_once_with("tuner_preset", b"01")

    async def test_select_rejects_unknown_option(self):
        with self.assertRaises(ServiceValidationError):
            await self.select.async_select_option("02: not stored")
        self.extras.set.assert_not_awaited()
from custom_components.onkyo_receiver_plus.const import InputSource
from custom_components.onkyo_receiver_plus.diagnostics import async_get_config_entry_diagnostics
from custom_components.onkyo_receiver_plus.extras import (
    ReceiverExtras, integer_parameter, raw_value, speaker_configuration
)
from custom_components.onkyo_receiver_plus.number import OnkyoReceiverNumber, OnkyoSubwooferLevel
from custom_components.onkyo_receiver_plus.receiver import ReceiverManager
from custom_components.onkyo_receiver_plus.select import OnkyoReceiverSelect
from custom_components.onkyo_receiver_plus.sensor import OnkyoReceiverSensor
from custom_components.onkyo_receiver_plus.switch import OnkyoReceiverSwitch
from custom_components.onkyo_receiver_plus.util import get_meaning


class ExtrasTest(unittest.TestCase):
    def test_setup_menu_uses_reported_labels_but_validates_stable_keys(self):
        bd, game, tv = map(InputSource, ("10", "02", "12"))
        selector = receiver_input_selector(
            {game: "GAME", bd: "Google TV"}, {bd: 1, game: 2}, {tv: "Fernseher"}
        )
        self.assertEqual(
            [option["label"] for option in selector.config["options"]],
            ["HDMI 1 / Google TV", "HDMI 2 / GAME", "Fernseher"],
        )
        self.assertEqual(selector([get_meaning(bd)]), [get_meaning(bd)])

    def test_shared_device_across_platforms(self):
        manager = ReceiverManager(
            Mock(), Mock(), SimpleNamespace(identifier="receiver", model_name="TX-NR6050")
        )
        extras = SimpleNamespace(manager=manager)
        for entity in (
            OnkyoSubwooferLevel(manager),
            OnkyoReceiverNumber(extras, "bass", -10, 10, 1, "dB"),
            OnkyoReceiverSelect(extras, "dimmer", {"bright": b"00"}),
            OnkyoReceiverSensor(extras, "audio_signal"),
            OnkyoReceiverSwitch(extras, "music_optimizer"),
        ):
            self.assertEqual(entity.device_info["identifiers"], {("onkyo_receiver_plus", "receiver")})

    def test_setting_values_obey_protocol(self):
        self.assertEqual(integer_parameter("bass", -10, -10, 10, 1), b"B-A")
        self.assertEqual(integer_parameter("treble", 0, -10, 10, 1), b"T00")
        self.assertEqual(integer_parameter("av_sync", 110, 0, 500, 5), b"+110")
        self.assertEqual(integer_parameter("sleep_timer", 0, 0, 90, 1), b"OFF")
        self.assertEqual(integer_parameter("fm_frequency", 103.35, 87.5, 108, .05), b"10335")
        self.assertEqual(raw_value(b"DIM", b"02"), ("dimmer", "dark"))
        self.assertEqual(raw_value(b"AVS", b"0000"), ("av_sync", 0))
        self.assertEqual(raw_value(b"MOT", b"00"), ("music_optimizer", False))
        self.assertIsNone(raw_value(b"VOC", b"N/A"))
        self.assertIsNone(raw_value(b"HAO", b"02"))
        self.assertEqual(raw_value(b"AEQ", b"01"), ("accueq", "all"))
        self.assertEqual(raw_value(b"EQS", b"03"), ("manual_eq", "preset_3"))
        self.assertEqual(raw_value(b"DGF", b"03"), ("digital_filter", "auto"))
        self.assertEqual(raw_value(b"NSB", b"ON"), ("network_standby", True))
        self.assertEqual(raw_value(b"DLC", b"+5"), ("dts_dialog", 5))
        self.assertEqual(integer_parameter("dts_dialog", 5, 0, 6, 1), b"+5")
        with self.assertRaises(ValueError):
            integer_parameter("av_sync", 3, 0, 500, 5)

    def test_speaker_configuration(self):
        label, attrs = speaker_configuration(b"1100000---000")
        self.assertEqual(label, "2.1")
        self.assertEqual(attrs["subwoofers"], 1)
        self.assertNotIn("crossover_hz", attrs)
        label, attrs = speaker_configuration(b"2111100080000")
        self.assertEqual(label, "5.2 + Surround Back")
        self.assertEqual(attrs["crossover_hz"], 80)
        self.assertIsNone(speaker_configuration(b"N/A"))


class DiagnosticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostics_omit_addresses_and_custom_labels(self):
        data = SimpleNamespace(
            manager=SimpleNamespace(
                info=SimpleNamespace(model_name="TX-NR6050", host="PRIVATE-HOST"),
                connected=True,
                hdmi_ports={InputSource("10"): 1},
            ),
            extras=None,
            channel_muting_coordinator=SimpleNamespace(data={}),
        )
        entry = SimpleNamespace(
            runtime_data=data,
            options={
                "input_sources": {"10": "PRIVATE-NAME"},
                "listening_modes": {"00": "PRIVATE-LABEL"},
                "password": "PRIVATE-PASSWORD",
                "volume_mode": "ramp",
            },
        )
        result = await async_get_config_entry_diagnostics(None, entry)
        self.assertNotIn("PRIVATE", str(result))
        self.assertEqual(result["options"]["input_sources"], ["10"])
        self.assertEqual(result["hdmi_ports"], {"10": 1})

    async def test_temperature_polls_only_while_powered_and_reads_celsius(self):
        manager = SimpleNamespace(
            entry=Mock(),
            callbacks=SimpleNamespace(update=[], disconnect=[]),
            hass=Mock(),
            info=SimpleNamespace(identifier="receiver"),
            device_info={},
            connected=True,
            write=AsyncMock(),
        )
        with (
            patch("custom_components.onkyo_receiver_plus.extras.async_track_time_interval"),
            patch("custom_components.onkyo_receiver_plus.extras.async_dispatcher_send"),
        ):
            extras = ReceiverExtras(manager)
            sensor = OnkyoReceiverSensor(extras, "receiver_temperature")
            await extras._refresh_temperature(None)
            manager.write.assert_not_awaited()
            extras.powered = True
            await extras._refresh_temperature(None)
            manager.write.assert_awaited_once_with(query.Temperature())
            await extras._update(status.Temperature(Code.TPD, b"F 89C 32", 32, 89))
            self.assertTrue(sensor.available)
            self.assertEqual(sensor.native_value, 32)
            await extras._update(status.Raw(b"HOI", b"12"))
            self.assertEqual(extras.hdmi_routing, {"main_output": "main", "sub_output": "zone_2"})
            await extras._update(status.Raw(b"DLC", b"00"))
            await extras._update(status.Raw(b"DCE", b"00"))
            self.assertFalse(extras.available("dts_dialog"))
            await extras._update(status.Raw(b"DCE", b"01"))
            self.assertTrue(extras.available("dts_dialog"))
            await extras._update(status.Raw(
                b"NRI",
                b"<response><device><firmwareversion>TEST-01</firmwareversion></device></response>",
            ))
            await extras._disconnect()
            self.assertFalse(sensor.available)
            firmware = OnkyoReceiverSensor(extras, "firmware_version")
            self.assertTrue(firmware.available)
            self.assertEqual(firmware.native_value, "TEST-01")
