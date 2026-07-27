#!/usr/bin/env python3
"""Entry point locale per il lint della wiki."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cyclist_kb.wiki_lint import main


if __name__ == "__main__":
    raise SystemExit(main())
