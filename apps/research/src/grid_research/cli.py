from __future__ import annotations

import argparse
import json

from grid_research import __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="grid-research")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("command", choices=["doctor"])
    args = parser.parse_args()
    if args.command == "doctor":
        print(
            json.dumps(
                {"application": "grid-research", "network": "disabled", "status": "scaffolded"}
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
