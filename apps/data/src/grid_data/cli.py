"""Command line entrypoint for the independently installable grid-data app."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from grid_bybit_public import BybitArchiveIndex, BybitPublicClient, UrllibJsonTransport

from grid_data import __version__
from grid_data.archive_inventory import build_archive_inventory
from grid_data.evidence import publish_evidence, verify_evidence
from grid_data.inventory import build_public_inventory


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="grid-data")
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="verify that the public-only runtime imports")
    doctor.set_defaults(handler=_doctor)

    inventory = commands.add_parser("inventory", help="inventory Bybit linear instruments")
    inventory.add_argument("--base-url", default="https://api.bybit.com")
    inventory.add_argument("--output", type=Path, required=True)
    inventory.add_argument("--force", action="store_true")
    inventory.set_defaults(handler=_inventory)

    archive = commands.add_parser(
        "archive-inventory", help="inventory official public.bybit.com daily trade archives"
    )
    archive.add_argument("--symbols", required=True, help="comma-separated symbols")
    archive.add_argument("--output", type=Path, required=True)
    archive.add_argument("--force", action="store_true")
    archive.set_defaults(handler=_archive_inventory)

    verify = commands.add_parser("verify-evidence", help="verify a feasibility receipt")
    verify.add_argument("artifact", type=Path)
    verify.set_defaults(handler=_verify)
    return root


def _doctor(_args: argparse.Namespace) -> int:
    print(json.dumps({"application": "grid-data", "network": "public-only", "status": "ready"}))
    return 0


def _inventory(args: argparse.Namespace) -> int:
    client = BybitPublicClient(UrllibJsonTransport(base_url=args.base_url))
    payload = build_public_inventory(client)
    artifact, receipt = publish_evidence(args.output, payload, force=args.force)
    print(
        json.dumps(
            {"artifact": str(artifact), "receipt": str(receipt), "summary": payload["summary"]}
        )
    )
    return 0


def _archive_inventory(args: argparse.Namespace) -> int:
    symbols = tuple(
        sorted({symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()})
    )
    if not symbols:
        raise ValueError("at least one symbol is required")
    payload = build_archive_inventory(BybitArchiveIndex(), symbols)
    artifact, receipt = publish_evidence(args.output, payload, force=args.force)
    print(
        json.dumps(
            {
                "archive_symbol_count": payload["archive_symbol_count"],
                "artifact": str(artifact),
                "coverage": payload["coverage"],
                "products": payload["products"],
                "receipt": str(receipt),
            }
        )
    )
    return 0


def _verify(args: argparse.Namespace) -> int:
    valid = verify_evidence(args.artifact)
    print(json.dumps({"artifact": str(args.artifact.resolve()), "valid": valid}))
    return 0 if valid else 2


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
