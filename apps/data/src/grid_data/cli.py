"""Command line entrypoint for the independently installable grid-data app."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from grid_bybit_public import (
    BybitArchiveIndex,
    BybitHistoricalDataCatalog,
    BybitPublicClient,
    UrllibJsonTransport,
)
from grid_contracts.canonical import sha256_file

from grid_data import __version__
from grid_data.archive_inventory import (
    build_archive_coverage_matrix,
    build_archive_inventory,
    load_verified_public_inventory,
)
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from grid_data.history_sources import (
    build_history_source_assessment,
    build_one_minute_history_source_assessment,
)
from grid_data.inventory import build_public_inventory
from grid_data.public_sample import build_public_sample


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

    archive_coverage = commands.add_parser(
        "archive-coverage",
        help="compare current USDT perpetuals with bounded official archive coverage",
    )
    archive_coverage.add_argument("--instrument-inventory", type=Path, required=True)
    archive_coverage.add_argument("--sample-size", type=int, default=20)
    archive_coverage.add_argument("--output", type=Path, required=True)
    archive_coverage.add_argument("--force", action="store_true")
    archive_coverage.set_defaults(handler=_archive_coverage)

    history_sources = commands.add_parser(
        "history-source-assessment",
        help="assess official bulk products and bound required REST backfill",
    )
    history_sources.add_argument("--instrument-inventory", type=Path, required=True)
    history_sources.add_argument("--output", type=Path, required=True)
    history_sources.add_argument("--force", action="store_true")
    history_sources.set_defaults(handler=_history_source_assessment)

    one_minute_history_sources = commands.add_parser(
        "history-source-assessment-1m",
        help="record the 1m-only source policy and REST bootstrap envelope",
    )
    one_minute_history_sources.add_argument("--instrument-inventory", type=Path, required=True)
    one_minute_history_sources.add_argument("--output", type=Path, required=True)
    one_minute_history_sources.add_argument("--force", action="store_true")
    one_minute_history_sources.set_defaults(handler=_one_minute_history_source_assessment)

    sample = commands.add_parser(
        "public-sample", help="summarize bounded trade/mark/funding public samples"
    )
    sample.add_argument("--symbol", required=True)
    sample.add_argument("--start-ms", required=True, type=int)
    sample.add_argument("--end-ms", required=True, type=int)
    sample.add_argument("--base-url", default="https://api.bybit.com")
    sample.add_argument("--output", type=Path, required=True)
    sample.add_argument("--force", action="store_true")
    sample.set_defaults(handler=_public_sample)

    verify = commands.add_parser("verify-evidence", help="verify a feasibility receipt")
    verify.add_argument("artifact", type=Path)
    verify.set_defaults(handler=_verify)
    return root


def _doctor(_args: argparse.Namespace) -> int:
    print(json.dumps({"application": "grid-data", "network": "public-only", "status": "ready"}))
    return 0


def _inventory(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    client = BybitPublicClient(UrllibJsonTransport(base_url=args.base_url))
    payload = build_public_inventory(client)
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {"artifact": str(artifact), "receipt": str(receipt), "summary": payload["summary"]}
        )
    )
    return 0


def _archive_inventory(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    symbols = tuple(
        sorted({symbol.strip().upper() for symbol in args.symbols.split(",") if symbol.strip()})
    )
    if not symbols:
        raise ValueError("at least one symbol is required")
    payload = build_archive_inventory(BybitArchiveIndex(), symbols)
    artifact, receipt = publish_evidence(output, payload, force=args.force)
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


def _archive_coverage(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    inventory = load_verified_public_inventory(args.instrument_inventory)
    payload = build_archive_coverage_matrix(
        BybitArchiveIndex(),
        inventory,
        inventory_artifact_sha256=sha256_file(args.instrument_inventory.resolve()),
        sample_size=args.sample_size,
    )
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "coverage_findings": payload["coverage_findings"],
                "receipt": str(receipt),
                "universe_comparison": payload["universe_comparison"],
            }
        )
    )
    return 0


def _public_sample(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    client = BybitPublicClient(UrllibJsonTransport(base_url=args.base_url))
    payload = build_public_sample(
        client,
        symbol=args.symbol.upper(),
        start_ms=args.start_ms,
        end_ms=args.end_ms,
    )
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "datasets": payload["datasets"],
                "receipt": str(receipt),
                "sample_status": payload["sample_status"],
            }
        )
    )
    return 0


def _history_source_assessment(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    inventory_path = args.instrument_inventory.resolve()
    inventory = load_verified_public_inventory(inventory_path)
    products = BybitHistoricalDataCatalog().products()
    payload = build_history_source_assessment(
        products,
        inventory,
        command=shlex.join(sys.argv),
        inventory_artifact=inventory_path.name,
        inventory_artifact_sha256=sha256_file(inventory_path),
    )
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "assessment": payload["assessment"],
                "receipt": str(receipt),
                "theoretical_rest_envelope": payload["theoretical_rest_envelope"],
            }
        )
    )
    return 0


def _one_minute_history_source_assessment(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    inventory_path = args.instrument_inventory.resolve()
    inventory = load_verified_public_inventory(inventory_path)
    products = BybitHistoricalDataCatalog().products()
    payload = build_one_minute_history_source_assessment(
        products,
        inventory,
        command=shlex.join(sys.argv),
        inventory_artifact=inventory_path.name,
        inventory_artifact_sha256=sha256_file(inventory_path),
    )
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "assessment": payload["assessment"],
                "receipt": str(receipt),
                "theoretical_rest_envelope": payload["theoretical_rest_envelope"],
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
