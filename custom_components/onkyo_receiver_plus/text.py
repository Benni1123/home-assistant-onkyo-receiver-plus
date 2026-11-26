"""Radio name editor on the receiver device page."""

from .radio_controls import FmName


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.runtime_data.fm is not None:
        async_add_entities([FmName(entry.runtime_data)])
