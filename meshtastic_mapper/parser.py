"""Parse GPS messages from meshtastic_messages.txt files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_GPS_PATTERN = re.compile(r"GPS\s+(-?\d+\.\d+),(-?\d+\.\d+)")
_SENT_AT_PATTERN = re.compile(r"sent_at:\s+([^|]+)")
_RECEIVED_AT_PATTERN = re.compile(r"received_at:\s+([^|]+)")
_DELAY_PATTERN = re.compile(r"delay_s:\s+([^|]+)")
_SATS_PATTERN = re.compile(r"sats\s+(\d+)")
_HDOP_PATTERN = re.compile(r"hdop\s+([\d.]+)")


@dataclass(frozen=True)
class GpsMessage:
    """A GPS message with coordinates and metadata."""

    lat: float
    lon: float
    sent_at: Optional[datetime]
    received_at: Optional[datetime]
    delay_seconds: Optional[float]
    satellites: Optional[int]
    hdop: Optional[float]
    raw_message: str


def _parse_iso_datetime(text: str) -> Optional[datetime]:
    """Parse an ISO datetime string."""
    if not text or text.strip() == "n/a":
        return None
    try:
        # Try parsing ISO format
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except Exception:
        return None


def _parse_float(value: str) -> Optional[float]:
    """Parse a float value."""
    if not value or value.strip() == "n/a":
        return None
    try:
        return float(value.strip())
    except Exception:
        return None


def _parse_int(value: str) -> Optional[int]:
    """Parse an integer value."""
    if not value or value.strip() == "n/a":
        return None
    try:
        return int(value.strip())
    except Exception:
        return None


def parse_message_line(line: str) -> Optional[GpsMessage]:
    """Parse a single line from meshtastic_messages.txt."""
    line = line.strip()
    if not line.startswith("message:"):
        return None

    # Extract GPS coordinates
    gps_match = _GPS_PATTERN.search(line)
    if not gps_match:
        return None

    lat = float(gps_match.group(1))
    lon = float(gps_match.group(2))

    # Extract timestamps
    sent_match = _SENT_AT_PATTERN.search(line)
    sent_at = _parse_iso_datetime(sent_match.group(1)) if sent_match else None

    received_match = _RECEIVED_AT_PATTERN.search(line)
    received_at = _parse_iso_datetime(received_match.group(1)) if received_match else None

    # Extract delay
    delay_match = _DELAY_PATTERN.search(line)
    delay_seconds = _parse_float(delay_match.group(1)) if delay_match else None

    # Extract satellites and HDOP
    sats_match = _SATS_PATTERN.search(line)
    satellites = _parse_int(sats_match.group(1)) if sats_match else None

    hdop_match = _HDOP_PATTERN.search(line)
    hdop = _parse_float(hdop_match.group(1)) if hdop_match else None

    return GpsMessage(
        lat=lat,
        lon=lon,
        sent_at=sent_at,
        received_at=received_at,
        delay_seconds=delay_seconds,
        satellites=satellites,
        hdop=hdop,
        raw_message=line,
    )


def parse_messages_file(path: Path) -> list[GpsMessage]:
    """Parse all GPS messages from a meshtastic_messages.txt file."""
    messages = []
    if not path.exists():
        return messages

    with path.open("r", encoding="utf-8") as file:
        for line in file:
            message = parse_message_line(line)
            if message:
                messages.append(message)

    return messages
