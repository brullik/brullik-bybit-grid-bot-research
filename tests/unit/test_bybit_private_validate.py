from __future__ import annotations

import argparse
import json
import urllib.request
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from grid_bybit_private.cli import _credentials, _probe
from grid_bybit_private.evidence import (
    PrivateEvidenceError,
    publish_private_report,
    resolve_private_output,
    verify_private_report,
)
from grid_bybit_private.fgrid_validate import (
    EXPECTED_CHECK_CODE,
    FuturesGridValidateRequest,
    build_probe_report,
)
from grid_bybit_private.transport import (
    HmacValidateTransport,
    ValidateTransportError,
    signed_headers,
)


def request() -> FuturesGridValidateRequest:
    return FuturesGridValidateRequest(
        symbol="BTCUSDT",
        cell_number=20,
        min_price=Decimal("100.00"),
        max_price=Decimal("200.00"),
        leverage=Decimal("2.00"),
        stop_loss_price=Decimal("90.00"),
        take_profit_price=Decimal("220.00"),
    )


def test_validate_payload_is_exact_neutral_geometric_string_data() -> None:
    assert request().payload() == {
        "cell_number": "20",
        "grid_mode": "1",
        "grid_type": "2",
        "leverage": "2",
        "max_price": "200",
        "min_price": "100",
        "stop_loss_price": "90",
        "symbol": "BTCUSDT",
        "take_profit_price": "220",
    }


def test_validate_request_rejects_binary_float_and_unsafe_stop_loss() -> None:
    with pytest.raises(ValueError, match="Decimal"):
        FuturesGridValidateRequest(
            symbol="BTCUSDT",
            cell_number=20,
            min_price=100.0,  # type: ignore[arg-type]
            max_price=Decimal("200"),
            leverage=Decimal("2"),
            stop_loss_price=Decimal("90"),
        )
    with pytest.raises(ValueError, match="below min_price"):
        FuturesGridValidateRequest(
            symbol="BTCUSDT",
            cell_number=20,
            min_price=Decimal("100"),
            max_price=Decimal("200"),
            leverage=Decimal("2"),
            stop_loss_price=Decimal("100"),
        )


def test_hmac_headers_match_a_fixed_vector() -> None:
    headers = signed_headers(
        body=b'{"symbol":"BTCUSDT"}',
        timestamp_ms=1_700_000_000_123,
        api_key="example-key",
        api_secret="example-secret",
        recv_window=5_000,
    )
    assert (
        headers["X-Bapi-Sign"] == "efa63b4eef4c4345113d208d893a7addb57214baaee5d7e552ae467289ebaad7"
    )
    assert headers["X-Bapi-Timestamp"] == "1700000000123"


@pytest.mark.parametrize(
    ("environment", "origin"),
    (
        ("demo", "https://api-demo.bybit.com"),
        ("mainnet", "https://api.bybit.com"),
        ("testnet", "https://api-testnet.bybit.com"),
    ),
)
def test_transport_calls_only_selected_validate_origin_and_redacts_repr(
    environment: Any, origin: str
) -> None:
    captured: dict[str, Any] = {}

    def read_response(request: urllib.request.Request, timeout: float) -> bytes:
        captured.update(url=request.full_url, body=request.data, timeout=timeout)
        return json.dumps({"retCode": 0, "result": {"check_code": EXPECTED_CHECK_CODE}}).encode()

    transport = HmacValidateTransport(
        environment=environment,
        api_key="example-key",
        api_secret="example-secret",
        clock_ms=lambda: 1_700_000_000_123,
        read_response=read_response,
    )
    response = transport.validate(request().payload())

    assert captured["url"] == f"{origin}/v5/fgridbot/validate"
    assert captured["timeout"] == 10.0
    assert b'"cell_number":"20"' in captured["body"]
    assert response["retCode"] == 0
    assert "example-key" not in repr(transport)
    assert "example-secret" not in repr(transport)


def test_demo_credentials_are_isolated_from_mainnet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BYBIT_MAINNET_API_KEY", "mainnet-key")
    monkeypatch.setenv("BYBIT_MAINNET_API_SECRET", "mainnet-secret")
    with pytest.raises(ValueError, match="BYBIT_DEMO_API_KEY"):
        _credentials("demo")

    monkeypatch.setenv("BYBIT_DEMO_API_KEY", "demo-key")
    monkeypatch.setenv("BYBIT_DEMO_API_SECRET", "demo-secret")
    assert _credentials("demo") == ("demo-key", "demo-secret")


def test_mainnet_probe_requires_explicit_acknowledgement() -> None:
    with pytest.raises(ValueError, match="acknowledge-mainnet"):
        _probe(
            argparse.Namespace(
                environment="mainnet",
                acknowledge_mainnet_validate_only=False,
            )
        )


def test_transport_rejects_a_response_that_echoes_credentials() -> None:
    transport = HmacValidateTransport(
        environment="testnet",
        api_key="example-key",
        api_secret="example-secret",
        read_response=lambda _request, _timeout: b'{"unexpected":"example-key"}',
    )
    with pytest.raises(ValidateTransportError, match="echoed credentials"):
        transport.validate(request().payload())


class FakeTransport:
    environment = "testnet"

    def __init__(self, response: Mapping[str, Any]) -> None:
        self.response = response

    def validate(self, _payload: Mapping[str, str]) -> Mapping[str, Any]:
        return self.response


def test_probe_success_requires_ret_code_and_expected_check_code() -> None:
    successful = build_probe_report(
        FakeTransport({"retCode": 0, "result": {"check_code": EXPECTED_CHECK_CODE}}),
        request(),
    )
    failed = build_probe_report(
        FakeTransport({"retCode": 0, "result": {"check_code": "OUT_OF_RANGE"}}),
        request(),
    )
    assert successful["result"]["successful"] is True
    assert failed["result"]["successful"] is False
    assert successful["safety"]["mutating_endpoint_called"] is False
    assert successful["safety"]["environment_is_simulated"] is True
    assert successful["probe_schema"] == "grid.bybit-fgrid-validate-probe/v2"


def test_probe_rejects_boolean_ret_code() -> None:
    report = build_probe_report(
        FakeTransport({"retCode": False, "result": {"check_code": EXPECTED_CHECK_CODE}}),
        request(),
    )
    assert report["result"] == {
        "check_code": EXPECTED_CHECK_CODE,
        "ret_code": None,
        "successful": False,
    }


def test_private_evidence_is_restricted_and_receipted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(PrivateEvidenceError, match="reports/private"):
        resolve_private_output(Path("public.json"))

    output = Path("reports/private/probe.json")
    artifact, receipt = publish_private_report(output, {"successful": True})
    assert artifact.is_file() and receipt.is_file()
    assert verify_private_report(artifact)
    with pytest.raises(PrivateEvidenceError, match="overwrite"):
        publish_private_report(output, {"successful": False})
