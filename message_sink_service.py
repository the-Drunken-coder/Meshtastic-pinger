from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY_SIZE = 1024 * 1024  # 1MB safety cap


def _append_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(message.rstrip("\n") + "\n")


def _build_handler(log_path: Path) -> type[BaseHTTPRequestHandler]:
    class MessageHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self.send_response(400)
                self.end_headers()
                return

            if length < 0:
                self.send_response(400)
                self.end_headers()
                return
            if length > MAX_BODY_SIZE:
                self.send_response(413)
                self.end_headers()
                return

            if length == 0:
                message = ""
            else:
                raw = self.rfile.read(length)
                message = raw.decode("utf-8", errors="replace")

            if self.headers.get("Content-Type", "").startswith("application/json"):
                try:
                    payload = json.loads(message)
                    if isinstance(payload, dict) and "message" in payload:
                        message = str(payload["message"])
                except json.JSONDecodeError:
                    pass

            _append_line(log_path, message)
            self.send_response(204)
            self.end_headers()

        def log_message(self, format: str, *args) -> None:  # pragma: no cover - suppress noisy logs
            return

    return MessageHandler


def run_server(host: str = "0.0.0.0", port: int = 8080, output: Path | str = "meshtastic_messages.log") -> None:
    output_path = Path(output)
    handler = _build_handler(output_path)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"Meshtastic pinger sink listening on {host}:{server.server_address[1]}, logging to {output_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping message sink...")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Receive Meshtastic pinger messages over HTTP and write them to a text file."
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument(
        "--output",
        default="meshtastic_messages.log",
        help="Path to the output log file (default: meshtastic_messages.log)",
    )
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, output=args.output)


if __name__ == "__main__":  # pragma: no cover - manual execution entrypoint
    main()
