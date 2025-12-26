from __future__ import annotations

import logging
import time
from typing import Optional, Set

from .configuration import AppConfig, load_config
from .gps import SerialGpsReader
from .radio import MeshtasticClient
from .serial_utils import auto_detect_radio_port

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _select_radio_port(config: AppConfig) -> Optional[str]:
    if config.meshtastic_port:
        return config.meshtastic_port

    candidate = auto_detect_radio_port(
        exclude_ports={config.gps_port} if config.gps_port else set()
    )
    if candidate:
        logger.info("Auto-detected radio port %s", candidate)
    else:
        logger.warning(
            "Unable to auto-detect radio port. Set MESHTASTIC_PINGER_RADIO_PORT if detection fails."
        )
    return candidate


def _run_loop(config: AppConfig) -> None:
    radio_port = _select_radio_port(config)
    exclude_ports: Set[str] = {radio_port} if radio_port else set()
    with SerialGpsReader(
        port=config.gps_port,
        exclude_ports=exclude_ports,
    ) as gps_reader, MeshtasticClient(
        target_node=config.target_node,
        device=radio_port or config.meshtastic_port,
        want_ack=config.radio_ack,
        radio_mode=config.radio_mode,
    ) as radio:
        while True:
            logger.info("Awaiting GPS fix (timeout=%ss)", config.gps_timeout_seconds)
            try:
                fix = gps_reader.get_fix(config.gps_timeout_seconds)
            except TimeoutError as exc:  # pragma: no cover - hardware dependent outcome
                logger.warning("GPS fix timed out: %s", exc)
                continue

            logger.info(
                "GPS fix acquired: lat=%f lon=%f hdop=%s sats=%s time=%s",
                fix.lat,
                fix.lon,
                fix.hdop if fix.hdop is not None else "n/a",
                fix.satellites if fix.satellites is not None else "n/a",
                fix.timestamp.isoformat(),
            )

            try:
                radio.send_fix(fix, config.message_template)
            except Exception as exc:  # pragma: no cover - depends on serial hardware
                logger.error("Failed to send Meshtastic message: %s", exc)

            if config.send_interval_seconds > 0:
                logger.info("Sleeping for %s seconds before next fix", config.send_interval_seconds)
                time.sleep(config.send_interval_seconds)


def main():
    _configure_logging()
    try:
        config = load_config()
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise SystemExit(1) from exc

    logger.info("Starting GPS-to-Meshtastic relay (target=%s)", config.target_node)
    try:
        _run_loop(config)
    except KeyboardInterrupt:
        logger.info("Stopping on user request")

