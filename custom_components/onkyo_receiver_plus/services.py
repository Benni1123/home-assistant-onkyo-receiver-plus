"""Onkyo services."""

from functools import partial

import probatio

from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, LEGACY_REV_HDMI_OUTPUT_MAPPING
from .media_player import DATA_MP_ENTITIES, DATA_RADIO, OnkyoMediaPlayer

ATTR_HDMI_OUTPUT = "hdmi_output"
ATTR_NAME = "name"
ATTR_FREQUENCY = "frequency"
ONKYO_SELECT_OUTPUT_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
        probatio.Required(ATTR_HDMI_OUTPUT): probatio.In(
            LEGACY_REV_HDMI_OUTPUT_MAPPING
        ),
    }
)
SERVICE_SELECT_HDMI_OUTPUT = "onkyo_receiver_plus_select_hdmi_output"
SERVICE_SAVE_FM_STATION = "save_fm_station"
SERVICE_DELETE_FM_STATION = "delete_fm_station"
SAVE_FM_STATION_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
        probatio.Required(ATTR_NAME): cv.string,
        probatio.Required(ATTR_FREQUENCY): probatio.Coerce(float),
    }
)
DELETE_FM_STATION_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_ENTITY_ID): cv.entity_ids,
        probatio.Required(ATTR_NAME): cv.string,
    }
)


def _resolve_fm_stations(hass: HomeAssistant, entity_ids: list[str]):
    """Find the FM station book for one of the targeted media players."""
    for entry_id, zones in hass.data.get(DATA_MP_ENTITIES, {}).items():
        if any(entity.entity_id in entity_ids for entity in zones.values()):
            radio = hass.data.get(DATA_RADIO, {}).get(entry_id)
            if radio is not None and radio[0] is not None:
                return radio[0]
    raise ServiceValidationError("No Onkyo Receiver Plus media player was targeted.")


async def _async_save_fm_station(hass: HomeAssistant, call: ServiceCall) -> None:
    fm = _resolve_fm_stations(hass, call.data[ATTR_ENTITY_ID])
    await fm.async_save_station(call.data[ATTR_NAME], call.data[ATTR_FREQUENCY])


async def _async_delete_fm_station(hass: HomeAssistant, call: ServiceCall) -> None:
    fm = _resolve_fm_stations(hass, call.data[ATTR_ENTITY_ID])
    await fm.async_delete_station(call.data[ATTR_NAME])


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register Onkyo services."""

    hass.data.setdefault(DATA_MP_ENTITIES, {})

    async def async_service_handle(service: ServiceCall) -> None:
        """Handle for services."""
        entity_ids = service.data[ATTR_ENTITY_ID]

        targets: list[OnkyoMediaPlayer] = []
        for receiver_entities in hass.data[DATA_MP_ENTITIES].values():
            targets.extend(
                entity
                for entity in receiver_entities.values()
                if entity.entity_id in entity_ids
            )

        for target in targets:
            if service.service == SERVICE_SELECT_HDMI_OUTPUT:
                await target.async_select_output(service.data[ATTR_HDMI_OUTPUT])

    hass.services.async_register(
        MEDIA_PLAYER_DOMAIN,
        SERVICE_SELECT_HDMI_OUTPUT,
        async_service_handle,
        schema=ONKYO_SELECT_OUTPUT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SAVE_FM_STATION, partial(_async_save_fm_station, hass), schema=SAVE_FM_STATION_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_FM_STATION,
        partial(_async_delete_fm_station, hass),
        schema=DELETE_FM_STATION_SCHEMA,
    )
