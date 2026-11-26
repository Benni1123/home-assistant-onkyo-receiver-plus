"""Exercise core controls without sending anything to a real receiver."""

import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aioonkyo import Code, Zone, command, query, status
from homeassistant.components.media_player import MediaPlayerState

from custom_components.onkyo_receiver_plus.const import InputSource
from custom_components.onkyo_receiver_plus.media_player import OnkyoMediaPlayer


class MediaPlayerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = SimpleNamespace(
            info=SimpleNamespace(model_name="TX-NR6050", identifier="test_receiver"),
            device_info={"identifiers": {("onkyo_receiver_plus", "test_receiver")}},
            connected=True,
            write=AsyncMock(),
            entry=SimpleNamespace(
                async_create_background_task=lambda _hass, work, _name: asyncio.create_task(
                    work
                )
            ),
        )
        self.entity = OnkyoMediaPlayer(
            self.manager,
            Zone.MAIN,
            volume_resolution=100,
            max_volume=40,
            ramp_enabled=True,
            ramp_delay=0,
            sources={InputSource("10"): "Blu-ray"},
            sound_modes={},
        )
        self.entity.hass = Mock()
        self.entity._attr_state = MediaPlayerState.ON
        self.entity._device_volume = 37
        self.entity._attr_volume_level = 37 / 40
        self.entity.async_write_ha_state = Mock()

    def confirm(self, instruction):
        self.entity._device_volume = instruction.param
        self.entity._volume_reports.put_nowait(instruction.param)

    async def test_ramp_steps_through_confirmed_levels(self):
        self.manager.write.side_effect = self.confirm
        await self.entity.async_set_volume_level(1)
        await self.entity._ramp_task
        self.assertEqual(
            [call.args[0].param for call in self.manager.write.await_args_list],
            [38, 39, 40],
        )
        await self.entity.async_volume_up()
        self.assertEqual(self.manager.write.await_count, 3)

    async def test_slider_resumes_live_feedback_after_protected_window(self):
        published = []
        self.entity.async_write_ha_state.side_effect = lambda: published.append(
            self.entity.volume_level
        )

        def reply(instruction):
            if instruction.param == 38:
                self.entity._volume_ui_feedback_after = float("inf")
            if instruction.param == 39:
                self.entity._volume_ui_feedback_after = 0
            self.entity.process_update(
                status.Volume(Code.MVL, instruction.parameter, instruction.param)
            )

        self.manager.write.side_effect = reply
        await self.entity.async_set_volume_level(1)
        await self.entity._ramp_task
        self.assertEqual(published, [37 / 40, 39 / 40, 1])

    async def test_slider_has_time_to_send_final_target_before_first_step(self):
        self.manager.write.side_effect = self.confirm
        await self.entity.async_set_volume_level(0.95)
        await asyncio.sleep(0.01)
        self.manager.write.assert_not_awaited()
        await self.entity.async_set_volume_level(1)
        await self.entity._ramp_task
        self.assertEqual(
            [call.args[0].param for call in self.manager.write.await_args_list],
            [38, 39, 40],
        )

    async def test_new_target_replaces_old_target(self):
        async def retarget(instruction):
            self.confirm(instruction)
            if instruction.param == 38:
                await self.entity.async_set_volume_level(0.9)

        self.manager.write.side_effect = retarget
        await self.entity.async_set_volume_level(1)
        await self.entity._ramp_task
        self.assertEqual(
            [call.args[0].param for call in self.manager.write.await_args_list],
            [38, 37, 36],
        )

    async def test_ramp_stops_on_unexpected_receiver_feedback(self):
        self.manager.write.side_effect = lambda _: self.entity._volume_reports.put_nowait(35)
        with (
            patch("custom_components.onkyo_receiver_plus.media_player.VOLUME_PUSH_TIMEOUT", 0.01),
            patch("custom_components.onkyo_receiver_plus.media_player.VOLUME_QUERY_TIMEOUT", 0.01),
            self.assertLogs(level="WARNING"),
        ):
            await self.entity.async_set_volume_level(1)
            await self.entity._ramp_task
        self.assertEqual(
            [call.args[0] for call in self.manager.write.await_args_list],
            [command.Volume(Zone.MAIN, 38), query.Volume(Zone.MAIN)],
        )

    async def test_ramp_rechecks_late_stale_report_after_confirmation(self):
        pending = None

        async def reply(instruction):
            nonlocal pending
            if isinstance(instruction, query.Volume):
                self.confirm(pending)
                return
            previous = self.entity._device_volume
            pending = instruction
            self.confirm(instruction)
            if instruction.param == 38:
                self.entity._device_volume = previous
                self.entity._volume_reports.put_nowait(previous)

        self.manager.write.side_effect = reply
        await self.entity.async_set_volume_level(1)
        await self.entity._ramp_task
        self.assertEqual(
            [call.args[0] for call in self.manager.write.await_args_list],
            [
                command.Volume(Zone.MAIN, 38),
                query.Volume(Zone.MAIN),
                command.Volume(Zone.MAIN, 39),
                command.Volume(Zone.MAIN, 40),
            ],
        )

    async def test_ramp_ignores_duplicates_and_queries_missing_push(self):
        pending = None

        def reply(instruction):
            nonlocal pending
            if isinstance(instruction, query.Volume):
                self.confirm(pending)
            else:
                self.entity._volume_reports.put_nowait(self.entity._device_volume)
                pending = instruction

        self.manager.write.side_effect = reply
        with patch(
            "custom_components.onkyo_receiver_plus.media_player.VOLUME_PUSH_TIMEOUT", 0.01
        ):
            await self.entity.async_set_volume_level(1)
            await self.entity._ramp_task
        expected = [
            message
            for step in (38, 39, 40)
            for message in (command.Volume(Zone.MAIN, step), query.Volume(Zone.MAIN))
        ]
        self.assertEqual(
            [call.args[0] for call in self.manager.write.await_args_list], expected
        )

    async def test_direct_mode_and_renamed_input(self):
        self.entity._ramp_enabled = False
        await self.entity.async_set_volume_level(1)
        self.manager.write.assert_awaited_once_with(command.Volume(Zone.MAIN, 40))
        await self.entity.async_select_source("Blu-ray")
        self.assertEqual(self.entity.source_list, ["Blu-ray"])
        self.assertEqual(
            self.manager.write.await_args.args[0], command.InputSource(Zone.MAIN, InputSource("10"))
        )

    async def test_imported_name_refreshes_active_source_and_keeps_alias(self):
        source = InputSource("10")
        self.entity._current_source = source
        self.entity.hass = None
        self.entity.update_source_names(
            {source: "HDMI 1 / Google TV"}, {source: "Google TV"}
        )
        self.assertEqual(self.entity.source, "HDMI 1 / Google TV")
        self.assertEqual(self.entity.source_list, ["HDMI 1 / Google TV"])
        for name in ("HDMI 1 / Google TV", "Google TV", "Blu-ray"):
            await self.entity.async_select_source(name)
            self.assertEqual(
                self.manager.write.await_args.args[0], command.InputSource(Zone.MAIN, source)
            )
