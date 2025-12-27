import threading
import time
from pathlib import Path

from meshtastic.protobuf import config_pb2

from meshtastic_listener.listener import (
    _append_line,
    _extract_message_text,
    _sanitize_for_log,
    MeshtasticListener,
)

SETUP_RETRIES = 20
THREAD_JOIN_TIMEOUT = 2

def test_append_line_appends_messages(tmp_path):
    log_file = tmp_path / "messages.log"
    _append_line(log_file, "first")
    _append_line(log_file, "second")

    assert log_file.read_text().splitlines() == ["first", "second"]

def test_extract_message_text_supports_variants():
    assert _extract_message_text({"decoded": {"text": "hello"}}) == "hello"
    assert _extract_message_text({"decoded": {"payload": b"bytes"}}) == "bytes"
    assert _extract_message_text({"decoded": {"data": "fallback"}}) == "fallback"
    assert (
        _extract_message_text({"decoded": {"data": {"text": "nested"}}})
        == "nested"
    )
    assert (
        _extract_message_text({"decoded": {"payload": {"payload": b"deep"}}})
        == "deep"
    )
    assert _extract_message_text({"payload": b"top"}) == "top"


def test_sanitize_for_log_handles_bytes_and_nested():
    data = {"decoded": {"payload": b"bytes", "nested": {"data": b"\xff\x00"}}}
    sanitized = _sanitize_for_log(data)
    assert sanitized["decoded"]["payload"] == "bytes"
    assert sanitized["decoded"]["nested"]["data"] == "ff00"

class FakeInterface:
    def __init__(self, devPath=None, **_):
        self.devPath = devPath
        self.onReceive = None
        self.closed = False

    def close(self):
        self.closed = True

    def emit(self, packet):
        if self.onReceive:
            self.onReceive(packet, self)


class FakeNode:
    def __init__(self):
        self.localConfig = config_pb2.Config()
        self.requested = False
        self.written = None

    def requestConfig(self, field):
        self.requested = True

    def writeConfig(self, name):
        self.written = name


class FakeInterfaceWithNode(FakeInterface):
    def __init__(self, devPath=None, **kwargs):
        super().__init__(devPath, **kwargs)
        self.node = FakeNode()
        self.pubSub = None

    def getNode(self, node_id, requestChannels=False):
        return self.node


class FakePubSub:
    def __init__(self):
        self.subscribed = []
        self.unsubscribed = False

    def subscribe(self, topic, handler):
        self.subscribed.append((topic, handler))
        return lambda: setattr(self, "unsubscribed", True)


class FakeInterfaceWithPubSub(FakeInterface):
    def __init__(self, devPath=None, **kwargs):
        super().__init__(devPath, **kwargs)
        self.pubSub = FakePubSub()


class DummyPub:
    def __init__(self):
        self.subscribed = []
        self.unsubscribed = []

    def subscribe(self, handler, topic):
        self.subscribed.append((topic, handler))

    def unsubscribe(self, handler, topic):
        self.unsubscribed.append((topic, handler))

def test_listener_listens_and_logs_packets(monkeypatch, tmp_path):
    log_file = tmp_path / "messages.log"
    stop_event = threading.Event()
    interface = FakeInterface()

    auto_detect_calls = []

    def fake_auto_detect(exclude_ports=None):
        auto_detect_calls.append(exclude_ports)
        return "/dev/ttyUSB0"

    monkeypatch.setattr("meshtastic_listener.listener.auto_detect_radio_port", fake_auto_detect)

    listener = MeshtasticListener(
        device=None,
        output_path=log_file,
        interface_factory=lambda devPath=None, **kwargs: interface,
    )

    thread = threading.Thread(
        target=listener.start,
        kwargs={"stop_event": stop_event},
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

    lines = log_file.read_text().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("message: ping | sent_at:")
    assert "received_at:" in lines[0]
    assert "delay_s:" in lines[0]
    assert lines[1].startswith("message: pong | sent_at:")
    assert "received_at:" in lines[1]
    assert "delay_s:" in lines[1]
    assert interface.closed
    assert auto_detect_calls == [None]

def test_listener_deduplicates_packets(monkeypatch, tmp_path):
    log_file = tmp_path / "messages.log"
    stop_event = threading.Event()
    stop_event.set()
    interface = FakeInterface()

    monkeypatch.setattr(
        "meshtastic_listener.listener.auto_detect_radio_port", lambda exclude_ports=None: "/dev/ttyUSB0"
    )

    listener = MeshtasticListener(
        device=None,
        output_path=log_file,
        interface_factory=lambda devPath=None, **kwargs: interface,
    )

    listener.start(stop_event=stop_event)

    packet = {"id": 123, "from": 1, "to": 2, "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "hello"}}
    interface.emit(packet)
    interface.emit(packet)  # duplicate

    lines = log_file.read_text().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("message: hello | sent_at:")
    assert "received_at:" in lines[0]
    assert "delay_s:" in lines[0]

def test_listener_ignores_non_text_port(monkeypatch, tmp_path):
    log_file = tmp_path / "messages.log"
    stop_event = threading.Event()
    stop_event.set()
    interface = FakeInterface()

    monkeypatch.setattr(
        "meshtastic_listener.listener.auto_detect_radio_port", lambda exclude_ports=None: "/dev/ttyUSB0"
    )

    listener = MeshtasticListener(
        device=None,
        output_path=log_file,
        interface_factory=lambda devPath=None, **kwargs: interface,
    )

    listener.start(stop_event=stop_event)
    # Simulate a POSITION_APP packet which should be ignored for message logging
    interface.emit({"decoded": {"portnum": "POSITION_APP", "payload": b"\x01\x02"}})

    assert not log_file.exists()


def test_listener_applies_radio_mode(monkeypatch, tmp_path):
    log_file = tmp_path / "messages.log"
    stop_event = threading.Event()
    stop_event.set()
    interface = FakeInterfaceWithNode()

    monkeypatch.setattr(
        "meshtastic_listener.listener.auto_detect_radio_port", lambda exclude_ports=None: "/dev/ttyUSB0"
    )

    listener = MeshtasticListener(
        device=None,
        output_path=log_file,
        radio_mode="longfast",
        interface_factory=lambda devPath=None, **kwargs: interface,
    )

    listener.start(stop_event=stop_event)

    preset = config_pb2.Config.LoRaConfig.ModemPreset.LONG_FAST
    assert interface.node.localConfig.lora.modem_preset == preset
    assert interface.node.written == "lora"
    assert interface.closed


def test_listener_subscribes_pubsub(monkeypatch, tmp_path):
    stop_event = threading.Event()
    stop_event.set()
    interface = FakeInterfaceWithPubSub()

    monkeypatch.setattr(
        "meshtastic_listener.listener.auto_detect_radio_port", lambda exclude_ports=None: "/dev/ttyUSB0"
    )

    listener = MeshtasticListener(
        device=None,
        output_path=tmp_path / "messages.log",
        interface_factory=lambda devPath=None, **kwargs: interface,
    )

    listener.start(stop_event=stop_event)

    assert interface.pubSub.subscribed
    topics = {topic for topic, _ in interface.pubSub.subscribed}
    assert "meshtastic.receive" in topics


def test_listener_subscribes_global_pubsub_when_missing_interface(monkeypatch, tmp_path):
    stop_event = threading.Event()
    stop_event.set()
    interface = FakeInterface()
    dummy_pub = DummyPub()

    monkeypatch.setattr(
        "meshtastic_listener.listener.auto_detect_radio_port", lambda exclude_ports=None: "/dev/ttyUSB0"
    )
    monkeypatch.setattr("meshtastic_listener.listener.pub", dummy_pub)

    listener = MeshtasticListener(
        device=None,
        output_path=tmp_path / "messages.log",
        interface_factory=lambda devPath=None, **kwargs: interface,
    )

    listener.start(stop_event=stop_event)

    assert dummy_pub.subscribed
    topics = {topic for topic, _ in dummy_pub.subscribed}
    assert "meshtastic.receive" in topics
