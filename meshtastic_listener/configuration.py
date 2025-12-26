from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_FILE = Path("meshtastic_listener.json")
DEFAULT_RADIO_MODE = "longfast"
DEFAULT_OUTPUT_FILE = "meshtastic_messages.log"

@dataclass(frozen=True)
class ListenerConfig:
    meshtastic_port: Optional[str]
    output_path: Path
    radio_mode: str

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text("utf-8"))
    except json.JSONDecodeError:
        return {}

def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def load_config(config_path: Optional[Path] = None) -> ListenerConfig:
    env = os.environ

    resolved_path = (
        Path(env["MESHTASTIC_LISTENER_CONFIG"])
        if "MESHTASTIC_LISTENER_CONFIG" in env
        else (config_path or DEFAULT_CONFIG_FILE)
    )

    raw = _load_json(resolved_path)

    meshtastic_port = (
        _as_optional_str(env.get("MESHTASTIC_LISTENER_RADIO_PORT"))
        or _as_optional_str(raw.get("meshtastic_port"))
    )

    output_path_str = (
        env.get("MESHTASTIC_LISTENER_OUTPUT")
        or raw.get("output_path")
        or DEFAULT_OUTPUT_FILE
    )
    output_path = Path(output_path_str)

    radio_mode = (
        _as_optional_str(env.get("MESHTASTIC_LISTENER_RADIO_MODE"))
        or _as_optional_str(raw.get("radio_mode"))
        or DEFAULT_RADIO_MODE
    )

    return ListenerConfig(
        meshtastic_port=meshtastic_port,
        output_path=output_path,
        radio_mode=radio_mode,
    )

