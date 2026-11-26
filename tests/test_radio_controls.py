"""Exercise the device editor and registered HA service handlers."""

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aioonkyo import Zone, status

from custom_components.onkyo_receiver_plus.fm import FmStations
from custom_components.onkyo_receiver_plus.media_player import DATA_MP_ENTITIES, DATA_RADIO
from custom_components.onkyo_receiver_plus.radio_controls import (
    FmName, FmFrequency, FmEditSelection, RadioButton,
)
from custom_components.onkyo_receiver_plus.receiver import ReceiverManager
from custom_components.onkyo_receiver_plus.services import async_setup_services


class RadioControlsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = SimpleNamespace(
            info=SimpleNamespace(identifier="rx"),
            device_info={"identifiers": {("onkyo_receiver_plus", "rx")}},
            connected=True,
        )
        with patch("custom_components.onkyo_receiver_plus.fm.Store") as store:
            store.return_value.async_save = AsyncMock()
            self.fm = FmStations(None, "entry", self.manager)
        self.data = SimpleNamespace(manager=self.manager, fm=self.fm, dab=None)

    async def test_device_controls_save_edit_delete_without_network(self):
        name, freq = FmName(self.data), FmFrequency(self.data)
        await name.async_set_value("89.0 RTL")
        await freq.async_set_native_value(89)
        await RadioButton(self.data, "fm_station_save").async_press()
        self.assertEqual(self.fm.stations, [{"name": "89.0 RTL", "freq": 89.0}])
        self.fm.edit_name = ""
        await FmEditSelection(self.data).async_select_option("89.0 RTL")
        self.assertEqual(name.native_value, "89.0 RTL")
        self.assertEqual(freq.native_value, 89.0)
        await freq.async_set_native_value(90)
        await RadioButton(self.data, "fm_station_save").async_press()
        self.assertEqual(len(self.fm.stations), 1)
        self.assertEqual(self.fm.stations[0]["freq"], 90)
        await RadioButton(self.data, "fm_station_delete").async_press()
        self.assertEqual(self.fm.stations, [])

    async def test_registered_service_accepts_one_service_call(self):
        hass = SimpleNamespace(data={}, services=SimpleNamespace(async_register=Mock()))
        hass.data[DATA_MP_ENTITIES] = {
            "entry": {Zone.MAIN: SimpleNamespace(entity_id="media_player.rx")}
        }
        hass.data[DATA_RADIO] = {"entry": (self.fm, None)}
        async_setup_services(hass)
        handlers = {
            call.args[1]: call.args[2]
            for call in hass.services.async_register.call_args_list
        }
        await handlers["save_fm_station"](SimpleNamespace(data={
            "entity_id": ["media_player.rx"], "name": "Test", "frequency": 89,
        }))
        self.assertEqual(self.fm.stations[0]["name"], "Test")
        await handlers["delete_fm_station"](SimpleNamespace(data={
            "entity_id": ["media_player.rx"], "name": "Test",
        }))
        self.assertEqual(self.fm.stations, [])


class ReceiverLifecycleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = ReceiverManager(None, SimpleNamespace(), SimpleNamespace())

    async def test_callback_error_does_not_kill_other_callbacks(self):
        bad = AsyncMock(side_effect=ValueError("bad metadata"))
        good = AsyncMock()
        self.manager.callbacks.update.extend([bad, good])
        msg = status.Raw(b"DSN", b"ENERGY")
        with self.assertLogs(
            "custom_components.onkyo_receiver_plus.receiver", level="ERROR"
        ):
            await self.manager.on_update(msg)
        good.assert_awaited_once_with(msg)

    async def test_stop_awaits_connection_task_and_clears_state(self):
        closed = asyncio.Event()

        async def connection():
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()

        self.manager._task = asyncio.create_task(connection())
        self.manager.connected = True
        await asyncio.sleep(0)
        await self.manager.async_stop()
        self.assertTrue(closed.is_set())
        self.assertFalse(self.manager.connected)
        self.assertIsNone(self.manager.receiver)
        await self.manager.async_stop()

    async def test_network_error_reconnects_and_cancellation_exits(self):
        first, second = AsyncMock(), AsyncMock()
        first.__aenter__.return_value.read.side_effect = OSError("connection reset")
        second.__aenter__.return_value.read.side_effect = asyncio.CancelledError
        self.manager.on_connect = AsyncMock()
        self.manager.on_disconnect = AsyncMock()
        with patch(
            "custom_components.onkyo_receiver_plus.receiver.connect",
            side_effect=[first, second],
        ) as connect, patch(
            "custom_components.onkyo_receiver_plus.receiver.asyncio.sleep", new=AsyncMock()
        ), self.assertLogs(
            "custom_components.onkyo_receiver_plus.receiver", level="WARNING"
        ):
            with self.assertRaises(asyncio.CancelledError):
                await self.manager._run()
        self.assertEqual(connect.call_args_list[0].kwargs, {"retry": False})
        self.assertEqual(connect.call_args_list[1].kwargs, {"retry": True})
        first.__aexit__.assert_awaited_once()
        second.__aexit__.assert_awaited_once()
        self.assertFalse(self.manager.connected)
