from __future__ import annotations

import argparse
import json

from grid_live import __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="grid-live")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("command", choices=["doctor"])
    args = parser.parse_args()
    if args.command == "doctor":
        print(
            json.dumps(
                {
                    "application": "grid-live",
                    "entries_blocked": True,
                    "reason": "Gate 6/7 not passed; no execution adapter is installed",
                    "status": "scaffolded",
                }
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
