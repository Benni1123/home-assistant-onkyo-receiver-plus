"""Media player platform."""

import asyncio
from datetime import datetime
import logging
from time import monotonic_ns
from typing import TYPE_CHECKING, Any, override

from aioonkyo import Code, Kind, Status, Zone, command, query, status
from aioonkyo.instruction import RawInstruction

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    SearchMedia,
    SearchMediaQuery,
)
from homeassistant.components.media_player.errors import BrowseError, SearchError
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later
from homeassistant.util.hass_dict import HassKey

from .const import (
    DOMAIN,
    LEGACY_HDMI_OUTPUT_MAPPING,
    LEGACY_REV_HDMI_OUTPUT_MAPPING,
    OPTION_AUTO_INPUT_NAMES,
    OPTION_MAX_VOLUME,
    OPTION_SHOW_HDMI_PORTS,
    OPTION_VOLUME_MODE,
    OPTION_VOLUME_RESOLUTION,
    OPTION_VOLUME_STEP_DELAY,
    VOLUME_MODE_RAMP,
    VOLUME_STEP_DELAY_DEFAULT,
    ZONES,
    InputSource,
    ListeningMode,
    VolumeResolution,
)
from .receiver import ReceiverManager
from .album_art import async_fetch_artwork
from .source_names import (
    DEVICE_INFO_CODE,
    HDMI_ASSIGNMENT_CODE,
    HDMI_ASSIGNMENT_QUERY,
    add_hdmi_prefixes,
    apply_input_names,
    parse_hdmi_assignments,
    parse_input_names,
    parse_presets,
)
from .dab import CONTENT_TYPE as DAB_CONTENT_TYPE, ROOT_ID as DAB_ROOT_ID, DabRadio
from .fm import CONTENT_TYPE as FM_CONTENT_TYPE, ROOT_ID as FM_ROOT_ID, FmStations
from .tunein import CONTENT_TYPE as TUNEIN_CONTENT_TYPE, NET, TuneIn
from .util import get_meaning

if TYPE_CHECKING:
    from . import OnkyoConfigEntry

_LOGGER = logging.getLogger(__name__)


DATA_MP_ENTITIES: HassKey[dict[str, dict[Zone, OnkyoMediaPlayer]]] = HassKey(DOMAIN)
DATA_RADIO: HassKey[dict[str, tuple[FmStations, DabRadio | None]]] = HassKey(
    f"{DOMAIN}_radio"
)


SUPPORTED_FEATURES_BASE = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.PLAY_MEDIA
)
SUPPORTED_FEATURES_VOLUME = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.VOLUME_STEP
)

PLAYABLE_SOURCES = (
    InputSource.FM,
    InputSource.AM,
    InputSource.DAB,
)

ATTR_PRESET = "preset"
ATTR_AUDIO_INFORMATION = "audio_information"
ATTR_VIDEO_INFORMATION = "video_information"
ATTR_VIDEO_OUT = "video_out"

QUERY_STATE_DELAY = 4
QUERY_AV_INFO_DELAY = 8
VOLUME_PUSH_TIMEOUT = 0.35
VOLUME_QUERY_TIMEOUT = 1.65
VOLUME_UI_FEEDBACK_PAUSE = 0.25

AUDIO_INFORMATION_MAPPING = [
    "audio_input_port",
    "input_signal_format",
    "input_frequency",
    "input_channels",
    "listening_mode",
    "output_channels",
    "output_frequency",
    "precision_quartz_lock_system",
    "auto_phase_control_delay",
    "auto_phase_control_phase",
    "upmix_mode",
]
VIDEO_INFORMATION_MAPPING = [
    "video_input_port",
    "input_resolution",
    "input_color_schema",
    "input_color_depth",
    "video_output_port",
    "output_resolution",
    "output_color_schema",
    "output_color_depth",
    "picture_mode",
    "input_hdr",
]


NET_META_CODES = {b"NTI", b"NAT", b"NAL", b"NJA"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnkyoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up media player platform for config entry."""
    data = entry.runtime_data

    manager = data.manager
    all_entities = hass.data[DATA_MP_ENTITIES]

    entities: dict[Zone, OnkyoMediaPlayer] = {}
    all_entities[entry.entry_id] = entities

    @callback
    def del_mp_entities() -> None:
        all_entities.pop(entry.entry_id, None)

    entry.async_on_unload(del_mp_entities)

    volume_resolution: VolumeResolution = entry.options[OPTION_VOLUME_RESOLUTION]
    max_volume: float = entry.options[OPTION_MAX_VOLUME]
    sources = data.sources
    unprefixed_sources = data.sources
    import_input_names = entry.options.get(OPTION_AUTO_INPUT_NAMES, True)
    can_read_hdmi_ports = manager.info.model_name.upper() == "TX-NR6050"
    show_hdmi_ports = entry.options.get(OPTION_SHOW_HDMI_PORTS, True)
    sound_modes = data.sound_modes
    fm_stations = data.fm
    dab_radio = data.dab
    hass.data.setdefault(DATA_RADIO, {})[entry.entry_id] = (fm_stations, dab_radio)
    @callback
    def del_radio() -> None:
        """Discard per-entry radio references without returning their values."""
        hass.data.get(DATA_RADIO, {}).pop(entry.entry_id, None)

    entry.async_on_unload(del_radio)

    async def connect_callback(reconnect: bool) -> None:
        await manager.write(RawInstruction(DEVICE_INFO_CODE, b"QSTN"))
        if can_read_hdmi_ports:
            await manager.write(RawInstruction(HDMI_ASSIGNMENT_CODE, HDMI_ASSIGNMENT_QUERY))
        if reconnect:
            for entity in entities.values():
                if entity.enabled:
                    await entity.query_state()

    async def disconnect_callback() -> None:
        for entity in entities.values():
            if entity.enabled:
                entity.cancel_pending()
                entity.async_write_ha_state()

    @callback
    def refresh_source_names() -> None:
        nonlocal sources, unprefixed_sources
        new_names = (
            apply_input_names(data.sources, manager.input_names)
            if import_input_names else data.sources
        )
        new_sources = (
            add_hdmi_prefixes(new_names, manager.hdmi_ports)
            if show_hdmi_ports else new_names
        )
        if new_sources != sources or new_names != unprefixed_sources:
            sources = new_sources
            unprefixed_sources = new_names
            for entity in entities.values():
                entity.update_source_names(sources, unprefixed_sources)

    async def update_callback(message: Status) -> None:
        if isinstance(message, status.Raw):
            if message.raw_code == DEVICE_INFO_CODE:
                if reported := parse_input_names(message.parameter):
                    manager.input_names = reported
                manager.presets = parse_presets(message.parameter)
                refresh_source_names()
            elif can_read_hdmi_ports and message.raw_code == HDMI_ASSIGNMENT_CODE:
                if (reported_ports := parse_hdmi_assignments(message.parameter)) is not None:
                    manager.hdmi_ports = reported_ports
                    refresh_source_names()
            elif message.raw_code in NET_META_CODES:
                if (main := entities.get(Zone.MAIN)) is not None and main.enabled:
                    main.update_net_media(message.raw_code, message.parameter)
            elif message.raw_code in (b"DSN", b"TUN"):
                if (main := entities.get(Zone.MAIN)) is not None and main.enabled:
                    main.update_tuner_media(message.raw_code, message.parameter)
            return

        zone = message.zone

        entity = entities.get(zone)
        if entity is not None:
            if entity.enabled:
                entity.process_update(message)
                if zone is Zone.MAIN and isinstance(message, status.InputSource):
                    if message.param == InputSource.DAB:
                        await manager.write(RawInstruction(b"DSN", b"QSTN"))
                    elif message.param == InputSource.FM:
                        await manager.write(RawInstruction(b"TUN", b"QSTN"))
        elif not isinstance(message, status.NotAvailable):
            # When we receive a valid status for a zone, then
            # that zone is available on the receiver,
            # so we create the entity for it.
            _LOGGER.debug(
                "Discovered %s on %s (%s)",
                ZONES[zone],
                manager.info.model_name,
                manager.info.host,
            )
            zone_entity = OnkyoMediaPlayer(
                manager,
                zone,
                volume_resolution=volume_resolution,
                max_volume=max_volume,
                ramp_enabled=entry.options.get(OPTION_VOLUME_MODE) == VOLUME_MODE_RAMP,
                ramp_delay=entry.options.get(
                    OPTION_VOLUME_STEP_DELAY, VOLUME_STEP_DELAY_DEFAULT
                ),
                sources=data.sources,
                sound_modes=sound_modes,
                tunein_supported=zone is Zone.MAIN and can_read_hdmi_ports,
                fm_stations=fm_stations,
                dab_radio=dab_radio,
            )
            if sources != data.sources or unprefixed_sources != data.sources:
                zone_entity.update_source_names(sources, unprefixed_sources)
            entities[zone] = zone_entity
            async_add_entities([zone_entity])

    manager.callbacks.connect.append(connect_callback)
    manager.callbacks.disconnect.append(disconnect_callback)
    manager.callbacks.update.append(update_callback)


class OnkyoMediaPlayer(MediaPlayerEntity):
    """Onkyo Receiver Media Player (one per each zone)."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_media_image_remotely_accessible = False

    _supports_volume: bool = False
    # None means no technical possibility of support
    _supports_sound_mode: bool | None = None
    _supports_audio_info: bool = False
    _supports_video_info: bool = False

    _query_state_unsub: CALLBACK_TYPE | None = None
    _query_av_info_unsub: CALLBACK_TYPE | None = None

    def __init__(
        self,
        manager: ReceiverManager,
        zone: Zone,
        *,
        volume_resolution: VolumeResolution,
        max_volume: float,
        ramp_enabled: bool,
        ramp_delay: float,
        sources: dict[InputSource, str],
        sound_modes: dict[ListeningMode, str],
        tunein_supported: bool = False,
        fm_stations: FmStations | None = None,
        dab_radio: DabRadio | None = None,
    ) -> None:
        """Initialize the Onkyo Receiver."""
        self._manager = manager
        self._zone = zone

        identifier = manager.info.identifier
        self._attr_device_info = manager.device_info
        self._attr_name = None if zone is Zone.MAIN else ZONES[zone]
        self._attr_unique_id = f"{identifier}_{zone.value}"

        self._volume_resolution = volume_resolution
        self._max_volume = max_volume
        self._device_volume: int | None = None
        self._ramp_enabled = ramp_enabled
        self._ramp_delay = ramp_delay
        self._ramp_target = 0
        self._volume_ui_feedback_after = 0.0
        self._ramp_task: asyncio.Task[None] | None = None
        self._volume_reports: asyncio.Queue[int] | None = None
        self._net_meta_unsub: CALLBACK_TYPE | None = None

        self._current_source: InputSource | None = None
        self._tuner_station_name: str | None = None
        self._fm_frequency: int | None = None
        self._set_source_mapping(sources)
        self._original_source_mapping = self._rev_source_mapping.copy()
        self._unprefixed_source_mapping: dict[str, InputSource] = {}

        zone_sound_modes = ListeningMode.for_zone(zone)
        self._sound_mode_mapping = {
            key: value for key, value in sound_modes.items() if key in zone_sound_modes
        }
        self._rev_sound_mode_mapping = {
            value: key for key, value in self._sound_mode_mapping.items()
        }

        self._hdmi_output_mapping = LEGACY_HDMI_OUTPUT_MAPPING
        self._rev_hdmi_output_mapping = LEGACY_REV_HDMI_OUTPUT_MAPPING

        self._attr_sound_mode_list = list(self._rev_sound_mode_mapping)

        self._attr_supported_features = SUPPORTED_FEATURES_BASE
        self._tunein = TuneIn(manager, self._set_network_title) if tunein_supported else None
        # DAB+ and the FM station book always act on the main zone, so only the
        # main-zone player offers them.
        self._fm = fm_stations if zone is Zone.MAIN else None
        self._dab = dab_radio if zone is Zone.MAIN else None
        if self._tunein is not None:
            self._attr_supported_features |= (
                MediaPlayerEntityFeature.BROWSE_MEDIA | MediaPlayerEntityFeature.SEARCH_MEDIA
            )
        if zone is Zone.MAIN:
            self._attr_supported_features |= SUPPORTED_FEATURES_VOLUME
            self._supports_volume = True
            self._attr_supported_features |= MediaPlayerEntityFeature.SELECT_SOUND_MODE
            self._supports_sound_mode = True
        elif Code.get_from_kind_zone(Kind.LISTENING_MODE, zone) is not None:
            # To be detected later:
            self._supports_sound_mode = False

        self._attr_extra_state_attributes = {}

    @override
    async def async_added_to_hass(self) -> None:
        """Entity has been added to hass."""
        if self._fm is not None:
            self._fm.listeners.append(self.async_write_ha_state)
            self.async_on_remove(lambda: self._fm.listeners.remove(self.async_write_ha_state))
        await self.query_state()

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Entity will be removed from hass."""
        self.cancel_pending()

    @property
    @override
    def available(self) -> bool:
        """Return if entity is available."""
        return self._manager.connected

    @property
    def media_title(self) -> str | None:
        """Prefer track metadata; otherwise identify the actual tuned station."""
        if self.state == MediaPlayerState.OFF:
            return None
        if self._attr_media_title:
            return self._attr_media_title
        if self._current_source == InputSource.DAB:
            return self._tuner_station_name
        if self._current_source == InputSource.FM and self._fm_frequency is not None:
            if self._fm is not None:
                for station in self._fm.stations:
                    if round(float(station["freq"]) * 100) == self._fm_frequency:
                        return str(station["name"])
            for preset in getattr(self._manager, "presets", {}).values():
                if preset.get("freq") == self._fm_frequency and preset.get("name"):
                    return str(preset["name"])
            return f"FM {self._fm_frequency / 100:g} MHz"
        return None

    def update_tuner_media(self, code: bytes, parameter: bytes) -> None:
        """Receive station metadata without stealing a NET track title."""
        if code == b"DSN" and self._current_source == InputSource.DAB:
            self._tuner_station_name = parameter.decode("utf-8", "replace").strip() or None
        elif code == b"TUN" and self._current_source == InputSource.FM:
            if not parameter.isdigit():
                return
            self._fm_frequency = int(parameter)
        else:
            return
        if self.hass is not None and self.enabled:
            self.async_write_ha_state()

    async def query_state(self) -> None:
        """Query the receiver for all the info, that we care about."""
        await self._manager.write(query.Power(self._zone))
        await self._manager.write(query.Volume(self._zone))
        await self._manager.write(query.Muting(self._zone))
        await self._manager.write(query.InputSource(self._zone))
        await self._manager.write(query.TunerPreset(self._zone))
        if self._supports_sound_mode is not None:
            await self._manager.write(query.ListeningMode(self._zone))
        if self._zone is Zone.MAIN:
            await self._manager.write(query.HDMIOutput())
            await self._manager.write(query.AudioInformation())
            await self._manager.write(query.VideoInformation())

    def cancel_pending(self) -> None:
        """Cancel the pending work."""
        self._cancel_ramp()
        self._device_volume = None
        if self._net_meta_unsub is not None:
            self._net_meta_unsub()
            self._net_meta_unsub = None
        if self._query_state_unsub is not None:
            self._query_state_unsub()
            self._query_state_unsub = None
        if self._query_av_info_unsub is not None:
            self._query_av_info_unsub()
            self._query_av_info_unsub = None

    @override
    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        message = command.Power(self._zone, command.Power.Param.ON)
        await self._manager.write(message)

    @override
    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        self._cancel_ramp()
        message = command.Power(self._zone, command.Power.Param.STANDBY)
        await self._manager.write(message)

    @property
    def _volume_limit(self) -> int:
        return int(self._volume_resolution * self._max_volume / 100)

    def _cancel_ramp(self) -> None:
        if self._ramp_task is not None:
            self._ramp_task.cancel()
            self._ramp_task = None
            self._publish_confirmed_volume()

    @callback
    def _publish_confirmed_volume(self) -> None:
        """Release the actual level to HA when the slider can accept feedback."""
        if self._device_volume is None:
            return
        volume_level = min(
            1, self._device_volume / (self._volume_resolution * self._max_volume / 100)
        )
        if self._attr_volume_level != volume_level:
            self._attr_volume_level = volume_level
            self.async_write_ha_state()

    @staticmethod
    async def _wait_for_volume_step(
        reports: asyncio.Queue[int], expected: int, timeout: float
    ) -> None:
        """Wait for the requested level, ignoring delayed replies for other levels."""
        async with asyncio.timeout(timeout):
            while await reports.get() != expected:
                pass

    async def _confirm_volume_step(
        self, reports: asyncio.Queue[int], expected: int
    ) -> None:
        """Recheck the current level before stopping for an inconsistent report."""
        await self._manager.write(query.Volume(self._zone))
        await self._wait_for_volume_step(reports, expected, VOLUME_QUERY_TIMEOUT)

    async def _run_volume_ramp(self) -> None:
        """Take one device step at a time and stop on missing or unexpected feedback."""
        next_level = None
        try:
            # Give the stock slider time to finish sending its drag/release events
            # before the receiver can report its first intermediate step.
            await asyncio.sleep(VOLUME_UI_FEEDBACK_PAUSE)
            while (
                self._manager.connected
                and self.state == MediaPlayerState.ON
                and (current := self._device_volume) is not None
                and current != self._ramp_target
            ):
                next_level = current + (1 if current < self._ramp_target else -1)
                # If the user raised volume outside HA above the configured limit,
                # do not send any target above that limit, even on the way down.
                next_level = min(next_level, self._volume_limit)
                loop = asyncio.get_running_loop()
                deadline = loop.time() + self._ramp_delay
                reports: asyncio.Queue[int] = asyncio.Queue()
                self._volume_reports = reports
                try:
                    await self._manager.write(command.Volume(self._zone, next_level))
                    try:
                        await self._wait_for_volume_step(
                            reports, next_level, VOLUME_PUSH_TIMEOUT
                        )
                    except TimeoutError:
                        await self._confirm_volume_step(reports, next_level)
                    if next_level != self._ramp_target:
                        await asyncio.sleep(max(0, deadline - loop.time()))
                    if self._device_volume != next_level:
                        while not reports.empty():
                            reports.get_nowait()
                        await self._confirm_volume_step(reports, next_level)
                finally:
                    if self._volume_reports is reports:
                        self._volume_reports = None
        except TimeoutError:
            _LOGGER.warning(
                "Onkyo volume ramp stopped: step %s not confirmed "
                "(last report %s, target %s)",
                next_level,
                self._device_volume,
                self._ramp_target,
            )
        except OSError as err:
            _LOGGER.warning("Onkyo volume ramp stopped: %s", err)
        finally:
            if self._ramp_task is asyncio.current_task():
                self._ramp_task = None
                self._publish_confirmed_volume()

    @override
    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1.

        However full volume on the amp is usually far too loud so allow the user to
        specify the upper range with CONF_MAX_VOLUME. We change as per max_volume
        set by user. This means that if max volume is 80 then full volume in HA
        will give 80% volume on the receiver. Then we convert that to the correct
        scale for the receiver.
        """
        # HA_VOL * (MAX VOL / 100) * VOL_RESOLUTION
        value = max(
            0,
            min(
                round(volume * (self._max_volume / 100) * self._volume_resolution),
                self._volume_limit,
            ),
        )
        _LOGGER.debug(
            "%s volume_set: requested=%.4f device_target=%d current=%s "
            "ramp=%s previous_target=%s",
            self.entity_id,
            volume,
            value,
            self._device_volume,
            self._ramp_enabled,
            self._ramp_target if self._ramp_task is not None else None,
        )
        if not self._ramp_enabled:
            await self._manager.write(command.Volume(self._zone, value))
            return
        if self.state != MediaPlayerState.ON or self._device_volume is None:
            raise HomeAssistantError("The receiver must report its current volume first.")
        self._ramp_target = value
        self._volume_ui_feedback_after = (
            asyncio.get_running_loop().time() + VOLUME_UI_FEEDBACK_PAUSE
        )
        if self._ramp_task is None:
            self._ramp_task = self._manager.entry.async_create_background_task(
                self.hass, self._run_volume_ramp(), f"volume_ramp_{self._zone.value}"
            )

    @override
    async def async_volume_up(self) -> None:
        """Increase volume by 1 step."""
        _LOGGER.debug("%s volume_up: current=%s", self.entity_id, self._device_volume)
        self._cancel_ramp()
        if self._device_volume is not None and self._device_volume < self._volume_limit:
            await self._manager.write(
                command.Volume(self._zone, self._device_volume + 1)
            )

    @override
    async def async_volume_down(self) -> None:
        """Decrease volume by 1 step."""
        _LOGGER.debug("%s volume_down: current=%s", self.entity_id, self._device_volume)
        self._cancel_ramp()
        message = command.Volume(self._zone, command.Volume.Param.DOWN)
        await self._manager.write(message)

    @override
    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        message = command.Muting(
            self._zone, command.Muting.Param.ON if mute else command.Muting.Param.OFF
        )
        await self._manager.write(message)

    @override
    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        selected = self._rev_source_mapping.get(
            source,
            self._unprefixed_source_mapping.get(source, self._original_source_mapping.get(source)),
        )
        if selected is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_source",
                translation_placeholders={
                    "invalid_source": source,
                    "entity_id": self.entity_id,
                },
            )

        message = command.InputSource(self._zone, selected)
        await self._manager.write(message)

    def _set_source_mapping(self, sources: dict[InputSource, str]) -> None:
        zone_sources = InputSource.for_zone(self._zone)
        self._source_mapping = {
            key: value for key, value in sources.items() if key in zone_sources
        }
        self._rev_source_mapping = {
            value: key for key, value in self._source_mapping.items()
        }
        self._attr_source_list = list(self._rev_source_mapping)

    @callback
    def update_source_names(
        self,
        sources: dict[InputSource, str],
        unprefixed_sources: dict[InputSource, str] | None = None,
    ) -> None:
        """Update the selectable labels and current label without switching inputs."""
        self._set_source_mapping(sources)
        self._unprefixed_source_mapping = {
            name: source
            for source, name in (unprefixed_sources or {}).items()
            if source in self._source_mapping
        }
        if self._current_source is not None:
            self._attr_source = self._source_mapping.get(
                self._current_source, get_meaning(self._current_source)
            )
        if self.hass is not None and self.enabled:
            self.async_write_ha_state()

    @override
    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select listening sound mode."""
        if sound_mode not in self._rev_sound_mode_mapping:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_sound_mode",
                translation_placeholders={
                    "invalid_sound_mode": sound_mode,
                    "entity_id": self.entity_id,
                },
            )

        message = command.ListeningMode(
            self._zone, self._rev_sound_mode_mapping[sound_mode]
        )
        await self._manager.write(message)

    async def async_select_output(self, hdmi_output: str) -> None:
        """Set hdmi-out."""
        message = command.HDMIOutput(self._rev_hdmi_output_mapping[hdmi_output])
        await self._manager.write(message)

    @override
    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play internet radio, tuner presets or a hardware tuner frequency."""
        if media_type == TUNEIN_CONTENT_TYPE and self._tunein is not None:
            if self.state != MediaPlayerState.ON:
                raise HomeAssistantError("Turn on the receiver before playing TuneIn.")
            await self._tunein.play(media_id)
            return
        if media_type == DAB_CONTENT_TYPE and self._dab is not None:
            if self.state != MediaPlayerState.ON:
                raise HomeAssistantError("Turn on the receiver before playing DAB+.")
            await self._dab.async_play(media_id.removeprefix("dab:"))
            return
        if media_type == FM_CONTENT_TYPE and self._fm is not None:
            if self.state != MediaPlayerState.ON:
                raise HomeAssistantError("Turn on the receiver before playing FM.")
            value = media_id.removeprefix("fm:")
            if value.startswith("station:"):
                await self._fm.async_play(value)
                return
            try:
                index = int(value)
            except ValueError as err:
                raise HomeAssistantError("Invalid FM station.") from err
            await self._fm.async_play(index)
            return
        if media_type.lower() != "radio":
            # Stream URLs are not an eISCP capability; HA's Cast player for
            # this receiver handles them. Fail loudly instead of ignoring.
            raise ServiceValidationError(
                f"{self.entity_id} cannot play {media_type} media. Cast or AirPlay "
                "the URL to this receiver's Google Cast player instead."
            )
        if self.source is None:
            return

        source = self._rev_source_mapping.get(self.source)
        if source not in PLAYABLE_SOURCES:
            raise ServiceValidationError(
                f"{self.entity_id} can only play tuner presets while FM/AM/DAB "
                f"is selected, not while {self.source} is active."
            )

        message = command.TunerPreset(self._zone, int(media_id))
        await self._manager.write(message)

    @callback
    def _set_network_title(self, title: str | None) -> None:
        """Expose the TuneIn station without changing the zone's power state."""
        self._attr_media_title = title
        if self.hass is not None and self.enabled:
            self.async_write_ha_state()

    def _clear_net_media(self) -> None:
        """Drop NET playback metadata, e.g. after leaving NET or standby."""
        self._attr_media_title = None
        self._attr_media_artist = None
        self._attr_media_album_name = None
        self._attr_media_image_url = None
        self._attr_media_image_hash = None

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Proxy the AVR's artwork, stripping its nonstandard CGI preamble."""
        if self.media_image_url is None:
            return None, None
        return await async_fetch_artwork(self.hass, self.media_image_url)

    def update_net_media(self, code: bytes, parameter: bytes) -> None:
        """Apply raw NET metadata reported by the main zone."""
        text = parameter.decode("utf-8", "replace").strip()
        if self._current_source != NET:
            return
        if code == b"NTI":
            if self._current_source != NET:
                return
            self._attr_media_title = text or None
            self._attr_media_image_hash = str(monotonic_ns())
            # The receiver serves the current artwork anonymously on this URL.
            self._attr_media_image_url = (
                f"http://{self._manager.info.host}/album_art.cgi" if text else None
            )
            # Do not query NTI again in response to NTI: that creates an
            # endless metadata polling loop on the shared connection.
        elif code == b"NAT":
            self._attr_media_artist = text or None
        elif code == b"NAL":
            self._attr_media_album_name = text or None
        elif code == b"NJA":
            # NJA can be "LINK" or "2-http://host/album_art.cgi".
            # Always use our own receiver endpoint, not a received arbitrary URL.
            self._attr_media_image_url = f"http://{self._manager.info.host}/album_art.cgi"
            self._attr_media_image_hash = str(monotonic_ns())
        if self.hass is not None and self.enabled:
            self.async_write_ha_state()

    def _schedule_net_meta_query(self) -> None:
        """Fetch title, artist, album and artwork after the receiver settles."""
        if self._net_meta_unsub is not None:
            self._net_meta_unsub()
            self._net_meta_unsub = None

        async def _query(_now: datetime) -> None:
            self._net_meta_unsub = None
            if (self._manager.connected and self.state == MediaPlayerState.ON
                    and self._current_source == NET):
                for code in NET_META_CODES:
                    await self._manager.write(RawInstruction(code, b"QSTN"))

        self._net_meta_unsub = async_call_later(self.hass, 0.8, _query)

    @override
    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Show receiver-reported TuneIn categories and stations in HA."""
        if self._tunein is None:
            raise BrowseError("TuneIn browsing is unavailable on this receiver.")
        if not media_content_id:
            root = self._tunein.root()
            if self._dab is not None:
                root.children.append(BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=DAB_ROOT_ID,
                    media_content_type=DAB_CONTENT_TYPE,
                    title="DAB+ Radio",
                    can_play=False,
                    can_expand=True,
                    can_search=True,
                ))
            if self._fm is not None:
                root.children.append(BrowseMedia(
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=FM_ROOT_ID,
                    media_content_type=FM_CONTENT_TYPE,
                    title="FM Radio (own list)",
                    can_play=False,
                    can_expand=True,
                    can_search=True,
                ))
            return root
        if media_content_type == DAB_CONTENT_TYPE and self._dab is not None:
            if self.state != MediaPlayerState.ON:
                raise BrowseError("Turn on the receiver before opening DAB+.")
            try:
                return await self._dab.async_browse(media_content_id)
            except HomeAssistantError as err:
                raise BrowseError(str(err)) from err
        if media_content_type == FM_CONTENT_TYPE and self._fm is not None:
            # The FM station book lives in Home Assistant, not on the
            # receiver, so browsing it works while the receiver is off.
            return await self._fm.async_browse()
        if media_content_type != TUNEIN_CONTENT_TYPE:
            raise BrowseError("Unsupported media type.")
        if self.state != MediaPlayerState.ON:
            raise BrowseError("Turn on the receiver before opening TuneIn.")
        try:
            return await self._tunein.browse(media_content_id)
        except HomeAssistantError as err:
            raise BrowseError(str(err)) from err

    @override
    async def async_search_media(self, query: SearchMediaQuery) -> SearchMedia:
        """Search the current TuneIn category, DAB+ services or the FM book."""
        if query.media_content_type == FM_CONTENT_TYPE and self._fm is not None:
            return SearchMedia(result=(await self._fm.async_search(query.search_query)).children)
        if query.media_content_type == DAB_CONTENT_TYPE and self._dab is not None:
            try:
                return SearchMedia(result=(await self._dab.async_search(
                    query.search_query, query.media_content_id or DAB_ROOT_ID
                )).children)
            except HomeAssistantError as err:
                raise SearchError(str(err)) from err
        if self._tunein is None or self.state != MediaPlayerState.ON:
            raise SearchError("Turn on a TuneIn-capable receiver before searching.")
        if query.media_content_type not in (None, "", TUNEIN_CONTENT_TYPE):
            raise SearchError("Unsupported TuneIn search scope.")
        try:
            return await self._tunein.search(query.media_content_id, query.search_query)
        except HomeAssistantError as err:
            raise SearchError(str(err)) from err

    def process_update(self, message: status.Known) -> None:
        """Process update."""
        match message:
            case status.Power(param=status.Power.Param.ON):
                if self.state != MediaPlayerState.ON:
                    self._query_state_delayed()
                self._attr_state = MediaPlayerState.ON
            case status.Power(param=status.Power.Param.STANDBY):
                self._cancel_ramp()
                self._device_volume = None
                self._clear_net_media()
                self._attr_state = MediaPlayerState.OFF

            case status.Volume(param=volume):
                self._device_volume = volume
                if self._volume_reports is not None:
                    self._volume_reports.put_nowait(volume)
                if not self._supports_volume:
                    self._attr_supported_features |= SUPPORTED_FEATURES_VOLUME
                    self._supports_volume = True
                # During a gesture, the stock slider can echo its displayed
                # value as a fresh target. Resume live feedback after a short
                # gap in target requests, not just at the end of the ramp.
                if (
                    self._ramp_task is None
                    or asyncio.get_running_loop().time()
                    >= self._volume_ui_feedback_after
                ):
                    self._attr_volume_level = min(
                        1, volume / (self._volume_resolution * self._max_volume / 100)
                    )

            case status.Muting(param=muting):
                self._attr_is_volume_muted = bool(muting is status.Muting.Param.ON)

            case status.InputSource(param=source):
                if source != self._current_source:
                    self._tuner_station_name = None
                    self._fm_frequency = None
                self._current_source = source
                if source != NET:
                    self._clear_net_media()
                else:
                    self._schedule_net_meta_query()
                if source in self._source_mapping:
                    self._attr_source = self._source_mapping[source]
                else:
                    source_meaning = get_meaning(source)
                    _LOGGER.warning(
                        'Input source "%s" for entity: %s is not'
                        " in the list. Check integration options",
                        source_meaning,
                        self.entity_id,
                    )
                    self._attr_source = source_meaning

                self._query_av_info_delayed()

            case status.ListeningMode(param=sound_mode):
                if not self._supports_sound_mode:
                    self._attr_supported_features |= (
                        MediaPlayerEntityFeature.SELECT_SOUND_MODE
                    )
                    self._supports_sound_mode = True

                if sound_mode in self._sound_mode_mapping:
                    self._attr_sound_mode = self._sound_mode_mapping[sound_mode]
                else:
                    sound_mode_meaning = get_meaning(sound_mode)
                    _LOGGER.warning(
                        'Listening mode "%s" for entity: %s is'
                        " not in the list. Check integration"
                        " options",
                        sound_mode_meaning,
                        self.entity_id,
                    )
                    self._attr_sound_mode = sound_mode_meaning

                self._query_av_info_delayed()

            case status.HDMIOutput(param=hdmi_output):
                self._attr_extra_state_attributes[ATTR_VIDEO_OUT] = (
                    self._hdmi_output_mapping[hdmi_output]
                )
                self._query_av_info_delayed()

            case status.TunerPreset(param=preset):
                self._attr_extra_state_attributes[ATTR_PRESET] = preset

            case status.AudioInformation():
                self._supports_audio_info = True
                audio_information = {}
                for item in AUDIO_INFORMATION_MAPPING:
                    item_value = getattr(message, item)
                    if item_value is not None:
                        audio_information[item] = item_value
                self._attr_extra_state_attributes[ATTR_AUDIO_INFORMATION] = (
                    audio_information
                )

            case status.VideoInformation():
                self._supports_video_info = True
                video_information = {}
                for item in VIDEO_INFORMATION_MAPPING:
                    item_value = getattr(message, item)
                    if item_value is not None:
                        video_information[item] = item_value
                self._attr_extra_state_attributes[ATTR_VIDEO_INFORMATION] = (
                    video_information
                )

            case status.FLDisplay():
                self._query_av_info_delayed()

            case status.NotAvailable(kind=Kind.AUDIO_INFORMATION):
                # Not available right now, but still supported
                self._supports_audio_info = True

            case status.NotAvailable(kind=Kind.VIDEO_INFORMATION):
                # Not available right now, but still supported
                self._supports_video_info = True

        self.async_write_ha_state()

    def _query_state_delayed(self) -> None:
        if self._query_state_unsub is not None:
            self._query_state_unsub()
            self._query_state_unsub = None

        async def coro(_now: datetime) -> None:
            self._query_state_unsub = None
            await self.query_state()

        self._query_state_unsub = async_call_later(self.hass, QUERY_STATE_DELAY, coro)

    def _query_av_info_delayed(self) -> None:
        if self._zone is not Zone.MAIN or self._query_av_info_unsub is not None:
            return

        async def coro(_now: datetime) -> None:
            self._query_av_info_unsub = None
            if self._supports_audio_info:
                await self._manager.write(query.AudioInformation())
            if self._supports_video_info:
                await self._manager.write(query.VideoInformation())

        self._query_av_info_unsub = async_call_later(
            self.hass, QUERY_AV_INFO_DELAY, coro
        )
