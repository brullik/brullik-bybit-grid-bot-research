"""Publish a non-secret conclusion from verified Mainnet validate-only probes."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from grid_bybit_private.evidence import verify_private_report
from grid_bybit_private.fgrid_validate import EXPECTED_CHECK_CODE
from grid_data.evidence import preflight_evidence, publish_evidence

EXPECTED_SYMBOLS = frozenset({"DOGEUSDT", "LINKUSDT", "XRPUSDT"})
OFFICIAL_MCP_COMMIT = "562291168e9fd3d679275bf28c16056d562cefce"
OFFICIAL_MCP_REPOSITORY = "https://github.com/bybit-exchange/trading-mcp"


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _positive_decimal_text(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be exact decimal text")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be exact decimal text") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def _candidate(report: Mapping[str, Any]) -> tuple[Decimal, dict[str, Any]]:
    if report.get("environment") != "mainnet":
        raise ValueError("every discovery report must come from Mainnet")
    if report.get("endpoint") != "/v5/fgridbot/validate":
        raise ValueError("every discovery report must use the validate-only endpoint")

    request = _mapping(report.get("request"), "request")
    response = _mapping(report.get("response"), "response")
    result = _mapping(report.get("result"), "result")
    safety = _mapping(report.get("safety"), "safety")
    if safety.get("credentials_persisted") is not False:
        raise ValueError("private report does not prove credential non-persistence")
    if safety.get("mutating_endpoint_called") is not False:
        raise ValueError("private report does not prove the validate-only boundary")
    if safety.get("validate_only") is not True:
        raise ValueError("private report does not assert validate-only operation")
    if (
        result.get("ret_code") != 0
        or result.get("check_code") != EXPECTED_CHECK_CODE
        or result.get("successful") is not True
    ):
        raise ValueError("private report is not a successful Futures Grid validation")

    symbol = request.get("symbol")
    if not isinstance(symbol, str) or symbol not in EXPECTED_SYMBOLS:
        raise ValueError("private report symbol is outside the approved discovery set")
    investment = _mapping(
        _mapping(response.get("result"), "response.result").get("investment"),
        "response.result.investment",
    )
    minimum_investment = _positive_decimal_text(
        investment.get("from"), "response.result.investment.from"
    )

    request_summary = {
        "cell_number": request.get("cell_number"),
        "grid_mode": request.get("grid_mode"),
        "grid_type": request.get("grid_type"),
        "leverage": request.get("leverage"),
        "max_price": request.get("max_price"),
        "min_price": request.get("min_price"),
        "numeric_encoding": "exact-decimal-and-integer-strings",
        "stop_loss_price": request.get("stop_loss_price"),
        "take_profit_price": request.get("take_profit_price"),
    }
    for name in (
        "cell_number",
        "leverage",
        "max_price",
        "min_price",
        "stop_loss_price",
        "take_profit_price",
    ):
        _positive_decimal_text(request_summary[name], f"request.{name}")
    if request_summary["grid_mode"] != "1" or request_summary["grid_type"] != "2":
        raise ValueError("discovery requires Neutral Geometric grid parameters")

    public_candidate = {
        "request_summary": request_summary,
        "response_summary": {
            "check_code": EXPECTED_CHECK_CODE,
            "minimum_investment": minimum_investment,
            "ret_code": 0,
            "successful": True,
        },
        "symbol": symbol,
    }
    return Decimal(minimum_investment), public_candidate


def build_mainnet_conclusion(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(reports) != len(EXPECTED_SYMBOLS):
        raise ValueError(f"expected {len(EXPECTED_SYMBOLS)} Mainnet reports")
    ranked = [_candidate(report) for report in reports]
    symbols = [candidate[1]["symbol"] for candidate in ranked]
    if len(symbols) != len(set(symbols)) or set(symbols) != EXPECTED_SYMBOLS:
        raise ValueError("Mainnet discovery reports must cover each approved symbol exactly once")
    ranked.sort(key=lambda item: (item[0], item[1]["symbol"]))

    observed_at = []
    for report in reports:
        value = report.get("created_at_utc")
        if not isinstance(value, str) or not value:
            raise ValueError("private report has no creation timestamp")
        observed_at.append(value)

    return {
        "candidate_count": len(ranked),
        "candidates": [candidate for _investment, candidate in ranked],
        "conclusion": (
            "Bybit Mainnet accepted all three Futures Grid validate-only requests. The official "
            "create contract exists, but was not exercised; returned minimum investment values "
            "are feasibility observations, not live-trading approval."
        ),
        "create_capability": {
            "endpoint": "/v5/fgridbot/create",
            "exercised": False,
            "official_source_commit": OFFICIAL_MCP_COMMIT,
            "official_source_path": "src/tools/bot/createFGridBot.ts",
            "official_source_repository": OFFICIAL_MCP_REPOSITORY,
            "required_additional_parameter": "total_investment",
            "successful_response_identifier": "bot_id",
        },
        "endpoint": "/v5/fgridbot/validate",
        "environment": "mainnet",
        "evidence_schema": "grid.bybit-fgrid-mainnet-validate-conclusion/v1",
        "observed_at_utc": max(observed_at),
        "safety": {
            "create_endpoint_called": False,
            "credentials_persisted": False,
            "mainnet_fallback": False,
            "mutating_endpoint_called": False,
            "owner_authorization_scope": "validate-only-mainnet",
            "private_artifacts_committed": False,
            "private_receipts_verified": True,
            "request_count": len(ranked),
            "retry_count": 0,
            "unified_trading_account_confirmed_by_owner": True,
        },
        "status": "mainnet-validate-success-create-unexercised",
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-report", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    output, _receipt = preflight_evidence(args.output, force=args.force)
    private_root = (Path.cwd() / "reports" / "private").resolve()
    reports: list[Mapping[str, Any]] = []
    for private_report_arg in args.private_report:
        private_report = private_report_arg.resolve()
        if not private_report.is_relative_to(private_root):
            raise ValueError("private report must be below reports/private")
        if not verify_private_report(private_report):
            raise ValueError(f"private receipt does not verify: {private_report.name}")
        raw = json.loads(private_report.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("private validate report is not a JSON object")
        reports.append(raw)
    publish_evidence(output, build_mainnet_conclusion(reports), force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
