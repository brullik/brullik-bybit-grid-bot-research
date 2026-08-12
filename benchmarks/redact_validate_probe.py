"""Publish a non-secret conclusion from a verified private validate-only probe."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from grid_bybit_private.evidence import verify_private_report
from grid_data.evidence import preflight_evidence, publish_evidence

EXPECTED_DEMO_RET_CODE = 10032
EXPECTED_DEMO_RET_MSG = "Demo trading are not supported."


def build_redacted_conclusion(report: Mapping[str, Any]) -> dict[str, Any]:
    response = report.get("response")
    safety = report.get("safety")
    request = report.get("request")
    if not isinstance(response, Mapping):
        raise ValueError("private report response is not an object")
    if not isinstance(safety, Mapping):
        raise ValueError("private report safety section is not an object")
    if not isinstance(request, Mapping):
        raise ValueError("private report request is not an object")
    if report.get("environment") != "demo":
        raise ValueError("only an isolated Demo result may use this redaction workflow")
    if report.get("endpoint") != "/v5/fgridbot/validate":
        raise ValueError("private report is not the validate-only endpoint")
    if response.get("retCode") != EXPECTED_DEMO_RET_CODE:
        raise ValueError("Demo response was not the expected unsupported-environment result")
    if response.get("retMsg") != EXPECTED_DEMO_RET_MSG:
        raise ValueError("Demo response message was not the expected unsupported result")
    if safety.get("credentials_persisted") is not False:
        raise ValueError("private report does not prove credential non-persistence")
    if safety.get("mutating_endpoint_called") is not False:
        raise ValueError("private report does not prove the validate-only boundary")
    symbol = request.get("symbol")
    if not isinstance(symbol, str) or not symbol:
        raise ValueError("private report has no symbol")

    return {
        "conclusion": (
            "Bybit Demo explicitly rejected native Futures Grid validation as unsupported; "
            "Testnet and mainnet feasibility remain unresolved."
        ),
        "endpoint": "/v5/fgridbot/validate",
        "environment": "demo",
        "evidence_schema": "grid.bybit-fgrid-validate-conclusion/v1",
        "observed_at_utc": report.get("created_at_utc"),
        "request_summary": {
            "grid_mode": "neutral",
            "grid_type": "geometric",
            "numeric_encoding": "exact-decimal-and-integer-strings",
            "symbol": symbol,
        },
        "response_summary": {
            "check_code": None,
            "ret_code": EXPECTED_DEMO_RET_CODE,
            "ret_msg": EXPECTED_DEMO_RET_MSG,
        },
        "safety": {
            "credentials_persisted": False,
            "mainnet_fallback": False,
            "mutating_endpoint_called": False,
            "private_artifact_committed": False,
            "private_receipt_verified": True,
            "retry_count": 0,
        },
        "status": "demo-unsupported",
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    private_report = args.private_report.resolve()
    private_root = (Path.cwd() / "reports" / "private").resolve()
    if not private_report.is_relative_to(private_root):
        raise ValueError("private report must be below reports/private")
    if not verify_private_report(private_report):
        raise ValueError("private validate report receipt does not verify")
    output, _receipt = preflight_evidence(args.output, force=args.force)
    raw = json.loads(private_report.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("private validate report is not a JSON object")
    publish_evidence(output, build_redacted_conclusion(raw), force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
