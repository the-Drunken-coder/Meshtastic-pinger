import http.client
import json
import threading

from http.server import ThreadingHTTPServer

from message_sink_service import MAX_BODY_SIZE, _append_line, _build_handler

SERVER_SHUTDOWN_TIMEOUT = 5
DEFAULT_HEADERS = {"Content-Type": "text/plain"}


def _post(server: ThreadingHTTPServer, body: str, headers: dict[str, str] | None = None) -> int:
    headers = headers or DEFAULT_HEADERS
    conn = http.client.HTTPConnection("localhost", server.server_address[1])
    conn.request("POST", "/", body=body, headers=headers)
    response = conn.getresponse()
    status = response.status
    conn.close()
    return status


def test_append_line_appends_messages(tmp_path):
    log_file = tmp_path / "messages.log"
    _append_line(log_file, "first")
    _append_line(log_file, "second")

    assert log_file.read_text().splitlines() == ["first", "second"]


def test_service_writes_plain_and_json_messages(tmp_path):
    log_file = tmp_path / "messages.log"
    handler = _build_handler(log_file)
    server = ThreadingHTTPServer(("localhost", 0), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    assert _post(server, "hello") == 204

    assert (
        _post(server, json.dumps({"message": "world"}), headers={"Content-Type": "application/json"})
        == 204
    )

    server.shutdown()
    thread.join(timeout=SERVER_SHUTDOWN_TIMEOUT)
    server.server_close()

    assert log_file.read_text().splitlines() == ["hello", "world"]


def test_invalid_content_length_is_rejected(tmp_path):
    log_file = tmp_path / "messages.log"
    handler = _build_handler(log_file)
    server = ThreadingHTTPServer(("localhost", 0), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    conn = http.client.HTTPConnection("localhost", server.server_address[1])
    conn.putrequest("POST", "/")
    conn.putheader("Content-Length", "invalid")
    conn.endheaders()
    response = conn.getresponse()
    assert response.status == 400
    conn.close()

    server.shutdown()
    thread.join(timeout=SERVER_SHUTDOWN_TIMEOUT)
    server.server_close()

    assert not log_file.exists()


def test_negative_content_length_is_rejected(tmp_path):
    log_file = tmp_path / "messages.log"
    handler = _build_handler(log_file)
    server = ThreadingHTTPServer(("localhost", 0), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    conn = http.client.HTTPConnection("localhost", server.server_address[1])
    conn.putrequest("POST", "/")
    conn.putheader("Content-Length", "-1")
    conn.endheaders()
    response = conn.getresponse()
    assert response.status == 400
    conn.close()

    server.shutdown()
    thread.join(timeout=SERVER_SHUTDOWN_TIMEOUT)
    server.server_close()

    assert not log_file.exists()


def test_payload_too_large_is_rejected(tmp_path):
    log_file = tmp_path / "messages.log"
    handler = _build_handler(log_file)
    server = ThreadingHTTPServer(("localhost", 0), handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    conn = http.client.HTTPConnection("localhost", server.server_address[1])
    conn.putrequest("POST", "/")
    conn.putheader("Content-Length", str(MAX_BODY_SIZE + 1))
    conn.endheaders()
    response = conn.getresponse()
    assert response.status == 413
    conn.close()

    server.shutdown()
    thread.join(timeout=SERVER_SHUTDOWN_TIMEOUT)
    server.server_close()

    assert not log_file.exists()
