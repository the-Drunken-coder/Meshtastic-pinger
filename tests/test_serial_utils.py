from serial.tools import list_ports

from meshtastic_pinger.serial_utils import (
    auto_detect_radio_port,
    find_port_by_keywords,
    GPS_KEYWORDS,
    RADIO_KEYWORDS,
)


class DummyPort:
    def __init__(
        self,
        device: str,
        description: str = "",
        manufacturer: str = "",
        product: str = "",
        hwid: str = "",
    ) -> None:
        self.device = device
        self.description = description
        self.manufacturer = manufacturer
        self.product = product
        self.hwid = hwid


def test_find_port_by_keywords_matches_keyword(monkeypatch) -> None:
    monkeypatch.setattr(
        list_ports,
        "comports",
        lambda: [
            DummyPort("COM1", description="USB GPS"),
            DummyPort("COM2", description="Meshtastic T-Beam"),
        ],
    )

    assert find_port_by_keywords(["t-beam"]) == "COM2"


def test_auto_detect_radio_port_prefers_radio_keyword(monkeypatch) -> None:
    monkeypatch.setattr(
        list_ports,
        "comports",
        lambda: [
            DummyPort("COM1", description="USB GPS"),
            DummyPort("COM2", description="Meshtastic Radio"),
        ],
    )

    assert auto_detect_radio_port() == "COM2"


def test_auto_detect_radio_port_skips_gps(monkeypatch) -> None:
    monkeypatch.setattr(
        list_ports,
        "comports",
        lambda: [
            DummyPort("COM1", description="GPS Module"),
            DummyPort("COM2", description="Generic USB Serial"),
        ],
    )

    assert auto_detect_radio_port() == "COM2"


def test_auto_detect_radio_port_respects_exclude(monkeypatch) -> None:
    monkeypatch.setattr(
        list_ports,
        "comports",
        lambda: [
            DummyPort("COM1", description="Meshtastic Radio"),
            DummyPort("COM2", description="GPS Module"),
        ],
    )

    assert auto_detect_radio_port(exclude_ports={"COM1"}) is None


def test_gps_keywords_present_in_module() -> None:
    assert "gps" in GPS_KEYWORDS


def test_radio_keywords_present_in_module() -> None:
    assert "meshtastic" in RADIO_KEYWORDS

