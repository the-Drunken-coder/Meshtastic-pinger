from datetime import datetime, timezone

import pytest
from meshtastic import BROADCAST_ADDR
from meshtastic.protobuf import config_pb2

from meshtastic_pinger.gps import GpsFix
from meshtastic_pinger.radio import (
    build_message,
    resolve_destination,
    resolve_radio_mode,
)


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

