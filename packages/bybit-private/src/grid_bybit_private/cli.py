"""Owner-controlled CLI for the M1 native Futures Grid validate-only probe."""

from __future__ import annotations

import argparse
import json
import os
from decimal import Decimal, InvalidOperation
from pathlib import Path

from grid_bybit_private.evidence import (
    publish_private_report,
    resolve_private_output,
    verify_private_report,
)
from grid_bybit_private.fgrid_validate import FuturesGridValidateRequest, build_probe_report
from grid_bybit_private.transport import HmacValidateTransport


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="grid-bybit-validate")
    commands = root.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor", help="show the hard-coded validate-only boundary")
    doctor.set_defaults(handler=_doctor)

    probe = commands.add_parser("probe", help="call native Futures Grid validate; never create")
    probe.add_argument("--symbol", required=True)
    probe.add_argument("--cell-number", required=True, type=int)
    probe.add_argument("--min-price", required=True, type=_decimal)
    probe.add_argument("--max-price", required=True, type=_decimal)
    probe.add_argument("--leverage", required=True, type=_decimal)
    probe.add_argument("--stop-loss-price", required=True, type=_decimal)
    probe.add_argument("--take-profit-price", type=_decimal)
    probe.add_argument("--environment", choices=("testnet", "mainnet"), default="testnet")
    probe.add_argument("--acknowledge-mainnet-validate-only", action="store_true")
    probe.add_argument("--output", required=True, type=Path)
    probe.set_defaults(handler=_probe)

    verify = commands.add_parser("verify", help="verify a private probe receipt")
    verify.add_argument("artifact", type=Path)
    verify.set_defaults(handler=_verify)
    return root


def _doctor(_args: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "allowed_endpoint": "/v5/fgridbot/validate",
                "application": "grid-bybit-validate",
                "credentials": "environment-only",
                "mutating_endpoints": False,
                "status": "ready",
            }
        )
    )
    return 0


def _probe(args: argparse.Namespace) -> int:
    if args.environment == "mainnet" and not args.acknowledge_mainnet_validate_only:
        raise ValueError("mainnet requires --acknowledge-mainnet-validate-only")
    output = resolve_private_output(args.output)
    api_key, api_secret = _credentials(args.environment)
    request = FuturesGridValidateRequest(
        symbol=args.symbol.upper(),
        cell_number=args.cell_number,
        min_price=args.min_price,
        max_price=args.max_price,
        leverage=args.leverage,
        stop_loss_price=args.stop_loss_price,
        take_profit_price=args.take_profit_price,
    )
    transport = HmacValidateTransport(
        environment=args.environment,
        api_key=api_key,
        api_secret=api_secret,
    )
    report = build_probe_report(transport, request)
    artifact, receipt = publish_private_report(output, report)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "environment": args.environment,
                "receipt": str(receipt),
                "successful": report["result"]["successful"],
            }
        )
    )
    return 0 if report["result"]["successful"] else 2


def _verify(args: argparse.Namespace) -> int:
    valid = verify_private_report(args.artifact)
    print(json.dumps({"artifact": str(args.artifact.resolve()), "valid": valid}))
    return 0 if valid else 2


def _credentials(environment: str) -> tuple[str, str]:
    prefix = "BYBIT_TESTNET" if environment == "testnet" else "BYBIT_MAINNET"
    key_name = f"{prefix}_API_KEY"
    secret_name = f"{prefix}_API_SECRET"
    api_key = os.environ.get(key_name, "")
    api_secret = os.environ.get(secret_name, "")
    if not api_key or not api_secret:
        raise ValueError(f"set {key_name} and {secret_name} in the process environment")
    return api_key, api_secret


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise argparse.ArgumentTypeError("expected exact decimal text") from error
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError("expected finite decimal text")
    return parsed


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
