import threading
import time

from message_sink_service import _append_line, _build_handler, _extract_message_text, run_sink

SETUP_RETRIES = 20
THREAD_JOIN_TIMEOUT = 2


def test_append_line_appends_messages(tmp_path):
    log_file = tmp_path / "messages.log"
    _append_line(log_file, "first")
    _append_line(log_file, "second")

    assert log_file.read_text().splitlines() == ["first", "second"]


def test_handler_writes_text_and_payload_bytes(tmp_path):
    log_file = tmp_path / "messages.log"
    handler = _build_handler(log_file)
    handler({"decoded": {"text": "hello"}}, None)
    handler({"decoded": {"payload": b"world"}}, None)

    assert log_file.read_text().splitlines() == ["hello", "world"]


def test_extract_message_text_supports_variants():
    assert _extract_message_text({"decoded": {"text": "hello"}}) == "hello"
    assert _extract_message_text({"decoded": {"payload": b"bytes"}}) == "bytes"
    assert _extract_message_text({"decoded": {"data": "fallback"}}) == "fallback"


class FakeInterface:
    def __init__(self, devPath=None):
        self.devPath = devPath
        self.onReceive = None
        self.closed = False

    def close(self):
        self.closed = True

    def emit(self, packet):
        if self.onReceive:
            self.onReceive(packet, self)


def test_run_sink_listens_and_logs_packets(monkeypatch, tmp_path):
    log_file = tmp_path / "messages.log"
    stop_event = threading.Event()
    interface = FakeInterface()

    auto_detect_calls = []

    def fake_auto_detect(exclude_ports=None):
        auto_detect_calls.append(exclude_ports)
        return "/dev/ttyUSB0"

    monkeypatch.setattr("message_sink_service.auto_detect_radio_port", fake_auto_detect)

    thread = threading.Thread(
        target=run_sink,
        kwargs={
            "device": None,
            "output": log_file,
            "stop_event": stop_event,
            "interface_factory": lambda devPath=None: interface,
        },
        daemon=True,
    )
    thread.start()

    for _ in range(SETUP_RETRIES):
        if interface.onReceive:
            break
        time.sleep(0.01)

    assert interface.onReceive is not None

    interface.emit({"decoded": {"text": "ping"}})
    interface.emit({"decoded": {"payload": b"pong"}})
    stop_event.set()
    thread.join(timeout=THREAD_JOIN_TIMEOUT)

    assert log_file.read_text().splitlines() == ["ping", "pong"]
    assert interface.closed
    assert auto_detect_calls == [None]
