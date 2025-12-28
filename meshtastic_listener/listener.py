from __future__ import annotations

import json
import logging
import re
import sys
import time
from pathlib import Path
from threading import Event
from typing import Any, Callable
from collections import deque
from datetime import datetime

_TX_TAG_PATTERN = re.compile(r"\btx=(\d+(?:\.\d+)?)")

# Add the project root to sys.path to allow running this file directly
if __name__ == "__main__" and __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from meshtastic import LOCAL_ADDR
from meshtastic.serial_interface import SerialInterface
from meshtastic_pinger.radio import resolve_radio_mode
from meshtastic_pinger.serial_utils import auto_detect_radio_port
from meshtastic_listener.configuration import load_config
from pubsub import pub

logger = logging.getLogger(__name__)

def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

def _extract_message_text(packet: Any) -> str | None:
    if not isinstance(packet, dict):
        return None

    # Some firmware versions wrap the payload under nested dicts
    def _decode_payload(value: Any) -> str | None:
        if isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested_text = value.get("text")
            if nested_text is not None:
                return str(nested_text)
            nested_payload = value.get("payload") or value.get("data")
            if isinstance(nested_payload, (bytes, bytearray)):
                return nested_payload.decode("utf-8", errors="replace")
        return None

    decoded = packet.get("decoded")
    decoded_dict = decoded if isinstance(decoded, dict) else None

    # Direct decoded content (bytes/str or dict with text)
    direct_message = _decode_payload(decoded)
    if direct_message:
        return direct_message

    if decoded_dict:
        text = decoded_dict.get("text")
        if text is not None:
            return str(text)

        payload = decoded_dict.get("payload") or decoded_dict.get("data")
        message = _decode_payload(payload)
        if message:
            return message

        # Some firmware variants put the raw bytes under decoded["payload"]["payload"]
        decoded_payload = decoded_dict.get("payload")
        message = _decode_payload(decoded_payload)
        if message:
            return message

    # Fallback: sometimes the top-level packet carries the data
    return _decode_payload(packet.get("payload") or packet.get("data"))

def _append_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(message.rstrip("\n") + "\n")

def _sanitize_for_log(value: Any) -> Any:
    """Make packets JSON-serializable for logging."""
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.hex()
    if isinstance(value, dict):
        return {k: _sanitize_for_log(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_for_log(v) for v in value]
    return value

def _parse_sent_time(raw: Any) -> datetime | None:
    """Parse a sent timestamp if provided as epoch seconds or ISO string."""
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(float(raw))
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                return None
            if text.isdigit():
                return datetime.fromtimestamp(float(text))
            try:
                return datetime.fromisoformat(text)
            except Exception:
                return None
    except Exception:
        return None
    return None

def _parse_time_from_message_tail(message: str, received_at: datetime) -> datetime | None:
    """Extract HH:MM:SS token at message end and map it to received_at's date."""
    parts = message.strip().split()
    if not parts:
        return None
    tail = parts[-1]
    if len(tail) != 8 or tail.count(":") != 2:
        return None
    try:
        hour, minute, second = map(int, tail.split(":"))
        return received_at.replace(hour=hour, minute=minute, second=second, microsecond=0)
    except Exception:
        return None

def _parse_tx_epoch(message: str) -> float | None:
    """Extract a transmit epoch timestamp from a 'tx=' tag in the message text."""
    match = _TX_TAG_PATTERN.search(message)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None

class MeshtasticListener:
    def __init__(
        self,
        device: str | None = None,
        output_path: Path | str = "meshtastic_messages.log",
        exclude_ports: list[str] | None = None,
        radio_mode: str | None = None,
        raw_packet_path: Path | str | None = None,
        interface_factory: Callable[..., SerialInterface] = SerialInterface,
    ) -> None:
        out_path = Path(output_path)
        if not out_path.suffix:
            out_path = out_path.with_suffix(".txt")
        self.output_path = out_path

        if raw_packet_path:
            raw_path = Path(raw_packet_path)
            if not raw_path.suffix:
                raw_path = raw_path.with_suffix(".txt")
            self.raw_packet_path = raw_path
        else:
            self.raw_packet_path = None
        self.interface_factory = interface_factory
        self.radio_mode = radio_mode
        self.device = device or auto_detect_radio_port(exclude_ports=exclude_ports)
        if self.device is None:
            raise RuntimeError("Unable to detect Meshtastic radio port.")
        
        self._interface: SerialInterface | None = None
        self._pubsub_unsub: Callable[[], None] | None = None
        self._pubsub_unsubscribers: list[Callable[[], None]] = []
        self._recent_keys: set[str] = set()
        self._recent_queue: deque[str] = deque(maxlen=200)

    def _apply_radio_mode(self) -> None:
        """Apply the configured radio modem preset if provided."""
        if not self.radio_mode or not self._interface:
            return

        try:
            mode_value = resolve_radio_mode(self.radio_mode)
        except ValueError as exc:
            logger.warning("Unknown radio mode '%s': %s", self.radio_mode, exc)
            return

        if mode_value is None:
            return

        try:
            node = self._interface.getNode(LOCAL_ADDR, requestChannels=False)
            if len(node.localConfig.ListFields()) == 0:
                lora_field = node.localConfig.DESCRIPTOR.fields_by_name.get("lora")
                if lora_field is not None:
                    node.requestConfig(lora_field)
            node.localConfig.lora.modem_preset = mode_value
            node.writeConfig("lora")
            logger.info("Configured radio mode '%s' (%s)", self.radio_mode, mode_value)
        except Exception as exc:  # pragma: no cover - depends on radio firmware
            logger.warning("Failed to apply radio mode '%s': %s", self.radio_mode, exc)

    def _on_receive(self, packet: dict[str, Any], _interface: Any = None) -> None:
        logger.info(
            "Packet received portnum=%s from=%s keys=%s decoded_keys=%s",
            packet.get("decoded", {}).get("portnum") if isinstance(packet.get("decoded"), dict) else None,
            packet.get("from"),
            list(packet.keys()),
            list(packet.get("decoded", {}).keys()) if isinstance(packet.get("decoded"), dict) else None,
        )

        decoded = packet.get("decoded") if isinstance(packet.get("decoded"), dict) else {}
        portnum = decoded.get("portnum")

        # Deduplicate if we've already handled this packet (helps avoid double fire from pubsub + onReceive)
        try:
            key = self._packet_key(packet)
            if key in self._recent_keys:
                logger.debug("Duplicate packet ignored (id=%s port=%s)", packet.get("id"), portnum)
                return
            self._remember_packet(key)
        except Exception:
            # If key building fails, continue without deduping
            pass

        # Only handle text messages; ignore routing/position/etc.
        if portnum and str(portnum).upper() != "TEXT_MESSAGE_APP":
            logger.info("Ignoring non-text portnum=%s", portnum)
            return

        sanitized = _sanitize_for_log(packet)
        try:
            logger.info("Raw packet: %s", json.dumps(sanitized, ensure_ascii=False))
        except Exception:
            logger.info("Raw packet (repr): %s", sanitized)
        if self.raw_packet_path:
            try:
                _append_line(self.raw_packet_path, json.dumps(sanitized, ensure_ascii=False))
            except Exception as exc:
                logger.warning("Failed to write raw packet log: %s", exc)
        message = _extract_message_text(packet)
        if not message or not str(message).strip():
            logger.info(
                "Ignoring non-text packet (keys=%s, decoded_keys=%s)",
                list(packet.keys()),
                list(packet.get("decoded", {}).keys()) if isinstance(packet.get("decoded"), dict) else None,
            )
            return
        received_epoch = time.time()
        received_dt = datetime.fromtimestamp(received_epoch)
        tx_epoch = _parse_tx_epoch(str(message))
        sent_dt = None
        delay_seconds = None
        sent_raw = decoded.get("timestamp") or decoded.get("time") or packet.get("timestamp")
        if tx_epoch is not None:
            sent_dt = datetime.fromtimestamp(tx_epoch)
            delay_seconds = max(0.0, received_epoch - tx_epoch)
        else:
            sent_dt = _parse_sent_time(sent_raw) or _parse_time_from_message_tail(str(message), received_dt)
            if sent_dt:
                delay_seconds = abs((received_dt - sent_dt).total_seconds())

        delay_label = "n/a"
        if sent_dt and delay_seconds is not None:
            delay_label = f"{delay_seconds:.3f}"

        logger.info(
            "Received message: %s (sent_at=%s received_at=%s delay_s=%s)",
            message,
            sent_dt.isoformat() if sent_dt else "n/a",
            received_dt.isoformat(),
            delay_label,
        )
        _append_line(
            self.output_path,
            f"message: {message} | sent_at: {sent_dt.isoformat() if sent_dt else 'n/a'} | received_at: {received_dt.isoformat()} | delay_s: {delay_label}",
        )

    def _subscribe_pubsub(self) -> None:
        """Subscribe to pubsub events as an additional tap for packets."""
        if not self._interface:
            return

        pubsub = getattr(self._interface, "pubSub", None)
        subscribe = getattr(pubsub, "subscribe", None)
        if callable(subscribe):
            topics = [
                "meshtastic.receive",
                "meshtastic.receive.text",
                "meshtastic.receive.data",
                "meshtastic.receive.position",
            ]
            logger.info("Attempting pubsub subscriptions: %s", topics)

            def handler(packet: Any, interface: Any = None) -> None:
                self._on_receive(packet, interface)

            unsubscribers: list[Callable[[], None]] = []
            for topic in topics:
                try:
                    unsub = subscribe(topic, handler)
                    if callable(unsub):
                        unsubscribers.append(unsub)
                    logger.info("PubSub subscription established for %s", topic)
                except Exception as exc:
                    logger.info("PubSub subscribe failed for %s: %s", topic, exc)

            if unsubscribers:
                def _unsub_all() -> None:
                    for func in unsubscribers:
                        try:
                            func()
                        except Exception:
                            pass
                self._pubsub_unsub = _unsub_all
                self._pubsub_unsubscribers.extend(unsubscribers)
                logger.info("PubSub subscriptions active: %s", topics)
                return

        logger.info("Interface pubsub unavailable or failed; trying global pubsub fallback")

        topics = [
            "meshtastic.receive",
            "meshtastic.receive.text",
            "meshtastic.receive.data",
            "meshtastic.receive.position",
        ]

        def handler(packet: Any, interface: Any = None) -> None:
            self._on_receive(packet, interface)

        unsubscribers: list[Callable[[], None]] = []
        for topic in topics:
            try:
                pub.subscribe(handler, topic)
                unsubscribers.append(lambda t=topic, h=handler: pub.unsubscribe(h, t))
                logger.info("Global pubsub subscription established for %s", topic)
            except Exception as exc:
                logger.info("Global pubsub subscribe failed for %s: %s", topic, exc)

        if unsubscribers:
            def _unsub_all() -> None:
                for func in unsubscribers:
                    try:
                        func()
                    except Exception:
                        pass
            self._pubsub_unsub = _unsub_all
            self._pubsub_unsubscribers.extend(unsubscribers)
            logger.info("Global pubsub subscriptions active: %s", topics)
        else:
            logger.warning("PubSub subscribe failed for all topics; relying on onReceive only")

    def _packet_key(self, packet: dict[str, Any]) -> str:
        """Build a deduplication key for a packet."""
        decoded = packet.get("decoded") if isinstance(packet.get("decoded"), dict) else {}
        portnum = decoded.get("portnum")
        key = (
            packet.get("id"),
            packet.get("from"),
            packet.get("to"),
            portnum,
            decoded.get("text") if isinstance(decoded, dict) else None,
            decoded.get("payload") if isinstance(decoded, dict) else packet.get("payload"),
        )
        return json.dumps(key, sort_keys=False, default=str)

    def _remember_packet(self, key: str) -> None:
        self._recent_keys.add(key)
        self._recent_queue.append(key)
        while len(self._recent_queue) > self._recent_queue.maxlen:
            oldest = self._recent_queue.popleft()
            self._recent_keys.discard(oldest)


    def start(self, stop_event: Event | None = None) -> None:
        logger.info("Starting Meshtastic listener on %s", self.device)
        logger.info("Logging messages to %s", self.output_path.resolve())
        self._interface = self.interface_factory(devPath=self.device, noNodes=True, timeout=20)
        self._interface.onReceive = self._on_receive
        self._subscribe_pubsub()
        self._apply_radio_mode()
        logger.info("Listener active, waiting for messages...")
        
        wait_for = stop_event or Event()
        try:
            while not wait_for.wait(timeout=1):
                pass
        except KeyboardInterrupt:
            logger.info("Stopping listener...")
        finally:
            self.close()

    def close(self) -> None:
        if self._pubsub_unsub:
            try:
                self._pubsub_unsub()
            except Exception:
                pass
            self._pubsub_unsub = None
            self._pubsub_unsubscribers.clear()
        if self._interface:
            self._interface.close()
            self._interface = None

    def __enter__(self) -> MeshtasticListener:
        return self

    def __exit__(self, *_) -> None:
        self.close()

def main() -> None:
    _configure_logging()
    try:
        config = load_config()
    except Exception as exc:
        logger.error("Failed to load configuration: %s", exc)
        sys.exit(1)

    try:
        with MeshtasticListener(
            device=config.meshtastic_port,
            output_path=config.output_path,
            radio_mode=config.radio_mode,
        ) as listener:
            listener.start()
    except Exception as exc:
        logger.error("Listener error: %s", exc)
        sys.exit(1)

if __name__ == "__main__":
    main()
