"""Measure the merged pooled public REST transport without retaining market values."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Final, cast

from grid_bybit_public import BybitPublicClient, PooledHttpsJsonTransport
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from grid_data.host_probe import probe_host_snapshot
from grid_data.rest_throughput import ThroughputProfile, build_rest_throughput_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

EVIDENCE_CONTRACT: Final = "grid.phase2-pooled-public-rest-performance/v1"
TRANSPORT_POLICY: Final = "bounded-http11-keep-alive-v1"
IMPLEMENTATION_RE = re.compile(r"git:[0-9a-f]{40}")
PROFILE: Final = ThroughputProfile(workers=24, target_rps=10)
PLANNED_REQUESTS: Final = 100
STAGE_SECONDS: Final = Decimal("10")
SAMPLE_SIZE: Final = 8


class PooledRestPerformanceError(RuntimeError):
    """The bounded performance measurement or its evidence failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PooledRestPerformanceError(message)


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PooledRestPerformanceError(f"{name} must be an object")
    return cast(dict[str, Any], value)


def _integer(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PooledRestPerformanceError(f"{name} must be an integer >= {minimum}")
    return value


def _decimal(value: object, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise PooledRestPerformanceError(f"{name} must be decimal text")
    try:
        parsed = Decimal(value)
    except Exception as error:
        raise PooledRestPerformanceError(f"{name} is invalid decimal text") from error
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise PooledRestPerformanceError(f"{name} is outside its allowed range")
    return parsed


def _decimal_text(value: Decimal, *, places: int = 6) -> str:
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _elapsed_ns(value: object, name: str) -> int:
    seconds = _decimal(value, name, positive=True)
    return int((seconds * Decimal(1_000_000_000)).to_integral_value(rounding=ROUND_HALF_UP))


def _profile(payload: Mapping[str, Any], name: str) -> dict[str, Any]:
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, list) or len(raw_profiles) != 1:
        raise PooledRestPerformanceError(f"{name} profile differs")
    profile = _mapping(raw_profiles[0], f"{name} profile")
    _require(profile.get("workers") == PROFILE.workers, f"{name} workers differ")
    _require(
        profile.get("target_requests_per_second") == PROFILE.target_rps,
        f"{name} target RPS differs",
    )
    return profile


def _verified_json(path: Path, name: str) -> tuple[Path, dict[str, Any]]:
    resolved = path.resolve()
    _require(verify_evidence(resolved), f"{name} receipt verification failed")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PooledRestPerformanceError(f"{name} is not readable JSON") from error
    return resolved, _mapping(raw, name)


def _measurement(profile: Mapping[str, Any]) -> dict[str, object]:
    latency = _mapping(profile.get("latency_ms"), "measurement latency")
    normalized_latency = {
        key: _decimal_text(_decimal(latency.get(key), f"latency {key}", positive=True), places=3)
        for key in ("min", "p50", "p95", "p99", "max")
    }
    ordered_latency = tuple(
        Decimal(normalized_latency[key]) for key in ("min", "p50", "p95", "p99", "max")
    )
    _require(ordered_latency == tuple(sorted(ordered_latency)), "latency percentiles are unordered")
    return {
        "actual_request_count": _integer(
            profile.get("actual_request_count"), "actual request count", minimum=1
        ),
        "error_count": _integer(profile.get("error_count"), "error count"),
        "full_page_count": _integer(profile.get("full_page_count"), "full page count"),
        "latency_ms": normalized_latency,
        "observed_requests_per_second": _decimal_text(
            _decimal(
                profile.get("observed_requests_per_second"),
                "observed requests per second",
                positive=True,
            )
        ),
        "observed_rows_per_second": _decimal_text(
            _decimal(
                profile.get("observed_rows_per_second"),
                "observed rows per second",
                positive=True,
            )
        ),
        "response_hash_aggregate": profile.get("response_hash_aggregate"),
        "row_count": _integer(profile.get("row_count"), "row count", minimum=1),
        "status": profile.get("status"),
        "success_count": _integer(profile.get("success_count"), "success count"),
        "target_attainment_ratio": _decimal_text(
            _decimal(profile.get("target_attainment_ratio"), "target attainment ratio")
        ),
        "wall_elapsed_ns": _elapsed_ns(
            profile.get("wall_duration_seconds"), "wall duration seconds"
        ),
    }


def _validate_probe(payload: Mapping[str, Any], name: str) -> None:
    request_audit = _mapping(payload.get("request_audit"), f"{name} request audit")
    _require(
        request_audit
        == {
            "actual_request_count": PLANNED_REQUESTS,
            "executed_profile_count": 1,
            "max_requests": PLANNED_REQUESTS,
            "planned_profile_count": 1,
            "planned_request_count": PLANNED_REQUESTS,
        },
        f"{name} request audit differs",
    )
    workload = _mapping(payload.get("workload"), f"{name} workload")
    _require(workload.get("base_url") == "https://api.bybit.com", f"{name} base URL differs")
    _require(workload.get("stage_seconds") == "10", f"{name} stage duration differs")
    _require(workload.get("kline_page_limit") == 1000, f"{name} page limit differs")
    _require(workload.get("page_minutes") == 1000, f"{name} page span differs")
    _require(workload.get("transport_max_attempts") == 1, f"{name} attempts differ")
    _require(
        workload.get("dataset_mix") == {"mark_price_1m": 50, "trade_price_1m": 50},
        f"{name} dataset mix differs",
    )
    storage = _mapping(payload.get("storage_policy"), f"{name} storage policy")
    _require(storage.get("market_rows_persisted") is False, f"{name} persisted rows")
    _require(storage.get("market_values_persisted") is False, f"{name} persisted values")
    _require(storage.get("tick_rows_requested") is False, f"{name} requested ticks")


def build_sanitized_performance_evidence(
    measured: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    generated_at_utc: str,
    implementation_identity: str,
    inventory_artifact_sha256: str,
    source_assessment_artifact_sha256: str,
    workstation_artifact_sha256: str,
    baseline_artifact_sha256: str,
    memory_total_bytes: int,
    memory_available_bytes: int,
    volume_free_bytes: int,
    storage_kind: str,
) -> dict[str, Any]:
    """Reduce the existing bounded probe to an identifier-free merged-code result."""

    _require(bool(IMPLEMENTATION_RE.fullmatch(implementation_identity)), "identity is invalid")
    _require(measured.get("evidence_schema") == "grid.bybit-rest-throughput/v1", "schema differs")
    _require(baseline.get("evidence_schema") == "grid.bybit-rest-throughput/v1", "baseline differs")
    _require(measured.get("status") == "bounded-benchmark-complete", "measurement incomplete")
    _require(baseline.get("status") == "bounded-benchmark-complete", "baseline incomplete")
    _validate_probe(measured, "measurement")
    _validate_probe(baseline, "baseline")
    _require(measured.get("selection") == baseline.get("selection"), "selection differs")
    measured_profile = _profile(measured, "measurement")
    baseline_profile = _profile(baseline, "baseline")
    measurement = _measurement(measured_profile)
    prior = _measurement(baseline_profile)
    _require(measurement["actual_request_count"] == PLANNED_REQUESTS, "request count differs")
    _require(measurement["success_count"] == PLANNED_REQUESTS, "not every request succeeded")
    _require(measurement["error_count"] == 0, "measurement contains endpoint errors")
    _require(measurement["full_page_count"] == PLANNED_REQUESTS, "full-page count differs")
    _require(measurement["row_count"] == 100_000, "row count differs")
    _require(prior["actual_request_count"] == PLANNED_REQUESTS, "baseline requests differ")
    _require(prior["success_count"] == PLANNED_REQUESTS, "baseline successes differ")
    _require(prior["error_count"] == 0, "baseline contains errors")
    _require(prior["full_page_count"] == PLANNED_REQUESTS, "baseline full pages differ")
    _require(prior["row_count"] == 100_000, "baseline row count differs")
    _require(
        measurement["response_hash_aggregate"] == prior["response_hash_aggregate"],
        "response aggregate differs from baseline",
    )
    measured_rps = _decimal(
        measurement["observed_requests_per_second"], "measured RPS", positive=True
    )
    baseline_rps = _decimal(prior["observed_requests_per_second"], "baseline RPS", positive=True)
    measured_elapsed = cast(int, measurement["wall_elapsed_ns"])
    baseline_elapsed = cast(int, prior["wall_elapsed_ns"])
    speedup = measured_rps / baseline_rps
    elapsed_reduction = (Decimal(baseline_elapsed - measured_elapsed) / baseline_elapsed) * 100
    status = (
        "measured-pooled-public-rest-throughput"
        if speedup > 1 and measured_elapsed < baseline_elapsed
        else "measured-no-speedup"
    )
    runtime = _mapping(measured.get("runtime"), "measurement runtime")
    payload: dict[str, Any] = {
        "assurances": {
            "adaptive_rate_limit_policy_changed": False,
            "credentials_or_private_endpoint_used": False,
            "market_rows_or_values_persisted": False,
            "network_request_count": PLANNED_REQUESTS,
            "request_retry_or_rate_ceiling_changed": False,
            "source_response_pages_validated_in_memory": True,
        },
        "baseline": prior,
        "bindings": {
            "baseline_artifact_sha256": baseline_artifact_sha256,
            "implementation_identity": implementation_identity,
            "inventory_artifact_sha256": inventory_artifact_sha256,
            "source_assessment_artifact_sha256": source_assessment_artifact_sha256,
            "workstation_artifact_sha256": workstation_artifact_sha256,
        },
        "comparison": {
            "observed_request_rate_speedup_ratio": _decimal_text(speedup),
            "wall_elapsed_reduction_percent": _decimal_text(elapsed_reduction),
        },
        "configuration": {
            "max_connections": PROFILE.workers,
            "planned_request_count": PLANNED_REQUESTS,
            "sample_size": SAMPLE_SIZE,
            "stage_seconds": int(STAGE_SECONDS),
            "target_requests_per_second": PROFILE.target_rps,
            "transport_max_attempts": 1,
            "transport_policy": TRANSPORT_POLICY,
            "workers": PROFILE.workers,
        },
        "content_sha256": "",
        "environment": {
            "logical_cpu_count": runtime.get("logical_cpu_count"),
            "memory_available_bytes": memory_available_bytes,
            "memory_total_bytes": memory_total_bytes,
            "platform_machine": runtime.get("platform_machine"),
            "platform_system": runtime.get("platform_system"),
            "python_version": runtime.get("python_version"),
            "storage_kind": storage_kind,
            "volume_free_bytes": volume_free_bytes,
        },
        "evidence_schema": EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at_utc,
        "limitations": [
            "This is one bounded 100-request observation from one host and network route.",
            (
                "The baseline used the prior urllib transport on the same owner laptop but a "
                "different run time."
            ),
            (
                "The probe retains no response rows or market values and does not measure full "
                "campaign publication."
            ),
            (
                "The result changes no Gate 2 criterion, does not authorize Phase 3, and enables "
                "no live action."
            ),
        ],
        "measurement": measurement,
        "status": status,
    }
    hash_input = dict(payload)
    hash_input.pop("content_sha256")
    payload["content_sha256"] = canonical_sha256(hash_input)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-identity", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--instrument-inventory", type=Path, required=True)
    parser.add_argument("--source-assessment", type=Path, required=True)
    parser.add_argument("--workstation-snapshot", type=Path, required=True)
    parser.add_argument("--baseline-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    output, _receipt = preflight_evidence(args.output)
    inventory_path, inventory = _verified_json(args.instrument_inventory, "inventory")
    source_path, source = _verified_json(args.source_assessment, "source assessment")
    workstation_path, workstation = _verified_json(args.workstation_snapshot, "workstation")
    baseline_path, baseline = _verified_json(args.baseline_result, "baseline")
    schema_path = (
        args.repo_root.resolve()
        / "schemas"
        / "evidence"
        / "v1"
        / "phase2-pooled-public-rest-performance.schema.json"
    )
    schema = _mapping(json.loads(schema_path.read_text(encoding="utf-8")), "schema")
    host = probe_host_snapshot(output.parent)
    with PooledHttpsJsonTransport(max_attempts=1, max_connections=PROFILE.workers) as transport:
        measured = build_rest_throughput_evidence(
            lambda: BybitPublicClient(transport),
            inventory,
            source,
            command="sanitized-by-wrapper",
            base_url="https://api.bybit.com",
            inventory_artifact=inventory_path.name,
            inventory_artifact_sha256=sha256_file(inventory_path),
            source_assessment_artifact=source_path.name,
            source_assessment_artifact_sha256=sha256_file(source_path),
            workstation_artifact=workstation_path.name,
            workstation_artifact_sha256=sha256_file(workstation_path),
            workstation_captured_at_utc=cast(str, workstation["observed_at_utc"]),
            profiles=(PROFILE,),
            stage_seconds=STAGE_SECONDS,
            cooldown_seconds=Decimal(0),
            sample_size=SAMPLE_SIZE,
            max_requests=PLANNED_REQUESTS,
        )
    payload = build_sanitized_performance_evidence(
        measured,
        baseline,
        generated_at_utc=cast(str, measured["fetched_at_utc"]),
        implementation_identity=args.implementation_identity,
        inventory_artifact_sha256=sha256_file(inventory_path),
        source_assessment_artifact_sha256=sha256_file(source_path),
        workstation_artifact_sha256=sha256_file(workstation_path),
        baseline_artifact_sha256=sha256_file(baseline_path),
        memory_total_bytes=host.memory_total_bytes,
        memory_available_bytes=host.memory_available_bytes,
        volume_free_bytes=host.volume_free_bytes,
        storage_kind=host.storage_kind,
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "observed_requests_per_second": payload["measurement"][
                    "observed_requests_per_second"
                ],
                "receipt": str(receipt),
                "speedup_ratio": payload["comparison"]["observed_request_rate_speedup_ratio"],
                "status": payload["status"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
