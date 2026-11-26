"""Temporary subwoofer level for the Onkyo TX-NR6050."""

from datetime import datetime
from typing import TYPE_CHECKING

from aioonkyo import Status, Zone, query, status
from aioonkyo.instruction import RawInstruction

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfFrequency, UnitOfSoundPressure, UnitOfTime
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .extra_entity import OnkyoExtraEntity
from .extras import ReceiverExtras, integer_parameter
from .receiver import ReceiverManager
from .subwoofer import LEVEL_STEP, MAX_LEVEL, MIN_LEVEL, decode_level, encode_level

if TYPE_CHECKING:
    from . import OnkyoConfigEntry

SUBWOOFER_CODE = b"SWL"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OnkyoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the verified subwoofer control."""
    manager = entry.runtime_data.manager
    if manager.info.model_name.upper() == "TX-NR6050":
        async_add_entities([OnkyoSubwooferLevel(manager)])
    if (extras := entry.runtime_data.extras) is not None:
        async_add_entities(
            OnkyoReceiverNumber(extras, key, low, high, step, unit)
            for key, low, high, step, unit in (
                ("bass", -10, 10, 1, UnitOfSoundPressure.DECIBEL),
                ("treble", -10, 10, 1, UnitOfSoundPressure.DECIBEL),
                ("vocal", 0, 5, 1, None),
                ("dts_dialog", 0, 6, 1, UnitOfSoundPressure.DECIBEL),
                ("av_sync", 0, 500, 5, UnitOfTime.MILLISECONDS),
                ("sleep_timer", 0, 90, 1, UnitOfTime.MINUTES),
                ("tuner_preset", 1, 40, 1, None),
                ("fm_frequency", 87.5, 108.0, 0.05, UnitOfFrequency.MEGAHERTZ),
            )
        )


class OnkyoReceiverNumber(OnkyoExtraEntity, NumberEntity):
    """Number control backed by receiver status."""

    _attr_mode = NumberMode.BOX

    def __init__(
        self, extras: ReceiverExtras, key: str, low: float, high: float,
        step: float, unit: str | None,
    ) -> None:
        super().__init__(extras, key)
        self._attr_native_min_value = low
        self._attr_native_max_value = high
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> float | None:
        value = self._extras.values.get(self._key)
        return value if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        try:
            parameter = integer_parameter(
                self._key, value, self.native_min_value, self.native_max_value, self.native_step
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await self._extras.set(self._key, parameter)


class OnkyoSubwooferLevel(NumberEntity):
    """Track the receiver's reported temporary subwoofer level."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfSoundPressure.DECIBEL
    _attr_native_min_value = MIN_LEVEL
    _attr_native_max_value = MAX_LEVEL
    _attr_native_step = LEVEL_STEP
    _attr_translation_key = "subwoofer_level"
    _attr_icon = "mdi:speaker"

    def __init__(self, manager: ReceiverManager) -> None:
        """Initialize the entity."""
        self._manager = manager
        self._attr_device_info = manager.device_info
        self._attr_unique_id = f"{manager.info.identifier}_subwoofer_temporary_level"
        self._powered = False
        self._cancel_query: CALLBACK_TYPE | None = None

    @property
    def available(self) -> bool:
        """Only show a setpoint when the receiver reports the live level."""
        return (
            self._manager.connected
            and self._powered
            and self.native_value is not None
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to receiver events before the first power report."""
        callbacks = self._manager.callbacks
        for entries, handler in (
            (callbacks.connect, self._on_connect),
            (callbacks.disconnect, self._on_disconnect),
            (callbacks.update, self._on_update),
        ):
            entries.append(handler)
            self.async_on_remove(
                lambda entries=entries, handler=handler: (
                    entries.remove(handler) if handler in entries else None
                )
            )
        if self._manager.connected:
            await self._manager.write(query.Power(Zone.MAIN))

    async def async_will_remove_from_hass(self) -> None:
        """Cancel a deferred query."""
        self._cancel_pending_query()

    async def _on_connect(self, _: bool) -> None:
        """The manager queries power on every connection."""
        self._powered = False
        self._attr_native_value = None

    async def _on_disconnect(self) -> None:
        self._cancel_pending_query()
        self._powered = False
        self._attr_native_value = None
        self.async_write_ha_state()

    def _cancel_pending_query(self) -> None:
        if self._cancel_query is not None:
            self._cancel_query()
            self._cancel_query = None

    async def _query_after_power_on(self, _: datetime) -> None:
        self._cancel_query = None
        if self._manager.connected and self._powered:
            await self._manager.write(RawInstruction(SUBWOOFER_CODE, b"QSTN"))

    async def _on_update(self, message: Status) -> None:
        if isinstance(message, status.Power) and message.zone is Zone.MAIN:
            powered = message.param is status.Power.Param.ON
            if powered != self._powered:
                self._cancel_pending_query()
                self._powered = powered
                self._attr_native_value = None
                self.async_write_ha_state()
                if powered:
                    self._cancel_query = async_call_later(
                        self.hass, 1, self._query_after_power_on
                    )
        elif (
            self._powered
            and isinstance(message, status.Raw)
            and message.raw_code == SUBWOOFER_CODE
        ):
            self._attr_native_value = decode_level(message.parameter)
            self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Write the requested temporary level without inventing its state."""
        if not self.available:
            raise HomeAssistantError("The receiver has not reported a subwoofer level.")
        try:
            parameter = encode_level(value)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await self._manager.write(RawInstruction(SUBWOOFER_CODE, parameter))
