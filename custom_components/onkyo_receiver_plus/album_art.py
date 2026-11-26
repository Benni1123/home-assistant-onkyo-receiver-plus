"""Fetch receiver artwork, including Onkyo's CGI headers inside the body."""

import asyncio
import logging

from aiohttp import ClientError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)
MAX_IMAGE = 5 * 1024 * 1024


def decode_artwork(data: bytes) -> tuple[bytes | None, str | None]:
    """Remove legacy CGI preamble and determine the actual image MIME type."""
    if data.lower().startswith((b"content-size:", b"content-type:")):
        for separator in (b"\r\n\r\n", b"\n\n"):
            marker = data.find(separator, 0, 1024)
            if marker >= 0:
                data = data[marker + len(separator):]
                break
    if len(data) > MAX_IMAGE:
        return None, None
    for magic, mime in ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png"),
                        (b"GIF8", "image/gif")):
        if data.startswith(magic):
            return data, mime
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return data, "image/webp"
    return None, None


async def async_fetch_artwork(hass, url: str):
    """Fetch a bounded image through HA; never expose receiver credentials."""
    try:
        async with asyncio.timeout(8):
            async with async_get_clientsession(hass).get(url) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE + 1024:
                        return None, None
                return decode_artwork(bytes(data))
    except (ClientError, TimeoutError, OSError):
        _LOGGER.debug("Receiver artwork unavailable", exc_info=True)
        return None, None
