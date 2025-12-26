import http.client
import json
import threading

from http.server import ThreadingHTTPServer

from message_sink_service import _append_line, _build_handler


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

    conn = http.client.HTTPConnection("localhost", server.server_address[1])
    conn.request("POST", "/", body="hello", headers={"Content-Type": "text/plain"})
    response = conn.getresponse()
    assert response.status == 204
    conn.close()

    conn = http.client.HTTPConnection("localhost", server.server_address[1])
    conn.request(
        "POST",
        "/",
        body=json.dumps({"message": "world"}),
        headers={"Content-Type": "application/json"},
    )
    response = conn.getresponse()
    assert response.status == 204
    conn.close()

    server.shutdown()
    thread.join(timeout=5)
    server.server_close()

    assert log_file.read_text().splitlines() == ["hello", "world"]

