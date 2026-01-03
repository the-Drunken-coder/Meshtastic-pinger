"""Main entry point for the Meshtastic mapper tool."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from .map_generator import generate_map_html
from .parser import parse_messages_file

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Configure logging for the mapper."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main() -> None:
    """Main function to parse messages and generate map."""
    _configure_logging()

    # Default input/output paths
    input_file = Path("meshtastic_messages.txt")
    output_file = Path("meshtastic_map.html")

    # Allow override via command line args (but keep it simple)
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_file = Path(sys.argv[2])

    if not input_file.exists():
        logger.error("Input file not found: %s", input_file)
        sys.exit(1)

    logger.info("Parsing messages from %s", input_file)
    messages = parse_messages_file(input_file)

    if not messages:
        logger.error("No GPS messages found in %s", input_file)
        sys.exit(1)

    logger.info("Found %d GPS messages", len(messages))
    logger.info("Generating map to %s", output_file)

    try:
        generate_map_html(messages, output_file)
        logger.info("Map generated successfully: %s", output_file.resolve())
        logger.info("Open %s in your web browser to view the map", output_file)
    except Exception as exc:
        logger.error("Failed to generate map: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
