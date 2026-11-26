"""Test local remote commands without sending anything to a real receiver."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aioonkyo import Code, Zone, command, status
from aioonkyo.instruction import RawInstruction
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.onkyo_receiver_plus.media_player import DATA_MP_ENTITIES
from custom_components.onkyo_receiver_plus.remote import OnkyoRemote


class RemoteTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = SimpleNamespace(
            info=SimpleNamespace(identifier="receiver"),
            entry=SimpleNamespace(entry_id="entry"),
            device_info={"identifiers": {("onkyo_receiver_plus", "receiver")}},
            connected=True,
            write=AsyncMock(),
        )
        self.remote = OnkyoRemote(self.manager)
        self.remote.hass = SimpleNamespace(data={DATA_MP_ENTITIES: {"entry": {}}})
        self.remote.async_write_ha_state = Mock()
        self.remote._attr_is_on = True

    async def test_navigation_sequence_and_repeats(self):
        with patch("custom_components.onkyo_receiver_plus.remote.asyncio.sleep", new_callable=AsyncMock):
            await self.remote.async_send_command(
                ["quick_menu", "left", "Enter"], num_repeats=2, delay_secs=0
            )
        expected = [
            RawInstruction(b"OSD", value)
            for value in (b"QUICK", b"LEFT", b"ENTER") * 2
        ]
        self.assertEqual([item.args[0] for item in self.manager.write.await_args_list], expected)

    async def test_uses_alternate_menu_codes_on_another_receiver(self):
        await self.remote._on_update(status.Raw(
            b"NRI",
            b'<response><device><controllist>'
            b'<control id="Setup" value="0" code="MENU"/>'
            b'<control id="Home" value="1" code="HOME"/>'
            b'<control id="AV Adjust" value="1" code="AUDIO"/>'
            b'</controllist></device></response>',
        ))
        await self.remote.async_send_command("setup")
        await self.remote.async_send_command("quick_menu")
        self.assertEqual(
            [item.args[0] for item in self.manager.write.await_args_list],
            [RawInstruction(b"OSD", b"HOME"), RawInstruction(b"OSD", b"AUDIO")],
        )

    async def test_rejects_unknown_keys_and_large_sequences_before_sending(self):
        for keys, kwargs in (
            (["up", "unknown"], {}),
            (["up"], {"num_repeats": 33}),
            (["up"], {"hold_secs": 2}),
        ):
            with self.assertRaises(ServiceValidationError):
                await self.remote.async_send_command(keys, **kwargs)
        self.manager.write.assert_not_awaited()

    async def test_volume_and_input_use_main_player(self):
        player = SimpleNamespace(enabled=True, async_volume_up=AsyncMock(), async_select_source=AsyncMock())
        self.remote.hass.data[DATA_MP_ENTITIES]["entry"][Zone.MAIN] = player
        await self.remote.async_send_command("volume_up")
        await self.remote.async_send_command("input:HDMI 1 / Google TV")
        player.async_volume_up.assert_awaited_once()
        player.async_select_source.assert_awaited_once_with("HDMI 1 / Google TV")
        self.manager.write.assert_not_awaited()

    async def test_home_assistant_service_style_keyword_call(self):
        # remote.send_command delivers service data as kwargs with `command`.
        await self.remote.async_send_command(command=["ok"], num_repeats=1)
        await self.remote.async_send_command(command="back")
        self.assertEqual(
            [item.args[0] for item in self.manager.write.await_args_list],
            [RawInstruction(b"OSD", b"ENTER"), RawInstruction(b"OSD", b"EXIT")],
        )

    async def test_missing_command_is_rejected(self):
        with self.assertRaises(ServiceValidationError):
            await self.remote.async_send_command()
        self.manager.write.assert_not_awaited()

    async def test_standby_blocks_menu_commands_but_allows_power_on(self):
        await self.remote._on_update(status.Power(Code.PWR, b"00", status.Power.Param.STANDBY))
        self.assertFalse(self.remote.is_on)
        with self.assertRaises(HomeAssistantError):
            await self.remote.async_send_command("quick_menu")
        await self.remote.async_send_command("power_on")
        self.manager.write.assert_awaited_once_with(
            command.Power(Zone.MAIN, command.Power.Param.ON)
        )
