"""Codec for the TX-NR6050 temporary subwoofer level."""

import re

MIN_LEVEL = -15.0
MAX_LEVEL = 12.0
LEVEL_STEP = 0.5


def decode_level(parameter: bytes) -> float | None:
    """Decode signed hexadecimal half-dB units."""
    if not re.fullmatch(rb"(?:[+-][0-9A-Fa-f]{2}|0{2,3})", parameter):
        return None
    level = int(parameter, 16) / 2
    return level if MIN_LEVEL <= level <= MAX_LEVEL else None


def encode_level(level: float) -> bytes:
    """Encode a valid half-dB setpoint."""
    if not MIN_LEVEL <= level <= MAX_LEVEL or level * 2 != round(level * 2):
        raise ValueError("Expected -15 to +12 dB in 0.5 dB steps.")
    return f"{round(level * 2):+03X}".encode("ascii")
