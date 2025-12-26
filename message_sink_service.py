from __future__ import annotations

import argparse
from pathlib import Path
from threading import Event
from typing import Any, Callable, Iterable

from meshtastic.serial_interface import SerialInterface

from meshtastic_pinger.serial_utils import auto_detect_radio_port


def _append_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(message.rstrip("\n") + "\n")


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


def _build_handler(log_path: Path) -> Callable[[dict[str, Any], Any], None]:
    def on_receive(packet: dict[str, Any], _interface: Any = None) -> None:
        message = _extract_message_text(packet)
        if message is None:
            return
        _append_line(log_path, message)

    return on_receive


def run_sink(
    device: str | None = None,
    output: Path | str = "meshtastic_messages.log",
    stop_event: Event | None = None,
    exclude_ports: Iterable[str] | None = None,
    interface_factory: Callable[..., SerialInterface] = SerialInterface,
) -> None:
    output_path = Path(output)
    port = device or auto_detect_radio_port(exclude_ports=exclude_ports)
    if port is None:
        raise RuntimeError("Unable to detect Meshtastic radio port. Specify --device to override.")

    handler = _build_handler(output_path)
    interface = interface_factory(devPath=port)
    interface.onReceive = handler

    print(f"Meshtastic radio sink listening on {port}, logging to {output_path}")
    wait_for = stop_event or Event()
    try:
        while not wait_for.wait(timeout=1):
            pass
    except KeyboardInterrupt:
        print("Stopping message sink...")
    finally:
        interface.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Listen for Meshtastic messages over USB and append them to a text file."
    )
    parser.add_argument(
        "--device",
        help="Serial port for the Meshtastic radio (default: auto-detect)",
    )
    parser.add_argument(
        "--output",
        default="meshtastic_messages.log",
        help="Path to the output log file (default: meshtastic_messages.log)",
    )
    args = parser.parse_args()
    run_sink(device=args.device, output=args.output)


if __name__ == "__main__":  # pragma: no cover - manual execution entrypoint
    main()
