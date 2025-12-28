from datetime import datetime, timezone

import pytest
from meshtastic import BROADCAST_ADDR, LOCAL_ADDR
from meshtastic.protobuf import config_pb2

from meshtastic_pinger.gps import GpsFix
from meshtastic_pinger.radio import (
    build_message,
    MeshtasticClient,
    resolve_destination,
    resolve_radio_mode,
)


class FakeNode:
    def __init__(self, entry=None, node_num=None):
        self.entry = entry or {}
        self.nodeNum = node_num
        self.localConfig = config_pb2.Config()


class FakeSerialInterface:
    def __init__(self, devPath=None, **_):
        self.nodesByNum = {}
        self.nodesById = {}
        self.sent = []

    def getNode(self, node_id, requestChannels=False):
        entry = self.nodesById.get(node_id)
        if entry is None and isinstance(node_id, int):
            entry = self.nodesByNum.get(node_id)
        return FakeNode(entry)

    def sendText(self, message, destinationId=None, wantAck=True, portNum=None):
        self.sent.append(
            {
                "message": message,
                "destinationId": destinationId,
                "wantAck": wantAck,
                "portNum": portNum,
            }
        )
        return message

    def close(self):
        pass


def test_build_message_formats_values() -> None:
    fix = GpsFix(
        lat=12.34567,
        lon=-45.6789,
        timestamp=datetime(2025, 12, 25, 12, 0, tzinfo=timezone.utc),
        hdop=0.8,
        satellites=6,
        fix_quality=1,
    )
    template = "GPS {lat:.2f},{lon:.2f} sats {satellites} hdop {hdop}"
    message = build_message(template, fix)

    assert "12.35" in message
    assert "-45.68" in message
    assert "6" in message
    assert "0.8" in message


def test_build_message_unknown_key() -> None:
    fix = GpsFix(
        lat=0.0,
        lon=0.0,
        timestamp=datetime.now(timezone.utc),
        hdop=None,
        satellites=None,
        fix_quality=None,
    )
    with pytest.raises(ValueError):
        build_message("unknown {missing}", fix)


def test_resolve_destination_variants() -> None:
    assert resolve_destination("12345") == 12345
    assert resolve_destination("000BROADCAST") == "000BROADCAST"
    assert resolve_destination("broadcast") == BROADCAST_ADDR


def test_resolve_radio_mode_aliases_and_numbers() -> None:
    preset = config_pb2.Config.LoRaConfig.ModemPreset
    assert resolve_radio_mode("longfast") == preset.LONG_FAST
    assert resolve_radio_mode("Long-Fast") == preset.LONG_FAST
    assert resolve_radio_mode("mediumslow") == preset.MEDIUM_SLOW
    assert resolve_radio_mode("8") == preset.SHORT_TURBO
    assert resolve_radio_mode("") is None


def test_resolve_radio_mode_unknown_raises() -> None:
    with pytest.raises(ValueError):
        resolve_radio_mode("invalidpreset")


def test_build_message_includes_signal_strength() -> None:
    fix = GpsFix(
        lat=0.0,
        lon=0.0,
        timestamp=datetime.now(timezone.utc),
        hdop=None,
        satellites=None,
        fix_quality=None,
    )
    message = build_message("snr {snr}", fix, extra={"snr": -12.5})
    assert "snr -12.5" in message


def test_build_message_includes_radio_signal_strength() -> None:
    fix = GpsFix(
        lat=0.0,
        lon=0.0,
        timestamp=datetime.now(timezone.utc),
        hdop=None,
        satellites=None,
        fix_quality=None,
    )
    message = build_message("radio_snr {radio_snr}", fix, extra={"radio_snr": -3.2})
    assert "radio_snr -3.2" in message


def test_extract_snr_direct_value() -> None:
    assert MeshtasticClient._extract_snr({"snr": -12.5}) == -12.5


def test_extract_snr_from_last_received() -> None:
    entry = {"lastReceived": {"rxSnr": -7.0}}
    assert MeshtasticClient._extract_snr(entry) == -7.0


def test_extract_snr_preserves_zero_rx_snr() -> None:
    entry = {"lastReceived": {"rxSnr": 0.0, "snr": -5.0}}
    assert MeshtasticClient._extract_snr(entry) == 0.0


def test_extract_snr_unknown_value_returns_none() -> None:
    assert MeshtasticClient._extract_snr({"snr": -128}) is None


def test_resolve_destination_num_parses_hex_id() -> None:
    assert MeshtasticClient._resolve_destination_num("!9e9f370c") == 0x9E9F370C
    assert MeshtasticClient._resolve_destination_num("0x9e9f370c") == 0x9E9F370C
    assert MeshtasticClient._resolve_destination_num("broadcast") is None


def test_resolve_destination_num_excludes_reserved_addresses() -> None:
    assert MeshtasticClient._resolve_destination_num(BROADCAST_ADDR) is None
    assert MeshtasticClient._resolve_destination_num(LOCAL_ADDR) is None


def test_read_signal_strength_supports_alias(monkeypatch) -> None:
    fake_interface = FakeSerialInterface()
    fake_interface.nodesById["myradio"] = {"snr": -7.5}
    monkeypatch.setattr("meshtastic_pinger.radio.SerialInterface", lambda devPath=None, **kwargs: fake_interface)

    client = MeshtasticClient(target_node="myradio", device=None, radio_mode=None)

    assert client._read_signal_strength() == -7.5


def test_send_fix_formats_missing_signal(monkeypatch) -> None:
    fake_interface = FakeSerialInterface()
    monkeypatch.setattr("meshtastic_pinger.radio.SerialInterface", lambda devPath=None, **kwargs: fake_interface)

    fix = GpsFix(
        lat=1.0,
        lon=2.0,
        timestamp=datetime.now(timezone.utc),
        hdop=None,
        satellites=None,
        fix_quality=None,
    )
    client = MeshtasticClient(target_node="12345", device=None, radio_mode=None)

    client.send_fix(fix, "sig {snr:.1f} radio {radio_snr}")

    assert fake_interface.sent
    sent_message = fake_interface.sent[0]["message"]
    assert "sig n/a" in sent_message
    assert "radio n/a" in sent_message


def test_send_fix_appends_tx_timestamp(monkeypatch) -> None:
    fake_interface = FakeSerialInterface()
    monkeypatch.setattr(
        "meshtastic_pinger.radio.SerialInterface",
        lambda devPath=None, **kwargs: fake_interface,
    )

    fix = GpsFix(
        lat=1.0,
        lon=2.0,
        timestamp=datetime.now(timezone.utc),
        hdop=None,
        satellites=None,
        fix_quality=None,
    )
    client = MeshtasticClient(target_node="12345", device=None, radio_mode=None)

    client.send_fix(fix, "hello")

    assert fake_interface.sent
    sent_message = fake_interface.sent[0]["message"]
    assert "tx=" in sent_message
    tx_part = sent_message.rsplit("tx=", 1)[1].split()[0]
    assert float(tx_part) > 0
