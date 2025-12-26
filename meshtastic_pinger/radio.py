from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Union

from meshtastic import BROADCAST_ADDR, LOCAL_ADDR
from meshtastic.protobuf import config_pb2, portnums_pb2
from meshtastic.serial_interface import SerialInterface

from .gps import GpsFix

logger = logging.getLogger(__name__)


class _SafeUnavailable(str):
    """String sentinel that ignores format specifiers (e.g., {:.1f})."""

    def __format__(self, format_spec: str) -> str:  # pragma: no cover - trivial
        return str(self)


_UNAVAILABLE = _SafeUnavailable("n/a")


def resolve_destination(target: str) -> Union[int, str]:
    normalized = target.strip()
    if not normalized or normalized.lower() in {"broadcast", "all"}:
        return BROADCAST_ADDR
    if normalized.isdigit():
        return int(normalized)
    if normalized.startswith("0x"):
        return normalized
    return normalized


def build_message(
    template: str, fix: GpsFix, extra: Optional[Dict[str, Any]] = None
) -> str:
    payload: Dict[str, Any] = {
        "lat": fix.lat,
        "lon": fix.lon,
        "hdop": fix.hdop if fix.hdop is not None else 0.0,
        "satellites": fix.satellites if fix.satellites is not None else 0,
        "fix_quality": fix.fix_quality if fix.fix_quality is not None else 0,
        "timestamp": fix.timestamp.isoformat(),
        "iso": fix.timestamp.isoformat(),
        "time": fix.timestamp.strftime("%H:%M:%S"),
        "date": fix.timestamp.strftime("%Y-%m-%d"),
    }
    if extra:
        payload.update(extra)
    try:
        return template.format(**payload)
    except KeyError as exc:
        missing = exc.args[0]
        raise ValueError(f"Message template references an unknown key: {missing}") from exc


def _normalize_mode_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


_MODEM_PRESET = config_pb2.Config.LoRaConfig.ModemPreset
_MODE_PRESET_MAP = {
    _normalize_mode_key(name): getattr(_MODEM_PRESET, name)
    for name in _MODEM_PRESET.keys()
}


def resolve_radio_mode(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    normalized = _normalize_mode_key(value)
    if not normalized:
        return None
    if normalized.isdigit():
        return int(normalized)
    preset = _MODE_PRESET_MAP.get(normalized)
    if preset is None:
        valid = ", ".join(sorted(_MODE_PRESET_MAP.keys()))
        raise ValueError(
            f"Unknown radio mode '{value}'. Valid preset names: {valid}"
        )
    return preset


@dataclass
class MeshtasticClient:
    target_node: str
    device: str | None = None
    want_ack: bool = True
    radio_mode: Optional[str] = "longfast"

    def __post_init__(self) -> None:
        self._destination = resolve_destination(self.target_node)
        self._destination_num = self._resolve_destination_num(self._destination)
        
        logger.info("Connecting to Meshtastic radio on %s (timeout=20s)...", self.device)
        try:
            # noNodes=True avoids downloading the node list, which is much faster/reliable on slow links
            self._interface = SerialInterface(devPath=self.device, timeout=20, noNodes=True)
        except Exception as exc:
            logger.error("Failed to connect to radio: %s", exc)
            raise

        self._radio_mode_value = resolve_radio_mode(self.radio_mode)
        self._configure_radio_mode()

    def __enter__(self) -> "MeshtasticClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def _configure_radio_mode(self) -> None:
        if self._radio_mode_value is None:
            return
        try:
            node = self._interface.getNode(LOCAL_ADDR, requestChannels=False)
            if len(node.localConfig.ListFields()) == 0:
                lora_field = node.localConfig.DESCRIPTOR.fields_by_name.get("lora")
                if lora_field is not None:
                    node.requestConfig(lora_field)
            node.localConfig.lora.modem_preset = self._radio_mode_value
            node.writeConfig("lora")
            logger.info("Configured radio mode '%s' (%s)", self.radio_mode, self._radio_mode_value)
        except Exception as exc:
            logger.warning("Failed to apply radio mode '%s': %s", self.radio_mode, exc)

    def close(self) -> None:
        self._interface.close()

    @staticmethod
    def _resolve_destination_num(dest: Union[int, str]) -> Optional[int]:
        if dest in (BROADCAST_ADDR, LOCAL_ADDR):
            return None
        if isinstance(dest, int):
            return dest
        try:
            value = str(dest).strip()
            if value.lower().startswith("0x"):
                value = value[2:]
            value = value.lstrip("!")
            return int(value[-8:], 16)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_snr(entry: Optional[Dict[str, Any]]) -> Optional[float]:
        if not entry:
            return None
        snr: Any = entry.get("snr")
        if snr is None:
            last = entry.get("lastReceived")
            if isinstance(last, dict):
                snr = last.get("rxSnr")
                if snr is None:
                    snr = last.get("snr")
        if snr in (None, -128):
            return None
        try:
            return float(snr)
        except (TypeError, ValueError):
            return None

    def _read_signal_strength(self) -> Optional[float]:
        try:
            nodes = getattr(self._interface, "nodesByNum", None) or {}
            if self._destination_num is not None:
                snr = self._extract_snr(nodes.get(self._destination_num))
                if snr is not None:
                    return snr

            nodes_by_id = getattr(self._interface, "nodesById", None) or {}
            entry = nodes_by_id.get(self._destination)
            if entry is not None:
                snr = self._extract_snr(entry)
                if snr is not None:
                    return snr

            # DO NOT call self._interface.getNode(self._destination) here
            # as it triggers a remote admin query which fails with ADMIN_PUBLIC_KEY_UNAUTHORIZED
        except Exception as exc:  # pragma: no cover - library-side failure
            logger.debug("Unable to read signal strength for %s: %s", self._destination, exc)
            return None
        return None

    def _read_local_signal_strength(self) -> Optional[float]:
        try:
            nodes = getattr(self._interface, "nodesByNum", None) or {}
            latest: Optional[float] = None
            latest_seen: float = -1
            for entry in nodes.values():
                snr = self._extract_snr(entry)
                if snr is None:
                    continue
                heard = entry.get("lastHeard") or 0
                if heard >= latest_seen:
                    latest_seen = heard
                    latest = snr
            return latest
        except Exception:
            return None

    def send_fix(self, fix: GpsFix, template: str) -> Any:
        extras: Dict[str, Any] = {}
        signal = self._read_signal_strength()
        extras["snr"] = signal if signal is not None else _UNAVAILABLE
        if signal is not None:
            logger.info("Signal strength for %s: %s dB", self._destination, signal)
        radio_signal = self._read_local_signal_strength()
        extras["radio_snr"] = radio_signal if radio_signal is not None else _UNAVAILABLE
        if radio_signal is not None:
            logger.info("Radio signal strength: %s dB", radio_signal)
        message = build_message(template, fix, extra=extras or None)
        logger.info("Sending to %s: %s", self._destination, message)
        return self._interface.sendText(
            message,
            destinationId=self._destination,
            wantAck=self.want_ack,
            portNum=portnums_pb2.PortNum.TEXT_MESSAGE_APP,
        )
