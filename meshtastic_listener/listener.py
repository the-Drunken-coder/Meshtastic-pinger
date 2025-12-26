from __future__ import annotations

import logging
import sys
from pathlib import Path
from threading import Event
from typing import Any, Callable

from meshtastic.serial_interface import SerialInterface
from meshtastic_pinger.serial_utils import auto_detect_radio_port
from .configuration import load_config

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
    decoded = packet.get("decoded")
    if not isinstance(decoded, dict):
        return None
    text = decoded.get("text")
    if text is not None:
        return str(text)
    payload = decoded.get("payload") or decoded.get("data")
    if isinstance(payload, (bytes, bytearray)):
        return payload.decode("utf-8", errors="replace")
    if isinstance(payload, str):
        return payload
    return None

def _append_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(message.rstrip("\n") + "\n")

class MeshtasticListener:
    def __init__(
        self,
        device: str | None = None,
        output_path: Path | str = "meshtastic_messages.log",
        exclude_ports: list[str] | None = None,
        interface_factory: Callable[..., SerialInterface] = SerialInterface,
    ) -> None:
        self.output_path = Path(output_path)
        self.interface_factory = interface_factory
        self.device = device or auto_detect_radio_port(exclude_ports=exclude_ports)
        if self.device is None:
            raise RuntimeError("Unable to detect Meshtastic radio port.")
        
        self._interface: SerialInterface | None = None

    def _on_receive(self, packet: dict[str, Any], _interface: Any = None) -> None:
        message = _extract_message_text(packet)
        if message is None:
            return
        
        logger.info("Received message: %s", message)
        _append_line(self.output_path, message)

    def start(self, stop_event: Event | None = None) -> None:
        logger.info("Starting Meshtastic listener on %s", self.device)
        self._interface = self.interface_factory(devPath=self.device)
        self._interface.onReceive = self._on_receive
        
        wait_for = stop_event or Event()
        try:
            while not wait_for.wait(timeout=1):
                pass
        except KeyboardInterrupt:
            logger.info("Stopping listener...")
        finally:
            self.close()

    def close(self) -> None:
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
            output_path=config.output_path
        ) as listener:
            listener.start()
    except Exception as exc:
        logger.error("Listener error: %s", exc)
        sys.exit(1)

if __name__ == "__main__":
    main()

