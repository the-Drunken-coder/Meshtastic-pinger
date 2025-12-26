from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional, Set

import pynmea2
import serial

from .serial_utils import GPS_KEYWORDS, find_port_by_keywords

logger = logging.getLogger(__name__)

DEFAULT_GPS_BAUDRATE = 9600


@dataclass(frozen=True)
class GpsFix:
    lat: float
    lon: float
    timestamp: datetime.datetime
    hdop: Optional[float]
    satellites: Optional[int]
    fix_quality: Optional[int]


def _coerce_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _coerce_float(value: Optional[str]) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _build_timestamp(sent_time: Optional[datetime.time]) -> datetime.datetime:
    now = datetime.datetime.now(datetime.timezone.utc)
    if sent_time is None:
        return now
    sent = datetime.datetime.combine(now.date(), sent_time, tzinfo=datetime.timezone.utc)
    if sent > now + datetime.timedelta(minutes=1):
        sent = sent - datetime.timedelta(days=1)
    return sent


def parse_nmea_sentence(sentence: str) -> Optional[GpsFix]:
    try:
        msg = pynmea2.parse(sentence)
    except (pynmea2.ParseError, AttributeError):
        return None

    if getattr(msg, "status", "A").upper() == "V":
        return None

    latitude = getattr(msg, "latitude", None)
    longitude = getattr(msg, "longitude", None)
    if latitude is None or longitude is None:
        return None

    tx_time = getattr(msg, "timestamp", None)
    ts = _build_timestamp(tx_time)

    hdop = getattr(msg, "hdop", None) or getattr(msg, "horizontal_dil", None)
    if isinstance(hdop, str):
        hdop = _coerce_float(hdop)
    satellites = _coerce_int(getattr(msg, "num_sats", None))
    fix_quality = _coerce_int(getattr(msg, "gps_qual", None) or getattr(msg, "fix_quality", None))

    if fix_quality == 0:
        return None

    return GpsFix(
        lat=float(latitude),
        lon=float(longitude),
        timestamp=ts,
        hdop=_coerce_float(hdop) if hdop is not None else None,
        satellites=satellites,
        fix_quality=fix_quality,
    )


def _auto_detect_port(exclude: Iterable[str] | None = None) -> Optional[str]:
    return find_port_by_keywords(GPS_KEYWORDS, exclude)


class SerialGpsReader:
    def __init__(
        self,
        port: Optional[str] = None,
        baudrate: int = DEFAULT_GPS_BAUDRATE,
        timeout: float = 1.0,
        exclude_ports: Optional[Iterable[str]] = None,
    ):
        self._port = port or _auto_detect_port(exclude_ports)
        if not self._port:
            raise ValueError(
                "Unable to detect GPS port. Provide `gps_port` in configuration or "
                "set GPS device that mentions GPS/GNSS in its description."
            )
        self._serial = serial.Serial(self._port, baudrate=baudrate, timeout=timeout)
        self._serial.reset_input_buffer()

    def __enter__(self) -> "SerialGpsReader":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def get_fix(self, timeout_seconds: float = 15.0) -> GpsFix:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            raw = self._serial.readline()
            if not raw:
                continue
            try:
                sentence = raw.decode("ascii", errors="ignore").strip()
            except UnicodeDecodeError:
                continue
            fix = parse_nmea_sentence(sentence)
            if fix:
                logger.debug("GPS fix acquired: %s", fix)
                return fix
        raise TimeoutError("Timed out waiting for GPS fix")

