import json
import os
from pathlib import Path

import pytest

from meshtastic_pinger.configuration import AppConfig, load_config


def test_load_config_from_file(tmp_path: Path) -> None:
    config_file = tmp_path / "meshtastic_pinger.json"
    config_file.write_text(
        json.dumps(
            {
                "target_node": "NODE123",
                "meshtastic_port": "COM7",
                "gps_port": "COM4",
                "send_interval_seconds": 30,
                "gps_timeout_seconds": 10,
                "message_template": "GPS {lat} {lon}",
                "want_ack": False,
            }
        )
    )

    config = load_config(config_file)

    assert isinstance(config, AppConfig)
    assert config.target_node == "NODE123"
    assert config.meshtastic_port == "COM7"
    assert config.gps_port == "COM4"
    assert config.send_interval_seconds == 30.0
    assert config.gps_timeout_seconds == 10.0
    assert config.message_template == "GPS {lat} {lon}"
    assert config.radio_ack is False


def test_radio_mode_defaults_to_longfast(tmp_path: Path) -> None:
    config_file = tmp_path / "radio.json"
    config_file.write_text(json.dumps({"target_node": "NODE_RADIO"}))

    config = load_config(config_file)

    assert config.radio_mode == "longfast"


def test_radio_mode_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "radio.json"
    config_file.write_text(json.dumps({"target_node": "NODE_RADIO"}))
    monkeypatch.setenv("MESHTASTIC_PINGER_CONFIG", str(config_file))
    monkeypatch.setenv("MESHTASTIC_PINGER_RADIO_MODE", "ShortTurbo")

    config = load_config()

    assert config.radio_mode == "ShortTurbo"


def test_blank_ports_treated_as_none(tmp_path: Path) -> None:
    config_file = tmp_path / "ports.json"
    config_file.write_text(
        json.dumps(
            {
                "target_node": "NODE_RADIO",
                "meshtastic_port": "",
                "gps_port": "",
            }
        )
    )

    config = load_config(config_file)

    assert config.meshtastic_port is None
    assert config.gps_port is None


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"target_node": "FROM_FILE"}))
    monkeypatch.setenv("MESHTASTIC_PINGER_CONFIG", str(config_file))
    monkeypatch.setenv("MESHTASTIC_PINGER_TARGET_NODE", "FROM_ENV")
    monkeypatch.setenv("MESHTASTIC_PINGER_INTERVAL", "22")
    monkeypatch.setenv("MESHTASTIC_PINGER_GPS_TIMEOUT", "8")
    monkeypatch.setenv("MESHTASTIC_PINGER_TEMPLATE", "env {lat}")
    monkeypatch.setenv("MESHTASTIC_PINGER_WANT_ACK", "0")

    config = load_config()

    assert config.target_node == "FROM_ENV"
    assert config.send_interval_seconds == 22.0
    assert config.gps_timeout_seconds == 8.0
    assert config.message_template == "env {lat}"
    assert config.radio_ack is False


def test_missing_target_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_config(tmp_path / "missing.json")

