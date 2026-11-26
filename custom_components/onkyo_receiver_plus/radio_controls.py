"""Native device-page controls for the integration's radio lists."""

from homeassistant.components.button import ButtonEntity
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.components.select import SelectEntity
from homeassistant.components.text import TextEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfFrequency
from homeassistant.helpers.entity import Entity
from homeassistant.exceptions import HomeAssistantError

from .fm import normalize_frequency


class RadioControl(Entity):
    """Associate radio editing controls with the receiver device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, data, key):
        self.data = data
        self.fm = data.fm
        self._attr_translation_key = key
        self._attr_unique_id = f"{data.manager.info.identifier}_{key}"
        self._attr_device_info = data.manager.device_info

    async def async_added_to_hass(self):
        self.fm.listeners.append(self.async_write_ha_state)
        self.async_on_remove(lambda: self.fm.listeners.remove(self.async_write_ha_state))


class FmName(RadioControl, TextEntity):
    """Station name field (local draft, saved by the button)."""

    _attr_native_min = 0
    _attr_native_max = 64

    def __init__(self, data):
        super().__init__(data, "fm_station_name")

    @property
    def native_value(self):
        return self.fm.edit_name

    async def async_set_value(self, value):
        self.fm.edit_name = value
        self.fm.notify()


class FmFrequency(RadioControl, NumberEntity):
    """Frequency field for the station being edited, not a live tuner."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 87.5
    _attr_native_max_value = 108
    _attr_native_step = 0.05
    _attr_native_unit_of_measurement = UnitOfFrequency.MEGAHERTZ

    def __init__(self, data):
        super().__init__(data, "fm_station_frequency")

    @property
    def native_value(self):
        return self.fm.edit_frequency

    async def async_set_native_value(self, value):
        self.fm.edit_frequency = normalize_frequency(value)
        self.fm.notify()


class FmEditSelection(RadioControl, SelectEntity):
    """Load a saved station's fields for editing or deletion."""

    def __init__(self, data):
        super().__init__(data, "fm_station_edit")

    @property
    def options(self):
        return [str(station["name"]) for station in self.fm.stations]

    @property
    def current_option(self):
        return self.fm.edit_name if self.fm.edit_name in self.options else None

    async def async_select_option(self, option):
        for station in self.fm.stations:
            if station["name"] == option:
                self.fm.edit_name = option
                self.fm.edit_frequency = float(station["freq"])
                self.fm.notify()
                return
        raise HomeAssistantError("This station is no longer saved.")


class RadioButton(RadioControl, ButtonEntity):
    """Save/delete FM stations or explicitly read the DAB service list."""

    def __init__(self, data, action):
        super().__init__(data, action)
        self.action = action

    async def async_press(self):
        if self.action == "fm_station_save":
            await self.fm.async_save_station(self.fm.edit_name, self.fm.edit_frequency)
        elif self.action == "fm_station_delete":
            await self.fm.async_delete_station(self.fm.edit_name)
        else:
            if not self.data.manager.connected:
                raise HomeAssistantError("Turn on and connect the receiver first.")
            extras = getattr(self.data, "extras", None)
            if extras is not None and not extras.powered:
                raise HomeAssistantError("Turn on the receiver before reading DAB services.")
            if self.data.dab.enumerating:
                raise HomeAssistantError("The DAB list is already being read.")
            await self.data.dab.async_start_scan()


class DabScanStatus(RadioControl, SensorEntity):
    """Progress and actual error text for the background enumeration."""

    def __init__(self, data):
        super().__init__(data, "dab_scan_status")

    @property
    def native_value(self):
        return self.data.dab.scan_status[:255]

    async def async_added_to_hass(self):
        self.data.dab.listeners.append(self.async_write_ha_state)
        self.async_on_remove(
            lambda: self.data.dab.listeners.remove(self.async_write_ha_state)
        )
