"""Import the receiver's input labels from its eISCP device information."""

from xml.etree import ElementTree

from .const import InputSource
from .util import get_meaning

DEVICE_INFO_CODE = b"NRI"
HDMI_ASSIGNMENT_CODE = b"sHI"
HDMI_ASSIGNMENT_QUERY = b"CQSTN"

# Web Setup group selector keys mapped to the corresponding eISCP input IDs.
HDMI_ASSIGNMENT_INPUTS = {
    b"BD": InputSource("10"),
    b"CB": InputSource("01"),
    b"GM": InputSource("02"),
    b"ST": InputSource("11"),
    b"PC": InputSource("05"),
    b"CD": InputSource("23"),
    b"TV": InputSource("12"),
    b"AX": InputSource("03"),
    b"PH": InputSource("22"),
}


def _parse_device_xml(payload: bytes) -> ElementTree.Element | None:
    if len(payload) > 65536 or b"\0" in payload or b"<!" in payload:
        return None
    try:
        return ElementTree.fromstring(payload)
    except (ElementTree.ParseError, LookupError, ValueError):
        return None


def parse_firmware_version(payload: bytes) -> str | None:
    """Read the receiver's reported firmware version from NRI XML."""
    root = _parse_device_xml(payload)
    if root is None:
        return None
    return root.findtext("./device/firmwareversion", "").strip() or None


def parse_remote_menu_keys(payload: bytes) -> dict[str, bytes]:
    """Read the receiver's advertised OSD shortcuts without accepting arbitrary codes."""
    root = _parse_device_xml(payload)
    if root is None:
        return {}
    supported = {
        control.get("id"): control.get("code", "").upper()
        for control in root.findall("./device/controllist/control")
        if control.get("value") == "1"
    }
    keys = {}
    for key, candidates, allowed in (
        ("setup", ("Setup", "Menu", "Home"), {"MENU", "HOME"}),
        ("quick_menu", ("Quick", "AV Adjust"), {"QUICK", "AUDIO"}),
    ):
        for candidate in candidates:
            if (code := supported.get(candidate)) in allowed:
                keys[key] = code.encode("ascii")
                break
    return keys


def parse_input_names(payload: bytes) -> dict[InputSource, str]:
    """Read enabled, recognized selectors from the receiver's XML reply."""
    root = _parse_device_xml(payload)
    if root is None:
        return {}

    names = {}
    for selector in root.findall("./device/selectorlist/selector"):
        if selector.get("value") != "1":
            continue
        name = selector.get("name", "").strip()
        code = selector.get("id", "").upper()
        if not name:
            continue
        try:
            names[InputSource(code)] = name
        except ValueError:
            continue
    return names


def apply_input_names(
    configured: dict[InputSource, str], reported: dict[InputSource, str]
) -> dict[InputSource, str]:
    """Replace default names only; preserve selection and avoid duplicate labels."""
    names = configured.copy()
    occupied = {label.casefold() for label in configured.values()}
    for source, original in configured.items():
        proposed = reported.get(source)
        if original == get_meaning(source) and proposed:
            if proposed.casefold() in occupied and proposed.casefold() != original.casefold():
                continue
            names[source] = proposed
            occupied.add(proposed.casefold())
    return names


def parse_hdmi_assignments(payload: bytes) -> dict[InputSource, int] | None:
    """Decode the TX-NR6050 HDMI assignment group, or ignore malformed replies."""
    if not payload.startswith(b"C") or len(payload) < 6 or (len(payload) - 1) % 5:
        return None
    assignments = {}
    for offset in range(1, len(payload), 5):
        source = HDMI_ASSIGNMENT_INPUTS.get(payload[offset : offset + 2])
        port = payload[offset + 2 : offset + 5]
        if source is not None and port[:2] == b"HI" and port[2:] in {
            b"1", b"2", b"3", b"4", b"5", b"6",
        }:
            assignments[source] = int(port[2:])
    return assignments


def add_hdmi_prefixes(
    names: dict[InputSource, str], ports: dict[InputSource, int]
) -> dict[InputSource, str]:
    """Add known port numbers without overwriting explicit HDMI labels."""
    result = names.copy()
    occupied = {name.casefold() for name in names.values()}
    for source, name in names.items():
        if (port := ports.get(source)) is None or name.casefold().startswith("hdmi "):
            continue
        label = f"HDMI {port} / {name}"
        if label.casefold() not in occupied:
            result[source] = label
            occupied.add(label.casefold())
    return result
