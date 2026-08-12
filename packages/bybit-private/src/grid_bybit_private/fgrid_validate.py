"""Exact request and redacted feasibility result for native Futures Grid validate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from grid_contracts.canonical import canonical_sha256, decimal_text

EXPECTED_CHECK_CODE = "FGRID_CHECK_CODE_UNSPECIFIED"
VALIDATE_ENDPOINT = "/v5/fgridbot/validate"


class ValidateTransport(Protocol):
    environment: str

    def validate(self, payload: Mapping[str, str]) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class FuturesGridValidateRequest:
    symbol: str
    cell_number: int
    min_price: Decimal
    max_price: Decimal
    leverage: Decimal
    stop_loss_price: Decimal
    take_profit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.symbol or self.symbol != self.symbol.upper() or not self.symbol.isalnum():
            raise ValueError("symbol must be non-empty uppercase alphanumeric text")
        if not 2 <= self.cell_number <= 400:
            raise ValueError("cell_number must be in [2, 400]")
        for name in ("min_price", "max_price", "leverage", "stop_loss_price"):
            _require_positive_decimal(name, getattr(self, name))
        if self.take_profit_price is not None:
            _require_positive_decimal("take_profit_price", self.take_profit_price)
        if self.min_price >= self.max_price:
            raise ValueError("min_price must be below max_price")
        if self.leverage > Decimal(100):
            raise ValueError("leverage must not exceed the documented V1 maximum of 100")
        if self.stop_loss_price >= self.min_price:
            raise ValueError("neutral-grid stop_loss_price must be below min_price")
        if self.take_profit_price is not None and self.take_profit_price <= self.max_price:
            raise ValueError("take_profit_price must be above max_price")

    def payload(self) -> dict[str, str]:
        result = {
            "cell_number": str(self.cell_number),
            "grid_mode": "1",
            "grid_type": "2",
            "leverage": decimal_text(self.leverage),
            "max_price": decimal_text(self.max_price),
            "min_price": decimal_text(self.min_price),
            "stop_loss_price": decimal_text(self.stop_loss_price),
            "symbol": self.symbol,
        }
        if self.take_profit_price is not None:
            result["take_profit_price"] = decimal_text(self.take_profit_price)
        return result


def build_probe_report(
    transport: ValidateTransport,
    request: FuturesGridValidateRequest,
) -> dict[str, Any]:
    payload = request.payload()
    response = transport.validate(payload)
    ret_code = response.get("retCode")
    result = response.get("result")
    result_mapping = result if isinstance(result, Mapping) else {}
    check_code = result_mapping.get("check_code", response.get("check_code"))
    valid_ret_code = type(ret_code) is int
    successful = valid_ret_code and ret_code == 0 and check_code == EXPECTED_CHECK_CODE
    report: dict[str, Any] = {
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "endpoint": VALIDATE_ENDPOINT,
        "environment": transport.environment,
        "probe_schema": "grid.bybit-fgrid-validate-probe/v1",
        "request": payload,
        "response": response,
        "result": {
            "check_code": check_code if isinstance(check_code, str) else None,
            "ret_code": ret_code if valid_ret_code else None,
            "successful": successful,
        },
        "safety": {
            "credentials_persisted": False,
            "mutating_endpoint_called": False,
            "validate_only": True,
        },
    }
    report["content_sha256"] = canonical_sha256(report)
    return report


def _require_positive_decimal(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a finite positive Decimal")
