from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
import json

DEFAULT_CONFIG_FILE = "meshtastic_pinger.json"
DEFAULT_RADIO_MODE = "longfast"


@dataclass(frozen=True)
class AppConfig:
    target_node: str
    meshtastic_port: Optional[str]
    gps_port: Optional[str]
    send_interval_seconds: float
    gps_timeout_seconds: float
    message_template: str
    radio_ack: bool
    radio_mode: str


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def _as_float(value: Any, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    env = os.environ

    if "MESHTASTIC_PINGER_CONFIG" in env:
        resolved_path = Path(env["MESHTASTIC_PINGER_CONFIG"])
    elif config_path:
        resolved_path = config_path
    else:
        # Check current working directory first, then package directory
        cwd_path = Path(DEFAULT_CONFIG_FILE)
        pkg_path = Path(__file__).parent / DEFAULT_CONFIG_FILE
        resolved_path = cwd_path if cwd_path.exists() else pkg_path

    raw = _load_json(resolved_path)

    target_node = (
        env.get("MESHTASTIC_PINGER_TARGET_NODE")
        or raw.get("target_node")
        or raw.get("target")
    )

    if not target_node:
        raise ValueError(
            "target_node must be set either through configuration file or "
            "MESHTASTIC_PINGER_TARGET_NODE"
        )

    meshtastic_port = (
        _as_optional_str(env.get("MESHTASTIC_PINGER_RADIO_PORT"))
        or _as_optional_str(raw.get("meshtastic_port"))
    )
    gps_port = (
        _as_optional_str(env.get("MESHTASTIC_PINGER_GPS_PORT"))
        or _as_optional_str(raw.get("gps_port"))
    )
    send_interval_seconds = _as_float(
        env.get("MESHTASTIC_PINGER_INTERVAL"),
        float(raw.get("send_interval_seconds", raw.get("interval", 60))),
    )
    gps_timeout_seconds = _as_float(
        env.get("MESHTASTIC_PINGER_GPS_TIMEOUT"),
        float(raw.get("gps_timeout_seconds", raw.get("gps_timeout", 15))),
    )
    message_template = (
        env.get("MESHTASTIC_PINGER_TEMPLATE")
        or raw.get(
            "message_template",
            "GPS {lat:.6f},{lon:.6f} sats {satellites} hdop {hdop:.1f} {time}",
        )
    )
    radio_mode = (
        _as_optional_str(env.get("MESHTASTIC_PINGER_RADIO_MODE"))
        or _as_optional_str(raw.get("radio_mode"))
        or DEFAULT_RADIO_MODE
    )
    radio_ack = _as_bool(env.get("MESHTASTIC_PINGER_WANT_ACK"), raw.get("want_ack", True))

    return AppConfig(
        target_node=target_node,
        meshtastic_port=meshtastic_port,
        gps_port=gps_port,
        send_interval_seconds=send_interval_seconds,
        gps_timeout_seconds=gps_timeout_seconds,
        message_template=message_template,
        radio_ack=radio_ack,
        radio_mode=radio_mode,
    )

