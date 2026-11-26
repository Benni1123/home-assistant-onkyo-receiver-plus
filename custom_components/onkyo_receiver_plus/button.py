"""Radio management buttons on the receiver device page."""

from .radio_controls import RadioButton


async def async_setup_entry(hass, entry, async_add_entities):
    data = entry.runtime_data
    if data.fm is not None:
        actions = ["fm_station_save", "fm_station_delete"]
        if data.dab is not None:
            actions.append("dab_read_services")
        async_add_entities([RadioButton(data, action) for action in actions])
