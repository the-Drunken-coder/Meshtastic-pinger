from datetime import datetime, timezone

from meshtastic_pinger.gps import GpsFix, parse_nmea_sentence


def test_parse_valid_gga_sentence() -> None:
    sentence = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
    fix = parse_nmea_sentence(sentence)

    assert isinstance(fix, GpsFix)
    assert abs(fix.lat - 48.1173) < 1e-6
    assert abs(fix.lon - 11.5166667) < 1e-6
    assert fix.satellites == 8
    assert fix.hdop is not None
    assert fix.fix_quality == 1
    assert isinstance(fix.timestamp, datetime)
    assert fix.timestamp.tzinfo == timezone.utc


def test_parse_invalid_status_returns_none() -> None:
    sentence = "$GPRMC,123519,V,4807.038,N,01131.000,E,0.0,0.0,200520,,,N*53"
    assert parse_nmea_sentence(sentence) is None

