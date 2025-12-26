from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from serial.tools import list_ports

GPS_KEYWORDS = ["gps", "gnss", "nmea", "ublox", "beidou"]
RADIO_KEYWORDS = ["meshtastic", "ttgo", "t-beam", "esp32", "usb serial", "cp210", "ch340"]


def _normalize_device(device: str) -> str:
    return device.lower()


def _port_haystack(port: list_ports.ListPortInfo) -> str:
    haystack = " ".join(
        filter(
            None,
            (
                port.description,
                port.manufacturer,
                port.product,
                port.hwid,
            ),
        )
    )
    return haystack.lower()


def _list_ports() -> List[list_ports.ListPortInfo]:
    return list(list_ports.comports())


def find_port_by_keywords(
    keywords: Sequence[str], exclude_ports: Iterable[str] | None = None
) -> Optional[str]:
    exclude = {bee.lower() for bee in exclude_ports or set()}
    for port in _list_ports():
        if _normalize_device(port.device) in exclude:
            continue
        haystack = _port_haystack(port)
        if any(keyword in haystack for keyword in keywords):
            return port.device
    return None


def auto_detect_radio_port(exclude_ports: Iterable[str] | None = None) -> Optional[str]:
    exclude = {bee.lower() for bee in exclude_ports or set()}
    candidates = _list_ports()

    radio = find_port_by_keywords(RADIO_KEYWORDS, exclude)
    if radio:
        return radio

    for port in candidates:
        if _normalize_device(port.device) in exclude:
            continue
        haystack = _port_haystack(port)
        if any(keyword in haystack for keyword in GPS_KEYWORDS):
            continue
        return port.device
    return None

