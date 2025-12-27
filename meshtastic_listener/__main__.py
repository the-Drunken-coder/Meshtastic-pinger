import sys
from pathlib import Path

# Add the project root to sys.path to allow running this file directly
if __name__ == "__main__" and __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    __package__ = "meshtastic_listener"

from .listener import main

if __name__ == "__main__":
    main()
