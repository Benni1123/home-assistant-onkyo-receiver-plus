"""Refresh options labels from the live AVR, not the startup snapshot."""

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

from aioonkyo import status
from aioonkyo.instruction import RawInstruction

from custom_components.onkyo_receiver_plus.config_flow import OnkyoOptionsFlowHandler
from custom_components.onkyo_receiver_plus.const import (
    InputSource, OPTION_INPUT_SOURCES, OPTION_LISTENING_MODES,
    ListeningMode, OPTION_VOLUME_RESOLUTION, OPTION_MAX_VOLUME,
    OPTION_AUTO_INPUT_NAMES, OPTION_SHOW_HDMI_PORTS, OPTION_VOLUME_MODE,
    OPTION_VOLUME_STEP_DELAY, VOLUME_MODE_DIRECT,
)
from custom_components.onkyo_receiver_plus.receiver import ReceiverManager
from custom_components.onkyo_receiver_plus.util import get_meaning


class InputCatalogTest(unittest.IsolatedAsyncioTestCase):
    async def test_refresh_reads_new_names_on_shared_connection(self):
        manager = ReceiverManager(
            None, SimpleNamespace(), SimpleNamespace(model_name="TX-NR6050")
        )
        manager.connected = True
        manager.input_names = {InputSource("02"): "GAME"}
        manager.hdmi_ports = {InputSource("02"): 1}

        async def write(message):
            if message.raw_code == b"NRI":
                reply = status.Raw(b"NRI", (
                    b'<response><device><selectorlist>'
                    b'<selector id="02" value="1" name="XBOX"/>'
                    b'</selectorlist></device></response>'
                ))
            else:
                reply = status.Raw(b"sHI", b"CGMHI2")
            await manager.on_update(reply)

        manager.write = AsyncMock(side_effect=write)
        names, ports = await manager.async_refresh_input_catalog()
        self.assertEqual(names[InputSource("02")], "XBOX")
        self.assertEqual(ports[InputSource("02")], 2)
        self.assertEqual(manager.callbacks.update, [])
        self.assertEqual(
            [call.args[0] for call in manager.write.await_args_list],
            [RawInstruction(b"NRI", b"QSTN"), RawInstruction(b"sHI", b"CQSTN")],
        )

    async def test_disconnected_refresh_preserves_known_labels(self):
        manager = ReceiverManager(
            None, SimpleNamespace(), SimpleNamespace(model_name="TX-NR6050")
        )
        manager.input_names = {InputSource("02"): "XBOX"}
        manager.write = AsyncMock()
        names, _ = await manager.async_refresh_input_catalog()
        self.assertEqual(names[InputSource("02")], "XBOX")
        manager.write.assert_not_awaited()

    async def test_options_open_uses_fresh_receiver_label_without_reload(self):
        manager = SimpleNamespace(
            input_names={InputSource("02"): "GAME"},
            hdmi_ports={InputSource("02"): 2},
            async_refresh_input_catalog=AsyncMock(return_value=(
                {InputSource("02"): "XBOX"}, {InputSource("02"): 2},
            )),
        )
        entry = SimpleNamespace(
            options={
                OPTION_VOLUME_RESOLUTION: 100, OPTION_MAX_VOLUME: 40,
                OPTION_INPUT_SOURCES: {"10": "Google TV"},
                OPTION_LISTENING_MODES: {},
            },
            runtime_data=SimpleNamespace(manager=manager),
        )
        with patch.object(
            OnkyoOptionsFlowHandler, "config_entry", new_callable=PropertyMock,
            return_value=entry,
        ):
            flow = OnkyoOptionsFlowHandler()
            # Inspect the real schema passed to HA, avoiding flow-manager setup.
            flow.async_show_form = Mock(side_effect=lambda **kwargs: kwargs)
            result = await flow.async_step_init()
            selector = next(
                value for key, value in result["data_schema"].schema.items()
                if key.schema == OPTION_INPUT_SOURCES
            )
            labels = [option["label"] for option in selector.config["options"]]
            self.assertIn("HDMI 2 / XBOX", labels)
            self.assertNotIn("HDMI 2 / GAME", labels)
            manager.async_refresh_input_catalog.assert_awaited_once()
            flow.async_step_names = AsyncMock(return_value={"step_id": "names"})
            await flow.async_step_init({
                OPTION_INPUT_SOURCES: [
                    get_meaning(InputSource("02")), get_meaning(InputSource("10")),
                ],
                OPTION_LISTENING_MODES: [get_meaning(ListeningMode("00"))],
                OPTION_AUTO_INPUT_NAMES: True, OPTION_SHOW_HDMI_PORTS: True,
                OPTION_MAX_VOLUME: 40, OPTION_VOLUME_MODE: VOLUME_MODE_DIRECT,
                OPTION_VOLUME_STEP_DELAY: 0.25,
            })
            self.assertEqual(flow._input_sources[InputSource("02")], "XBOX")
            self.assertEqual(flow._input_sources[InputSource("10")], "Google TV")
            manager.async_refresh_input_catalog.assert_awaited_once()
