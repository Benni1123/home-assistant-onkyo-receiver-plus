"""Controls and signal information for the TX-NR6050."""

import asyncio
from datetime import datetime, timedelta
import logging
import re

from aioonkyo import Status, Zone, query, status
from aioonkyo.instruction import RawInstruction

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_interval

from .const import DOMAIN, InputSource
from .receiver import ReceiverManager
from .source_names import DEVICE_INFO_CODE, parse_firmware_version

_LOGGER = logging.getLogger(__name__)

DIMMER = {"bright": b"00", "dim": b"01", "dark": b"02"}
NIGHT = {"off": b"00", "on": b"01", "high": b"02", "auto": b"03"}
OUTPUT = {"main": b"01", "sub": b"02", "both": b"03"}
ACCUEQ = {"off": b"00", "all": b"01", "except_front": b"02"}
MANUAL_EQ = {"off": b"00", "preset_1": b"01", "preset_2": b"02", "preset_3": b"03"}
DIGITAL_FILTER = {"slow": b"00", "sharp": b"01", "short": b"02", "auto": b"03"}
STEREO_ASSIGN = {
    "front": b"FR",
    "surround": b"SR",
    "surround_back": b"SB",
    "height_1": b"H1",
    "height_2": b"H2",
}
TUNER_SOURCES = {InputSource("24"), InputSource("25"), InputSource("33")}
FM = InputSource("24")
TEMPERATURE_INTERVAL = timedelta(minutes=1)

CONTROL_CODES = {
    "bass": b"TFR",
    "treble": b"TFR",
    "av_sync": b"AVS",
    "vocal": b"VOC",
    "dts_dialog": b"DLC",
    "sleep_timer": b"SLP",
    "music_optimizer": b"MOT",
    "hdmi_cec": b"CEC",
    "hdmi_audio_out": b"HAO",
    "arc": b"ARC",
    "cinema_filter": b"RAS",
    "dimmer": b"DIM",
    "late_night": b"LTN",
    "hdmi_output": b"HDO",
    "accueq": b"AEQ",
    "manual_eq": b"EQS",
    "digital_filter": b"DGF",
    "stereo_assign": b"SAM",
    "tuner_preset": b"PRS",
    "fm_frequency": b"TUN",
}

STARTUP_CODES = tuple(
    dict.fromkeys(code for key, code in CONTROL_CODES.items() if key not in {
        "tuner_preset", "fm_frequency",
    })
)
AUDIO_MODE_CODES = (
    b"TFR", b"AVS", b"MOT", b"LTN", b"VOC", b"AEQ", b"EQS", b"DGF", b"RAS",
    b"SAM", b"DCE", b"DLC",
)


def integer_parameter(
    key: str, value: float, minimum: float, maximum: float, step: float
) -> bytes:
    """Encode a validated numeric control value."""
    if not minimum <= value <= maximum or abs(value / step - round(value / step)) > 1e-6:
        raise ValueError("Value is outside the allowed range or step.")
    number = round(value)
    if key in {"bass", "treble"}:
        return (key[0].upper() + (f"{number:+02X}" if number else "00")).encode()
    if key == "av_sync":
        return (f"+{number:03d}" if number else "0000").encode()
    if key == "sleep_timer" and number == 0:
        return b"OFF"
    if key == "dts_dialog" and number != 0:
        return f"+{number}".encode()
    if key == "fm_frequency":
        return f"{round(value * 100):05d}".encode()
    return f"{number:02X}".encode()


def raw_value(code: bytes, parameter: bytes) -> tuple[str, str | int | float | bool] | None:
    """Decode raw replies for controls not handled natively by aioonkyo."""
    for key in ("music_optimizer", "hdmi_cec", "hdmi_audio_out", "arc", "cinema_filter"):
        if code == CONTROL_CODES[key] and parameter in {b"00", b"01"}:
            return key, parameter == b"01"
    for key, options in (
        ("dimmer", DIMMER), ("late_night", NIGHT), ("accueq", ACCUEQ),
        ("manual_eq", MANUAL_EQ), ("digital_filter", DIGITAL_FILTER),
        ("stereo_assign", STEREO_ASSIGN),
    ):
        if code == CONTROL_CODES[key]:
            for label, value in options.items():
                if value == parameter:
                    return key, label
    if code == b"AVS" and re.fullmatch(rb"(?:[+-][0-9]{3}|0000)", parameter):
        return "av_sync", int(parameter)
    if code == b"TUN" and re.fullmatch(rb"\d{5}", parameter):
        if 8750 <= (freq := int(parameter)) <= 10800:
            return "fm_frequency", freq / 100
    if code == b"SLP" and parameter == b"OFF":
        return "sleep_timer", 0
    if code == b"NSB" and parameter in (b"ON", b"OFF"):
        return "network_standby", parameter == b"ON"
    if code == b"DCE" and parameter in (b"00", b"01"):
        return "dts_dialog_supported", parameter == b"01"
    if code == b"DLC" and re.fullmatch(rb"(?:00|\+[1-6])", parameter):
        return "dts_dialog", int(parameter)
    if code in (b"SLP", b"VOC") and re.fullmatch(rb"[0-9A-Fa-f]{2}", parameter):
        value = int(parameter, 16)
        if code == b"SLP" and value <= 90:
            return "sleep_timer", value
        if code == b"VOC" and value <= 5:
            return "vocal", value
    return None


def speaker_configuration(
    payload: bytes,
) -> tuple[str, dict[str, str | int]] | None:
    """Decode the receiver's speaker layout without assuming a surround-back count."""
    if not re.fullmatch(rb"[0-2]{7}(?:\d{3}|---)[0-8]{2}[0-7]", payload):
        return None
    subs, front, center, surround, back, height1, height2 = map(
        int, payload[:7].decode("ascii")
    )
    channels = (2 if front else 0) + bool(center) + (2 if surround else 0)
    summary = f"{channels}.{subs}"
    if back:
        summary += " + Surround Back"
    if height1 or height2:
        summary += " + Height"
    sizes = ("none", "small", "large")
    attributes = {
        "subwoofers": subs,
        "front": sizes[front],
        "center": sizes[center],
        "surround": sizes[surround],
        "surround_back": sizes[back],
        "height_1": sizes[height1],
        "height_2": sizes[height2],
    }
    if payload[7:10] != b"---":
        attributes["crossover_hz"] = int(payload[7:10])
    return summary, attributes


class ReceiverExtras:
    """Keep extra entities synchronized via the existing eISCP connection."""

    def __init__(self, manager: ReceiverManager) -> None:
        self.manager = manager
        self.signal = f"{DOMAIN}_{manager.entry.entry_id}_extras"
        self.values: dict[str, str | int | float | bool | None] = {}
        self.audio: dict[str, str] = {}
        self.video: dict[str, str] = {}
        self.speakers: dict[str, str | int] = {}
        self.hdmi_routing: dict[str, str] = {}
        self.firmware: str | None = None
        self.powered = False
        self.source: InputSource | None = None
        self._refresh_cancel: CALLBACK_TYPE | None = None
        self._startup_pending = True
        manager.callbacks.update.append(self._update)
        manager.callbacks.disconnect.append(self._disconnect)
        manager.entry.async_on_unload(self._cancel_refresh)
        manager.entry.async_on_unload(
            async_track_time_interval(
                manager.hass, self._refresh_temperature, TEMPERATURE_INTERVAL
            )
        )

    @callback
    def _publish(self) -> None:
        async_dispatcher_send(self.manager.hass, self.signal)

    @callback
    def _cancel_refresh(self) -> None:
        if self._refresh_cancel is not None:
            self._refresh_cancel()
            self._refresh_cancel = None

    async def _disconnect(self) -> None:
        self._cancel_refresh()
        self.powered = False
        self.source = None
        self.values.clear()
        self.audio.clear()
        self.video.clear()
        self.speakers.clear()
        self.hdmi_routing.clear()
        self._startup_pending = True
        self._publish()

    @callback
    def _queue_refresh(self) -> None:
        self._cancel_refresh()
        self._refresh_cancel = async_call_later(self.manager.hass, 0.8, self._refresh)

    async def _refresh(self, _: datetime) -> None:
        self._refresh_cancel = None
        startup = self._startup_pending
        self._startup_pending = False
        codes = list(
            (*STARTUP_CODES, b"DCE", b"NSB", b"HOI") if startup else AUDIO_MODE_CODES
        )
        if self.source in TUNER_SOURCES:
            codes.append(b"PRS")
        if self.source is FM:
            codes.append(b"TUN")
        try:
            for code in codes:
                if not self.powered or not self.manager.connected:
                    return
                await self.manager.write(RawInstruction(code, b"QSTN"))
                await asyncio.sleep(0.1)
            if startup and self.powered and self.manager.connected:
                for instruction in (
                    query.AudioInformation(),
                    query.VideoInformation(),
                    query.FLDisplay(),
                    query.Temperature(),
                    RawInstruction(b"SPI", b"QSTN"),
                ):
                    await self.manager.write(instruction)
        except OSError as err:
            _LOGGER.debug("Extra receiver status query interrupted: %s", err)

    async def _refresh_temperature(self, _: datetime) -> None:
        if self.powered and self.manager.connected:
            try:
                await self.manager.write(query.Temperature())
            except OSError as err:
                _LOGGER.debug("Receiver temperature query interrupted: %s", err)

    def available(self, key: str) -> bool:
        if key == "firmware_version":
            return self.firmware is not None
        if not self.powered or not self.manager.connected:
            return False
        if key == "tuner_preset":
            return self.source in TUNER_SOURCES and key in self.values
        if key == "dts_dialog" and self.values.get("dts_dialog_supported") is not True:
            return False
        if key == "fm_frequency" and self.source is not FM:
            return False
        return self.values.get(key) is not None

    async def set(self, key: str, parameter: bytes) -> None:
        """Send one documented setting change and ask the AVR for its value."""
        if not self.available(key):
            raise HomeAssistantError("Receiver setting is currently unavailable.")
        code = CONTROL_CODES[key]
        await self.manager.write(RawInstruction(code, parameter))
        await asyncio.sleep(0.2)
        if self.manager.connected and self.powered:
            await self.manager.write(RawInstruction(code, b"QSTN"))

    async def _update(self, message: Status) -> None:
        if isinstance(message, status.Raw) and message.raw_code == DEVICE_INFO_CODE:
            firmware = parse_firmware_version(message.parameter)
            if firmware is not None and firmware != self.firmware:
                self.firmware = firmware
                self._publish()
            return
        if not isinstance(message, status.Raw) and message.zone is not Zone.MAIN:
            return
        if isinstance(message, status.Power):
            if message.param is status.Power.Param.STANDBY:
                await self._disconnect()
            elif not self.powered and message.param is status.Power.Param.ON:
                self.powered = True
                self._queue_refresh()
                self._publish()
            return
        if not self.powered:
            return
        match message:
            case status.Raw(raw_code=code, parameter=parameter):
                if code == b"SPI":
                    if configuration := speaker_configuration(parameter):
                        self.values["speaker_configuration"], self.speakers = configuration
                    else:
                        self.values.pop("speaker_configuration", None)
                        self.speakers.clear()
                elif code == b"HOI":
                    if re.fullmatch(rb"1[012]", parameter):
                        sub = {b"0": "none", b"1": "main", b"2": "zone_2"}[parameter[1:]]
                        self.hdmi_routing = {"main_output": "main", "sub_output": sub}
                        self.values["hdmi_routing"] = sub
                    else:
                        self.hdmi_routing.clear()
                        self.values.pop("hdmi_routing", None)
                elif result := raw_value(code, parameter):
                    key, value = result
                    self.values[key] = value
                elif code == b"DCE":
                    self.values.pop("dts_dialog_supported", None)
                elif code == b"SLP":
                    self.values.pop("sleep_timer", None)
                elif code in CONTROL_CODES.values():
                    for key, control_code in CONTROL_CODES.items():
                        if control_code == code:
                            self.values.pop(key, None)
                else:
                    return
            case status.InputSource(param=source):
                if source == self.source:
                    return
                self.source = source
                for key in (
                    "av_sync", "music_optimizer", "tuner_preset", "fm_frequency",
                ):
                    self.values.pop(key, None)
                self._queue_refresh()
            case status.ListeningMode():
                self._queue_refresh()
                return
            case status.NotAvailable(code=code):
                keys = [key for key, control_code in CONTROL_CODES.items()
                        if code.raw == control_code]
                if not keys:
                    return
                for key in keys:
                    self.values.pop(key, None)
            case status.Tone(bass=bass, treble=treble):
                self.values.update(bass=bass, treble=treble)
            case status.TunerPreset(param=preset):
                self.values["tuner_preset"] = preset or None
            case status.HDMIOutput(param=output):
                self.values["hdmi_output"] = next(
                    (key for key, code in OUTPUT.items() if code == output.value.encode()),
                    None,
                )
            case status.FLDisplay(param=display):
                self.values["display"] = display.strip() or None
            case status.Temperature(celsius=celsius):
                if not -20 <= celsius <= 125:
                    return
                self.values["receiver_temperature"] = celsius
            case status.AudioInformation():
                self.audio = {
                    key: value
                    for key in (
                        "input_port", "input_signal_format", "input_frequency",
                        "input_channels", "listening_mode", "output_channels",
                    )
                    if (value := getattr(message, key if key != "input_port" else "audio_input_port", None))
                }
                self.values["audio_signal"] = self.audio.get("input_signal_format")
                self.values["audio_input_channels"] = self.audio.get("input_channels")
                self.values["audio_output_channels"] = self.audio.get("output_channels")
            case status.VideoInformation():
                self.video = {
                    key: value
                    for key in (
                        "video_input_port", "input_resolution", "input_color_schema",
                        "input_color_depth", "video_output_port", "output_resolution",
                        "output_color_schema", "output_color_depth", "input_hdr",
                    )
                    if (value := getattr(message, key, None))
                }
                self.values["video_signal"] = self.video.get("output_resolution")
                self.values["video_hdr"] = self.video.get("input_hdr")
            case _:
                return
        self._publish()
