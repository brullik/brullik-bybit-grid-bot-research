"""Fail-closed handoff and progress status for the external Gate 1 campaign."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from benchmarks.gate1_review_pack import (
    DECISION_SCHEMA,
    FEATURE_SCHEMA,
    LAYOUT_SCHEMA,
    REAL_MARKET_SCHEMA,
    REVIEW_SCHEMA,
    WORKSTATION_SCHEMA,
    load_verified_evidence,
)
from benchmarks.reference_environment import collect_reference_environment
from benchmarks.reference_host import admit_reference_host

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"
PLAN_SCHEMA_NAME = "grid.reference-campaign-plan/v1"
PLAN_SCHEMA = ROOT / "schemas" / "evidence" / "v1" / "reference-campaign-plan.schema.json"
REFERENCE_ROWS = 100_000_000
REFERENCE_INSTRUMENTS = 700
EFFECTIVE_REFERENCE_ROWS = REFERENCE_ROWS - REFERENCE_ROWS % REFERENCE_INSTRUMENTS
ROW_GROUP_ROWS = 100_000
GENERATION_CHUNK_ROWS = 1_000_000

LAYOUT_WORK_DIR_NAME = "reference-layout"
LAYOUT_OUTPUT_NAME = "m1-reference-layout.json"
FEATURE_OUTPUT_NAME = "m1-reference-feature.json"
REVIEW_OUTPUT_NAME = "m1-gate1-review-pack.json"
PLAN_NAME = "campaign-plan.json"

MEASUREMENT_LEGS: tuple[tuple[str, str], ...] = (
    ("duckdb", "single-symbol"),
    ("duckdb", "universe-month"),
    ("polars", "single-symbol"),
    ("polars", "universe-month"),
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"artifact is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"artifact is not a JSON object: {path}")
    return payload


def _safe_campaign_root(path: Path) -> Path:
    root = path.resolve()
    forbidden = {Path(root.anchor).resolve(), Path.cwd().resolve(), Path.home().resolve(), ROOT}
    if root in forbidden or root.is_relative_to(ROOT):
        raise ValueError("campaign root must be a dedicated directory outside the repository")
    return root


def _source_manifest_summary() -> dict[str, Any]:
    verification = subprocess.run(
        (str(Path(sys.executable).resolve()), str(ROOT / "scripts" / "update_manifest.py")),
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    if verification.returncode != 0 or not MANIFEST.is_file():
        raise ValueError("source manifest is stale; run python scripts/update_manifest.py --write")
    source_file_count = len(MANIFEST.read_text(encoding="utf-8").splitlines())
    if source_file_count < 1:
        raise ValueError("source manifest is empty")
    return {
        "artifact": MANIFEST.name,
        "artifact_sha256": sha256_file(MANIFEST),
        "path": str(MANIFEST.resolve()),
        "source_file_count": source_file_count,
    }


def _require_reference_environment() -> dict[str, Any]:
    report = collect_reference_environment()
    if report.get("status") != "ready-for-reference-campaign":
        failures = report.get("failures")
        rendered = ", ".join(str(item) for item in failures) if isinstance(failures, list) else ""
        raise ValueError(f"reference environment preflight failed: {rendered or 'unknown failure'}")
    return report


def _source_summary(
    path: Path,
    payload: Mapping[str, Any],
    *,
    schema_key: str,
) -> dict[str, str]:
    resolved = path.resolve()
    return {
        "artifact": resolved.name,
        "artifact_sha256": sha256_file(resolved),
        "path": str(resolved),
        "schema": str(payload[schema_key]),
        "status": str(payload["status"]),
    }


def _display_command(argv: Sequence[str]) -> str:
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


def _step(
    step_id: str,
    argv: Sequence[str],
    *,
    expected_artifact: Path,
    depends_on: Sequence[str],
    requires_reboot_before: bool = False,
) -> dict[str, Any]:
    exact_argv = list(argv)
    return {
        "argv": exact_argv,
        "depends_on": list(depends_on),
        "display_command": _display_command(exact_argv),
        "expected_artifact": str(expected_artifact.resolve()),
        "id": step_id,
        "requires_reboot_before": requires_reboot_before,
    }


def _commands(
    *,
    campaign_root: Path,
    decision_path: Path,
    real_market_path: Path,
    reference_host_path: Path,
) -> list[dict[str, Any]]:
    python = str(Path(sys.executable).resolve())
    work_dir = campaign_root / LAYOUT_WORK_DIR_NAME
    preparation = work_dir / "preparation.json"
    layout_output = campaign_root / LAYOUT_OUTPUT_NAME
    feature_output = campaign_root / FEATURE_OUTPUT_NAME
    review_output = campaign_root / REVIEW_OUTPUT_NAME
    prepare = _step(
        "layout-prepare",
        (
            python,
            "-m",
            "benchmarks.reference_layout_benchmark",
            "prepare",
            "--work-dir",
            str(work_dir),
            "--profile",
            "reference",
            "--rows",
            str(REFERENCE_ROWS),
            "--instruments",
            str(REFERENCE_INSTRUMENTS),
            "--row-group-rows",
            str(ROW_GROUP_ROWS),
            "--generation-chunk-rows",
            str(GENERATION_CHUNK_ROWS),
            "--decision-evidence",
            str(decision_path),
            "--real-market-evidence",
            str(real_market_path),
            "--reference-host-evidence",
            str(reference_host_path),
        ),
        expected_artifact=preparation,
        depends_on=(),
    )
    steps = [prepare]
    previous = "layout-prepare"
    for engine, query_shape in MEASUREMENT_LEGS:
        step_id = f"layout-measure-{engine}-{query_shape}"
        steps.append(
            _step(
                step_id,
                (
                    python,
                    "-m",
                    "benchmarks.reference_layout_benchmark",
                    "measure",
                    "--work-dir",
                    str(work_dir),
                    "--engine",
                    engine,
                    "--query-shape",
                    query_shape,
                    "--cache-proof",
                    "reboot",
                ),
                expected_artifact=work_dir / f"measurement-{engine}-{query_shape}.json",
                depends_on=(previous,),
                requires_reboot_before=True,
            )
        )
        previous = step_id
    steps.append(
        _step(
            "layout-finalize",
            (
                python,
                "-m",
                "benchmarks.reference_layout_benchmark",
                "finalize",
                "--work-dir",
                str(work_dir),
                "--output",
                str(layout_output),
            ),
            expected_artifact=layout_output,
            depends_on=(previous,),
        )
    )
    steps.append(
        _step(
            "feature-reference",
            (
                python,
                "-m",
                "benchmarks.feature_benchmark",
                "--profile",
                "reference",
                "--rows",
                str(REFERENCE_ROWS),
                "--instruments",
                str(REFERENCE_INSTRUMENTS),
                "--core-minutes",
                "2880",
                "--window-minutes",
                "1440",
                "--memory-limit-percent",
                "70",
                "--reference-host-evidence",
                str(reference_host_path),
                "--output",
                str(feature_output),
            ),
            expected_artifact=feature_output,
            depends_on=("layout-finalize",),
        )
    )
    steps.append(
        _step(
            "gate1-review-pack",
            (
                python,
                "-m",
                "benchmarks.gate1_review_pack",
                "--layout",
                str(layout_output),
                "--feature",
                str(feature_output),
                "--decision",
                str(decision_path),
                "--real-market",
                str(real_market_path),
                "--workstation",
                str(reference_host_path),
                "--output",
                str(review_output),
            ),
            expected_artifact=review_output,
            depends_on=("feature-reference",),
        )
    )
    return steps


def publish_campaign_plan(
    *,
    campaign_root: Path,
    reference_host_path: Path,
    decision_path: Path,
    real_market_path: Path,
) -> dict[str, Any]:
    """Admit all fixed inputs before publishing one immutable campaign plan."""

    campaign_root = _safe_campaign_root(campaign_root)
    reference_host_path = reference_host_path.resolve()
    decision_path = decision_path.resolve()
    real_market_path = real_market_path.resolve()
    workstation = load_verified_evidence(reference_host_path, WORKSTATION_SCHEMA)
    admitted = admit_reference_host(
        reference_host_path,
        required_volume_path=campaign_root,
    )
    decision = load_verified_evidence(decision_path, DECISION_SCHEMA)
    real_market = load_verified_evidence(real_market_path, REAL_MARKET_SCHEMA)
    if decision.get("status") != "decision-matrix-candidate":
        raise ValueError("layout decision evidence is not a decision-matrix candidate")
    if real_market.get("status") != "complete-bounded-real-market-skew":
        raise ValueError("real-market evidence is not a complete bounded layout result")
    _require_reference_environment()
    source_manifest = _source_manifest_summary()

    plan_path = campaign_root / PLAN_NAME
    preflight_evidence(plan_path)
    reserved_paths = (
        campaign_root / LAYOUT_WORK_DIR_NAME,
        campaign_root / LAYOUT_OUTPUT_NAME,
        campaign_root / FEATURE_OUTPUT_NAME,
        campaign_root / REVIEW_OUTPUT_NAME,
    )
    if any(path.exists() for path in reserved_paths):
        raise ValueError("campaign root already contains a reserved benchmark output path")

    steps = _commands(
        campaign_root=campaign_root,
        decision_path=decision_path,
        real_market_path=real_market_path,
        reference_host_path=reference_host_path,
    )
    payload: dict[str, Any] = {
        "campaign_root": str(campaign_root),
        "content_sha256": "",
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "evidence_schema": PLAN_SCHEMA_NAME,
        "gate_1": {
            "automatic_acceptance": False,
            "owner_decision_required": True,
            "status": "pending-owner-decision",
        },
        "limitations": [
            (
                "The plan orchestrates evidence commands but does not execute, approve, "
                "or promote them."
            ),
            "Each layout measurement requires a distinct reboot and an otherwise idle host.",
            "A complete review pack still requires an explicit owner/PM Gate 1 decision.",
            "Phase 2 history ingestion remains unauthorized while Gate 1 is pending.",
        ],
        "reference_host": admitted,
        "repository_source": {
            "root": str(ROOT),
            "source_manifest": source_manifest,
        },
        "sources": {
            "decision": _source_summary(
                decision_path,
                decision,
                schema_key="benchmark_schema",
            ),
            "real_market": _source_summary(
                real_market_path,
                real_market,
                schema_key="evidence_schema",
            ),
            "workstation": _source_summary(
                reference_host_path,
                workstation,
                schema_key="evidence_schema",
            ),
        },
        "status": "ready-to-run",
        "steps": steps,
    }
    hash_input = dict(payload)
    hash_input.pop("content_sha256")
    payload["content_sha256"] = canonical_sha256(hash_input)
    Draft202012Validator(
        _load_json(PLAN_SCHEMA),
        format_checker=FormatChecker(),
    ).validate(payload)
    publish_evidence(plan_path, payload)
    return payload


def _basic_artifact_state(
    path: Path,
    *,
    schema_key: str,
    expected_schema: str,
    expected_fields: Mapping[str, Any],
) -> tuple[str, dict[str, Any] | None, str | None]:
    if not path.exists() and not path.with_suffix(path.suffix + ".receipt.json").exists():
        return "pending", None, None
    if not verify_evidence(path):
        return "invalid", None, "completion receipt does not verify"
    try:
        payload = _load_json(path)
    except ValueError as error:
        return "invalid", None, str(error)
    if payload.get(schema_key) != expected_schema:
        return "invalid", None, f"unexpected {schema_key}"
    for key, expected in expected_fields.items():
        if payload.get(key) != expected:
            return "invalid", None, f"unexpected {key}"
    return "complete", payload, None


def _schema_artifact_state(
    path: Path,
    schema: Path,
) -> tuple[str, dict[str, Any] | None, str | None]:
    if not path.exists() and not path.with_suffix(path.suffix + ".receipt.json").exists():
        return "pending", None, None
    try:
        payload = load_verified_evidence(path, schema)
    except ValueError as error:
        return "invalid", None, str(error)
    return "complete", payload, None


def _expected_reference_input() -> dict[str, int]:
    return {
        "generation_chunk_rows": GENERATION_CHUNK_ROWS,
        "instrument_count": REFERENCE_INSTRUMENTS,
        "row_count": EFFECTIVE_REFERENCE_ROWS,
        "row_group_rows": ROW_GROUP_ROWS,
    }


def _matches_source(
    reference: object,
    source: Mapping[str, Any],
    *,
    schema_key: str,
) -> bool:
    if not isinstance(reference, Mapping):
        return False
    return all(
        reference.get(key) == expected
        for key, expected in (
            ("artifact", source["artifact"]),
            ("artifact_sha256", source["artifact_sha256"]),
            (schema_key, source["schema"]),
            ("status", source["status"]),
        )
    )


def _layout_completion_reason(
    payload: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    preparation_hash: str | None,
) -> str | None:
    preparation = payload.get("preparation")
    sources = plan["sources"]
    if (
        payload.get("profile") != "reference"
        or payload.get("status") != "reference-protocol-candidate"
        or not isinstance(preparation, Mapping)
        or preparation_hash is None
        or preparation.get("artifact_sha256") != preparation_hash
        or preparation.get("input") != _expected_reference_input()
        or preparation.get("reference_host_evidence") != plan["reference_host"]
        or not _matches_source(
            preparation.get("decision_evidence"),
            sources["decision"],
            schema_key="benchmark_schema",
        )
        or not _matches_source(
            preparation.get("real_market_evidence"),
            sources["real_market"],
            schema_key="evidence_schema",
        )
    ):
        return "final layout does not bind the campaign preparation, scale, host, or sources"
    return None


def _feature_completion_reason(
    payload: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> str | None:
    expected_input = {
        "core_minutes_per_shard": 2880,
        "instrument_count": REFERENCE_INSTRUMENTS,
        "row_count": EFFECTIVE_REFERENCE_ROWS,
        "window_minutes": 1440,
    }
    raw_input = payload.get("input")
    memory_gate = payload.get("memory_gate")
    status = payload.get("status")
    if (
        payload.get("profile") != "reference"
        or status not in {"reference-host-feature-candidate", "reference-feature-rejected-memory"}
        or not isinstance(raw_input, Mapping)
        or any(raw_input.get(key) != value for key, value in expected_input.items())
        or payload.get("reference_host_evidence") != plan["reference_host"]
        or not isinstance(memory_gate, Mapping)
        or memory_gate.get("configured_limit_percent") != 70
        or (status == "reference-host-feature-candidate") != (memory_gate.get("passed") is True)
    ):
        return "feature result does not bind the campaign scale, host, or memory limit"
    return None


def _review_completion_reason(
    payload: Mapping[str, Any],
    plan: Mapping[str, Any],
    *,
    layout_path: Path,
    layout_payload: Mapping[str, Any] | None,
    feature_path: Path,
    feature_payload: Mapping[str, Any] | None,
) -> str | None:
    if layout_payload is None or feature_payload is None:
        return "review pack exists without valid campaign layout and feature results"

    def source_summary(
        path: Path, source_payload: Mapping[str, Any], schema_key: str
    ) -> dict[str, str]:
        return {
            "artifact": path.name,
            "artifact_sha256": sha256_file(path),
            "schema": str(source_payload[schema_key]),
            "status": str(source_payload["status"]),
        }

    sources = plan["sources"]
    expected_sources = {
        "decision_layout": {
            key: sources["decision"][key]
            for key in ("artifact", "artifact_sha256", "schema", "status")
        },
        "feature": source_summary(feature_path, feature_payload, "benchmark_schema"),
        "layout": source_summary(layout_path, layout_payload, "benchmark_schema"),
        "real_market": {
            key: sources["real_market"][key]
            for key in ("artifact", "artifact_sha256", "schema", "status")
        },
        "workstation": {
            key: sources["workstation"][key]
            for key in ("artifact", "artifact_sha256", "schema", "status")
        },
    }
    gate = payload.get("gate_1")
    blockers = gate.get("blockers") if isinstance(gate, Mapping) else None
    status = payload.get("status")
    classification_matches_blockers = isinstance(blockers, list) and (
        (status == "ready-for-owner-review" and not blockers)
        or (status == "blocked-by-reference-results" and bool(blockers))
    )
    if (
        status not in {"ready-for-owner-review", "blocked-by-reference-results"}
        or not classification_matches_blockers
        or payload.get("reference_host") != plan["reference_host"]
        or payload.get("sources") != expected_sources
        or payload.get("owner_decision_required") is not True
        or gate
        != {
            "automatic_promotion": False,
            "blockers": blockers,
            "owner_decision_required": True,
            "status": "pending-owner-decision",
        }
    ):
        return "review pack does not bind the campaign results, host, sources, or owner gate"
    return None


def _current_boot_marker() -> str:
    return datetime.fromtimestamp(int(psutil.boot_time()), UTC).isoformat().replace("+00:00", "Z")


def campaign_status(plan_path: Path) -> dict[str, Any]:
    """Inspect only receipt-marked artifacts and return the next safe operator action."""

    plan_path = plan_path.resolve()
    plan = load_verified_evidence(plan_path, PLAN_SCHEMA)
    hash_input = dict(plan)
    embedded_hash = hash_input.pop("content_sha256")
    if embedded_hash != canonical_sha256(hash_input):
        raise ValueError("campaign plan embedded content hash does not verify")
    campaign_root = _safe_campaign_root(Path(str(plan["campaign_root"])))
    if plan_path != campaign_root / PLAN_NAME:
        raise ValueError("campaign plan path does not match its declared campaign root")
    workstation_path = Path(str(plan["sources"]["workstation"]["path"]))
    admitted = admit_reference_host(workstation_path, required_volume_path=campaign_root)
    if admitted != plan["reference_host"]:
        raise ValueError("current reference host admission differs from the campaign plan")
    manifest = plan["repository_source"]["source_manifest"]
    if _source_manifest_summary() != manifest:
        raise ValueError("current repository source manifest differs from the campaign plan")
    for source in plan["sources"].values():
        path = Path(str(source["path"]))
        if not verify_evidence(path) or sha256_file(path) != source["artifact_sha256"]:
            raise ValueError(f"campaign source no longer verifies: {path}")

    work_dir = campaign_root / LAYOUT_WORK_DIR_NAME
    artifact_states: dict[str, tuple[str, dict[str, Any] | None, str | None]] = {}
    artifact_states["layout-prepare"] = _basic_artifact_state(
        work_dir / "preparation.json",
        schema_key="preparation_schema",
        expected_schema="grid.reference-layout-preparation/v2",
        expected_fields={
            "profile": "reference",
            "status": "prepared-for-separated-measurement",
        },
    )
    preparation = artifact_states["layout-prepare"][1]
    if preparation is not None:
        preparation_mismatch = bool(
            preparation.get("input") != _expected_reference_input()
            or preparation.get("reference_host_evidence") != plan["reference_host"]
            or preparation.get("decision_evidence", {}).get("artifact_sha256")
            != plan["sources"]["decision"]["artifact_sha256"]
            or preparation.get("real_market_evidence", {}).get("artifact_sha256")
            != plan["sources"]["real_market"]["artifact_sha256"]
        )
        if preparation_mismatch:
            artifact_states["layout-prepare"] = (
                "invalid",
                None,
                "preparation does not bind the campaign scale, host, or source evidence",
            )
            preparation = None
    preparation_hash = (
        sha256_file(work_dir / "preparation.json") if preparation is not None else None
    )
    for engine, query_shape in MEASUREMENT_LEGS:
        step_id = f"layout-measure-{engine}-{query_shape}"
        measurement_state = _basic_artifact_state(
            work_dir / f"measurement-{engine}-{query_shape}.json",
            schema_key="measurement_schema",
            expected_schema="grid.reference-layout-measurement/v2",
            expected_fields={
                "cache_proof": "reboot",
                "engine": engine,
                "profile": "reference",
                "query_shape": query_shape,
                "status": "reboot-separated-first-read",
            },
        )
        if (
            measurement_state[0] == "complete"
            and preparation_hash is not None
            and measurement_state[1] is not None
            and measurement_state[1].get("preparation", {}).get("artifact_sha256")
            != preparation_hash
        ):
            measurement_state = (
                "invalid",
                None,
                "measurement does not bind the current preparation",
            )
        artifact_states[step_id] = measurement_state
    layout_path = campaign_root / LAYOUT_OUTPUT_NAME
    layout_state = _schema_artifact_state(layout_path, LAYOUT_SCHEMA)
    if layout_state[0] == "complete" and layout_state[1] is not None:
        reason = _layout_completion_reason(
            layout_state[1],
            plan,
            preparation_hash=preparation_hash,
        )
        if reason is not None:
            layout_state = ("invalid", None, reason)
    artifact_states["layout-finalize"] = layout_state

    feature_path = campaign_root / FEATURE_OUTPUT_NAME
    feature_state = _schema_artifact_state(feature_path, FEATURE_SCHEMA)
    if feature_state[0] == "complete" and feature_state[1] is not None:
        reason = _feature_completion_reason(feature_state[1], plan)
        if reason is not None:
            feature_state = ("invalid", None, reason)
    artifact_states["feature-reference"] = feature_state

    review_state = _schema_artifact_state(campaign_root / REVIEW_OUTPUT_NAME, REVIEW_SCHEMA)
    if review_state[0] == "complete" and review_state[1] is not None:
        reason = _review_completion_reason(
            review_state[1],
            plan,
            layout_path=layout_path,
            layout_payload=layout_state[1],
            feature_path=feature_path,
            feature_payload=feature_state[1],
        )
        if reason is not None:
            review_state = ("invalid", None, reason)
    artifact_states["gate1-review-pack"] = review_state

    ordered_steps = list(plan["steps"])
    seen_pending = False
    status_rows: list[dict[str, Any]] = []
    invalid_reasons: list[str] = []
    boot_markers: list[str] = []
    preparation_boot_marker = preparation.get("boot_marker") if preparation is not None else None
    for step in ordered_steps:
        step_id = str(step["id"])
        step_state, payload, reason = artifact_states[step_id]
        if step_state == "pending":
            seen_pending = True
        elif step_state == "complete" and seen_pending:
            step_state = "invalid"
            reason = "artifact exists out of campaign order"
        if step_state == "invalid":
            invalid_reasons.append(f"{step_id}: {reason}")
        if payload is not None and step["requires_reboot_before"]:
            marker = payload.get("boot_marker")
            if (
                not isinstance(marker, str)
                or not marker
                or marker == preparation_boot_marker
                or marker in boot_markers
            ):
                step_state = "invalid"
                reason = "measurement boot marker is missing or not distinct from prior stages"
                invalid_reasons.append(f"{step_id}: {reason}")
            else:
                boot_markers.append(marker)
        status_rows.append({"id": step_id, "reason": reason, "state": step_state})

    next_step = next(
        (
            step
            for step, row in zip(ordered_steps, status_rows, strict=True)
            if row["state"] == "pending"
        ),
        None,
    )
    if invalid_reasons:
        campaign_state = "blocked-invalid-artifact"
        next_action = None
    elif next_step is None:
        review = artifact_states["gate1-review-pack"][1]
        campaign_state = (
            "complete-ready-for-owner-review"
            if review is not None and review.get("status") == "ready-for-owner-review"
            else "complete-blocked-by-reference-results"
        )
        next_action = None
    elif next_step["requires_reboot_before"]:
        prior_markers = []
        if preparation is not None:
            marker = preparation.get("boot_marker")
            if isinstance(marker, str):
                prior_markers.append(marker)
        prior_markers.extend(boot_markers)
        if _current_boot_marker() in prior_markers:
            campaign_state = "reboot-required"
            next_action = {"action": "reboot", "then": next_step}
        else:
            campaign_state = "ready"
            next_action = {"action": "run", "step": next_step}
    else:
        campaign_state = "ready"
        next_action = {"action": "run", "step": next_step}

    return {
        "campaign_root": str(campaign_root),
        "campaign_status": campaign_state,
        "gate_1": {
            "automatic_acceptance": False,
            "owner_decision_required": True,
            "status": "pending-owner-decision",
        },
        "invalid_reasons": invalid_reasons,
        "next_action": next_action,
        "steps": status_rows,
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command_name", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--campaign-root", type=Path, required=True)
    plan.add_argument("--reference-host-evidence", type=Path, required=True)
    plan.add_argument(
        "--decision-evidence",
        type=Path,
        default=Path("benchmarks/results/m1-layout-exact-decision-candidate.json"),
    )
    plan.add_argument(
        "--real-market-evidence",
        type=Path,
        default=Path("benchmarks/results/m1-real-market-layout-skew.json"),
    )
    status = commands.add_parser("status")
    status.add_argument("--plan", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    try:
        if args.command_name == "plan":
            payload = publish_campaign_plan(
                campaign_root=args.campaign_root,
                reference_host_path=args.reference_host_evidence,
                decision_path=args.decision_evidence,
                real_market_path=args.real_market_evidence,
            )
            result = {
                "artifact": str((Path(payload["campaign_root"]) / PLAN_NAME).resolve()),
                "status": payload["status"],
                "step_count": len(payload["steps"]),
            }
            exit_code = 0
        else:
            result = campaign_status(args.plan)
            exit_code = 2 if str(result["campaign_status"]).startswith("blocked-") else 0
    except ValueError as error:
        result = {"error": str(error), "status": "blocked-preflight"}
        exit_code = 2
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
