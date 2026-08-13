"""Command line entrypoint for the independently installable grid-data app."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from grid_bybit_public import (
    BybitArchiveIndex,
    BybitHistoricalDataCatalog,
    BybitPublicClient,
    UrllibJsonTransport,
)
from grid_contracts.canonical import sha256_file
from grid_market_store import verify_committed_candle_dataset, verify_compacted_candle_dataset
from grid_market_store.catalog import (
    load_catalog_selection_request,
    preflight_catalog_registration,
    register_catalog_datasets,
    select_catalog_range,
    verify_catalog,
)

from grid_data import __version__
from grid_data.archive_inventory import (
    build_archive_coverage_matrix,
    build_archive_inventory,
    load_verified_public_inventory,
)
from grid_data.dataset_catalog import (
    build_catalog_registration_evidence,
    build_catalog_selection_evidence,
    verify_catalog_registration_evidence,
    verify_catalog_selection_evidence,
)
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from grid_data.history_acquisition import (
    execute_history_job,
    preflight_history_job,
    verify_completed_history_job,
)
from grid_data.history_compaction import (
    build_compaction_evidence,
    preflight_history_compaction,
    publish_preflighted_compaction,
    verify_compaction_evidence,
)
from grid_data.history_coverage_audit import build_completed_history_coverage_audit
from grid_data.history_pilot_evidence import build_history_pilot_evidence
from grid_data.history_publication import (
    preflight_completed_history_publication,
    publish_preflighted_history,
)
from grid_data.history_repair_execution import (
    execute_gap_repair,
    preflight_gap_repair_execution,
    verify_gap_repair_execution,
)
from grid_data.history_repair_plan import build_gap_repair_plan
from grid_data.history_repair_publication import (
    build_gap_replacement_evidence,
    preflight_repaired_history_publication,
    publish_preflighted_repair,
    verify_gap_replacement_evidence,
)
from grid_data.history_request import closed_before_now_ms, resolve_history_request
from grid_data.history_sources import (
    build_history_source_assessment,
    build_one_minute_history_source_assessment,
)
from grid_data.host_probe import probe_host_snapshot
from grid_data.instrument_registry import build_verified_registry_from_inventory
from grid_data.inventory import build_public_inventory
from grid_data.public_sample import build_public_sample
from grid_data.rest_history_boundary import build_rest_history_boundary
from grid_data.rest_throughput import (
    build_rest_throughput_evidence,
    default_profile_text,
    parse_profiles,
)


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

    registry = commands.add_parser(
        "instrument-registry",
        help="publish stable UInt32 identities from a verified linear instrument inventory",
    )
    registry.add_argument("--instrument-inventory", type=Path, required=True)
    registry.add_argument("--output", type=Path, required=True)
    registry.add_argument("--force", action="store_true")
    registry.set_defaults(handler=_instrument_registry)

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

    rest_history = commands.add_parser(
        "rest-history-boundary",
        help="probe bounded earliest 1m/funding availability without retaining market values",
    )
    rest_history.add_argument("--instrument-inventory", type=Path, required=True)
    rest_history.add_argument("--sample-size", type=int, default=8)
    rest_history.add_argument("--workers", type=int, default=8)
    rest_history.add_argument("--max-requests", type=int, default=1000)
    rest_history.add_argument("--base-url", default="https://api.bybit.com")
    rest_history.add_argument("--output", type=Path, required=True)
    rest_history.add_argument("--force", action="store_true")
    rest_history.set_defaults(handler=_rest_history_boundary)

    rest_throughput = commands.add_parser(
        "rest-throughput",
        help="measure paced 1m REST page throughput without retaining market values",
    )
    rest_throughput.add_argument("--instrument-inventory", type=Path, required=True)
    rest_throughput.add_argument("--source-assessment", type=Path, required=True)
    rest_throughput.add_argument("--workstation-snapshot", type=Path, required=True)
    rest_throughput.add_argument(
        "--profiles",
        type=parse_profiles,
        default=parse_profiles(default_profile_text()),
    )
    rest_throughput.add_argument("--stage-seconds", type=Decimal, default=Decimal("4"))
    rest_throughput.add_argument("--cooldown-seconds", type=Decimal, default=Decimal("5.25"))
    rest_throughput.add_argument("--sample-size", type=int, default=8)
    rest_throughput.add_argument("--max-requests", type=int, default=1000)
    rest_throughput.add_argument("--base-url", default="https://api.bybit.com")
    rest_throughput.add_argument("--output", type=Path, required=True)
    rest_throughput.add_argument("--force", action="store_true")
    rest_throughput.set_defaults(handler=_rest_throughput)

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

    history = commands.add_parser(
        "history-1m",
        help="preflight or execute one bounded receipt-resumable public Bybit 1m job",
    )
    history.add_argument("--request", type=Path, required=True)
    history.add_argument("--instrument-registry", type=Path, required=True)
    history.add_argument("--capacity-evidence", type=Path, required=True)
    history.add_argument("--staging-root", type=Path, required=True)
    history.add_argument(
        "--execute",
        action="store_true",
        help="mutate Landing and make public requests; omitted means no-mutation preflight",
    )
    history.set_defaults(handler=_history_1m)

    history_verify = commands.add_parser(
        "verify-history-1m",
        help="verify one completed history job, all page receipts, and its exact file allowlist",
    )
    history_verify.add_argument("job_root", type=Path)
    history_verify.set_defaults(handler=_verify_history_1m)

    history_publish = commands.add_parser(
        "publish-history-1m",
        help="preflight or receipt-last publish one verified Landing job as canonical Parquet",
    )
    history_publish.add_argument("--job-root", type=Path, required=True)
    history_publish.add_argument("--instrument-registry", type=Path, required=True)
    history_publish.add_argument("--capacity-evidence", type=Path, required=True)
    history_publish.add_argument("--store-root", type=Path, required=True)
    history_publish.add_argument("--software-identity", required=True)
    history_publish.add_argument(
        "--execute",
        action="store_true",
        help="write canonical Parquet and receipt; omitted means no-mutation preflight",
    )
    history_publish.set_defaults(handler=_publish_history_1m)

    canonical_verify = commands.add_parser(
        "verify-canonical-candle",
        help="verify one receipt-committed canonical candle dataset and exact file allowlist",
    )
    canonical_verify.add_argument("dataset_root", type=Path)
    canonical_verify.set_defaults(handler=_verify_canonical_candle)

    pilot_evidence = commands.add_parser(
        "history-pilot-evidence",
        help="publish GitHub-safe hashes/counts for one verified canonical public 1m pilot",
    )
    pilot_evidence.add_argument("--job-root", type=Path, required=True)
    pilot_evidence.add_argument("--instrument-registry", type=Path, required=True)
    pilot_evidence.add_argument("--capacity-evidence", type=Path, required=True)
    pilot_evidence.add_argument("--store-root", type=Path, required=True)
    pilot_evidence.add_argument("--software-identity", required=True)
    pilot_evidence.add_argument("--output", type=Path, required=True)
    pilot_evidence.set_defaults(handler=_history_pilot_evidence)

    coverage_audit = commands.add_parser(
        "audit-history-1m",
        help="audit source parity, exact requested coverage, gaps, duplicates, and lifecycle",
    )
    coverage_audit.add_argument("--job-root", type=Path, required=True)
    coverage_audit.add_argument("--instrument-registry", type=Path, required=True)
    coverage_audit.add_argument("--capacity-evidence", type=Path, required=True)
    coverage_audit.add_argument("--store-root", type=Path, required=True)
    coverage_audit.add_argument("--publisher-software-identity", required=True)
    coverage_audit.add_argument("--audit-software-identity", required=True)
    coverage_audit.add_argument("--output", type=Path, required=True)
    coverage_audit.set_defaults(handler=_audit_history_1m)

    repair_plan = commands.add_parser(
        "plan-history-repair",
        help="build bounded standard 1m requests from a verified blocked coverage audit",
    )
    repair_plan.add_argument("--coverage-audit", type=Path, required=True)
    repair_plan.add_argument("--job-root", type=Path, required=True)
    repair_plan.add_argument("--instrument-registry", type=Path, required=True)
    repair_plan.add_argument("--capacity-evidence", type=Path, required=True)
    repair_plan.add_argument("--store-root", type=Path, required=True)
    repair_plan.add_argument("--planner-software-identity", required=True)
    repair_plan.add_argument("--output", type=Path, required=True)
    repair_plan.set_defaults(handler=_plan_history_repair)

    repair_execute = commands.add_parser(
        "execute-history-repair",
        help="preflight or execute every standard request in a verified 1m gap repair plan",
    )
    repair_execute.add_argument("--repair-plan", type=Path, required=True)
    repair_execute.add_argument("--coverage-audit", type=Path, required=True)
    repair_execute.add_argument("--job-root", type=Path, required=True)
    repair_execute.add_argument("--instrument-registry", type=Path, required=True)
    repair_execute.add_argument("--capacity-evidence", type=Path, required=True)
    repair_execute.add_argument("--store-root", type=Path, required=True)
    repair_execute.add_argument("--repair-staging-root", type=Path, required=True)
    repair_execute.add_argument("--executor-software-identity", required=True)
    repair_execute.add_argument("--output", type=Path, required=True)
    repair_execute.add_argument(
        "--execute",
        action="store_true",
        help="make bounded public requests and write Landing/evidence; omitted is preflight",
    )
    repair_execute.set_defaults(handler=_execute_history_repair)

    repair_publish = commands.add_parser(
        "publish-history-repair",
        help="preflight or publish a passed repair as a new immutable child dataset",
    )
    repair_publish.add_argument("--repair-execution", type=Path, required=True)
    repair_publish.add_argument("--repair-plan", type=Path, required=True)
    repair_publish.add_argument("--coverage-audit", type=Path, required=True)
    repair_publish.add_argument("--job-root", type=Path, required=True)
    repair_publish.add_argument("--instrument-registry", type=Path, required=True)
    repair_publish.add_argument("--capacity-evidence", type=Path, required=True)
    repair_publish.add_argument("--store-root", type=Path, required=True)
    repair_publish.add_argument("--repair-staging-root", type=Path, required=True)
    repair_publish.add_argument("--software-identity", required=True)
    repair_publish.add_argument("--output", type=Path, required=True)
    repair_publish.add_argument(
        "--execute",
        action="store_true",
        help="publish replacement Parquet and lineage evidence; omitted is preflight",
    )
    repair_publish.set_defaults(handler=_publish_history_repair)

    compact = commands.add_parser(
        "compact",
        help="preflight or compact immutable canonical fragments into a new child dataset",
    )
    compact.add_argument(
        "--dataset",
        action="append",
        required=True,
        help="parent dataset ID; repeat for each immutable fragment",
    )
    compact.add_argument("--capacity-evidence", type=Path, required=True)
    compact.add_argument("--store-root", type=Path, required=True)
    compact.add_argument("--software-identity", required=True)
    compact.add_argument("--output", type=Path, required=True)
    compact.add_argument(
        "--execute",
        action="store_true",
        help="publish compacted Parquet and evidence; omitted is no-mutation preflight",
    )
    compact.set_defaults(handler=_compact_history)

    catalog_register = commands.add_parser(
        "catalog-register",
        help="preflight or atomically register receipt-verified canonical datasets",
    )
    catalog_register.add_argument(
        "--dataset",
        action="append",
        required=True,
        help="dataset ID; repeat and include any unregistered lineage parents",
    )
    catalog_register.add_argument("--store-root", type=Path, required=True)
    catalog_register.add_argument("--catalog", type=Path, required=True)
    catalog_register.add_argument("--software-identity", required=True)
    catalog_register.add_argument("--output", type=Path, required=True)
    catalog_register.add_argument(
        "--execute",
        action="store_true",
        help="atomically update catalog and publish evidence; omitted is no-mutation preflight",
    )
    catalog_register.set_defaults(handler=_catalog_register)

    catalog_select = commands.add_parser(
        "catalog-select",
        help="select hash-bound canonical objects from one explicitly bound catalog snapshot",
    )
    catalog_select.add_argument("--request", type=Path, required=True)
    catalog_select.add_argument("--store-root", type=Path, required=True)
    catalog_select.add_argument("--catalog", type=Path, required=True)
    catalog_select.add_argument("--output", type=Path, required=True)
    catalog_select.set_defaults(handler=_catalog_select)

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


def _instrument_registry(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    payload = build_verified_registry_from_inventory(args.instrument_inventory)
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "identity_policy": payload["identity_policy"],
                "receipt": str(receipt),
                "summary": payload["summary"],
            }
        )
    )
    return 0


def _history_1m(args: argparse.Namespace) -> int:
    resolved = resolve_history_request(
        args.request,
        instrument_registry_path=args.instrument_registry,
        capacity_evidence_path=args.capacity_evidence,
    )
    snapshot = probe_host_snapshot(args.staging_root)
    now_ms = time.time_ns() // 1_000_000
    plan = preflight_history_job(
        args.staging_root,
        resolved.spec,
        resolved.budget,
        snapshot,
        now_ms=now_ms,
        closed_before_ms=closed_before_now_ms(now_ms),
    )
    summary = {
        "capacity_evidence_sha256": resolved.capacity_artifact_sha256,
        "execute": bool(args.execute),
        "existing_complete": plan.existing_complete,
        "host_preflight": {
            "device_identity_sha256": snapshot.device_identity_sha256,
            "memory_available_bytes": snapshot.memory_available_bytes,
            "memory_total_bytes": snapshot.memory_total_bytes,
            "observed_at_ms": snapshot.observed_at_ms,
            "storage_kind": snapshot.storage_kind,
            "volume_free_bytes": snapshot.volume_free_bytes,
        },
        "instrument_registry_sha256": resolved.registry.artifact_sha256,
        "job_root": str(plan.paths.job_root),
        "pending_page_count": len(plan.pending_tasks),
        "plan_sha256": plan.plan_sha256,
        "planned_page_count": len(plan.tasks),
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "request_sha256": resolved.request_sha256,
        "required_free_bytes": plan.required_free_bytes,
        "status": "preflight-passed",
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    completed = execute_history_job(
        plan,
        lambda: BybitPublicClient(
            UrllibJsonTransport(base_url="https://api.bybit.com", max_attempts=1)
        ),
        lambda: probe_host_snapshot(args.staging_root),
    )
    summary.update(
        {
            "manifest": str(completed.manifest_path),
            "manifest_sha256": completed.manifest_sha256,
            "page_count": completed.page_count,
            "row_count": completed.row_count,
            "status": "complete",
        }
    )
    print(json.dumps(summary))
    return 0


def _verify_history_1m(args: argparse.Namespace) -> int:
    completed = verify_completed_history_job(args.job_root)
    print(
        json.dumps(
            {
                "job_root": str(completed.job_root),
                "manifest_sha256": completed.manifest_sha256,
                "page_count": completed.page_count,
                "row_count": completed.row_count,
                "valid": True,
            }
        )
    )
    return 0


def _publish_history_1m(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    resolved = preflight_completed_history_publication(
        args.store_root,
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        snapshot,
        now_ms=observed_at_ms,
        software_identity=args.software_identity,
    )
    plan = resolved.plan
    summary = {
        "dataset_id": plan.spec.dataset_id,
        "dataset_root": str(plan.paths.dataset_root),
        "execute": bool(args.execute),
        "existing_commit": plan.existing_commit,
        "history_manifest_sha256": resolved.completed_history.manifest_sha256,
        "input_table_sha256": plan.input_table_sha256,
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "request_sha256": plan.request_sha256,
        "required_free_bytes": plan.required_free_bytes,
        "row_count": plan.batch.table.num_rows,
        "status": "preflight-passed",
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    published = publish_preflighted_history(
        resolved,
        lambda: probe_host_snapshot(args.store_root),
        lambda: time.time_ns() // 1_000_000,
    )
    summary.update(
        {
            "manifest": str(published.manifest_path),
            "manifest_sha256": published.receipt.manifest_sha256,
            "receipt": str(published.receipt_path),
            "status": "complete",
        }
    )
    print(json.dumps(summary))
    return 0


def _verify_canonical_candle(args: argparse.Namespace) -> int:
    published = verify_committed_candle_dataset(args.dataset_root)
    print(
        json.dumps(
            {
                "dataset_id": published.manifest.dataset_id,
                "dataset_root": str(published.dataset_root),
                "file_count": len(published.manifest.files),
                "instrument_count": published.manifest.instrument_count,
                "manifest_sha256": published.receipt.manifest_sha256,
                "row_count": published.manifest.row_count,
                "valid": True,
            }
        )
    )
    return 0


def _history_pilot_evidence(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    resolved = preflight_completed_history_publication(
        args.store_root,
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        snapshot,
        now_ms=observed_at_ms,
        software_identity=args.software_identity,
    )
    if not resolved.plan.existing_commit:
        raise ValueError("pilot evidence requires the exact canonical publication to exist")
    published = verify_committed_candle_dataset(resolved.plan.paths.dataset_root)
    payload = build_history_pilot_evidence(
        resolved,
        published,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "canonical": payload["canonical"],
                "receipt": str(receipt),
                "scope": payload["scope"],
                "status": payload["status"],
            }
        )
    )
    return 0


def _audit_history_1m(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    audit = build_completed_history_coverage_audit(
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        args.store_root,
        publisher_software_identity=args.publisher_software_identity,
        audit_software_identity=args.audit_software_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    artifact, receipt = publish_evidence(output, audit.payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "dataset_id": audit.payload["dataset_id"],
                "quality": audit.payload["quality"],
                "receipt": str(receipt),
                "status": audit.payload["status"],
            }
        )
    )
    return 0 if audit.passed else 2


def _plan_history_repair(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    plan = build_gap_repair_plan(
        args.coverage_audit,
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        args.store_root,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        planner_software_identity=args.planner_software_identity,
    )
    artifact, receipt = publish_evidence(output, plan.payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "dataset_id": plan.payload["dataset_id"],
                "planned_max_http_requests": plan.planned_max_http_requests,
                "receipt": str(receipt),
                "status": plan.payload["status"],
                "task_count": plan.task_count,
            }
        )
    )
    return 0


def _execute_history_repair(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.repair_staging_root)
    observed_at_ms = time.time_ns() // 1_000_000
    preflight = preflight_gap_repair_execution(
        args.repair_plan,
        args.coverage_audit,
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        args.store_root,
        args.repair_staging_root,
        snapshot,
        now_ms=observed_at_ms,
        closed_before_ms=closed_before_now_ms(observed_at_ms),
        executor_software_identity=args.executor_software_identity,
    )
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    verified_execution = None
    if output.exists() or receipt.exists():
        verified_execution = verify_gap_repair_execution(
            output,
            args.repair_plan,
            args.coverage_audit,
            args.job_root,
            args.instrument_registry,
            args.capacity_evidence,
            args.store_root,
            args.repair_staging_root,
        )
        if (
            verified_execution.payload.get("executor_software_identity")
            != args.executor_software_identity
        ):
            raise ValueError("existing repair execution uses a different software identity")
    else:
        preflight_evidence(output)
    summary = {
        "execute": bool(args.execute),
        "existing_execution": verified_execution is not None,
        "existing_complete_task_count": preflight.existing_complete_count,
        "planned_max_http_requests": preflight.verified_plan.planned_max_http_requests,
        "planned_peak_memory_bytes": preflight.planned_peak_memory_bytes,
        "repair_plan_sha256": preflight.verified_plan.artifact_sha256,
        "required_free_bytes": preflight.required_free_bytes,
        "status": "preflight-passed",
        "task_count": len(preflight.task_plans),
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    if verified_execution is not None:
        payload = verified_execution.payload
        artifact = verified_execution.path
    else:
        preflight_evidence(output)
        result = execute_gap_repair(
            preflight,
            lambda: BybitPublicClient(
                UrllibJsonTransport(base_url="https://api.bybit.com", max_attempts=1)
            ),
            lambda: probe_host_snapshot(args.repair_staging_root),
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            executor_software_identity=args.executor_software_identity,
            now_ms=lambda: time.time_ns() // 1_000_000,
        )
        artifact, receipt = publish_evidence(output, result.payload)
        payload = result.payload
    limits = payload["limits"]
    summary.update(
        {
            "artifact": str(artifact),
            "limits": limits,
            "receipt": str(output.with_suffix(output.suffix + ".receipt.json")),
            "status": payload["status"],
        }
    )
    print(json.dumps(summary))
    return 0 if payload["status"] == "passed" else 2


def _publish_history_repair(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    resolved = preflight_repaired_history_publication(
        args.repair_execution,
        args.repair_plan,
        args.coverage_audit,
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        args.store_root,
        args.repair_staging_root,
        snapshot,
        now_ms=observed_at_ms,
        software_identity=args.software_identity,
    )
    plan = resolved.plan
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing_evidence = output.exists() or receipt.exists()
    published = None
    evidence = None
    if existing_evidence:
        if not plan.existing_commit or not verify_evidence(output):
            raise ValueError("replacement evidence conflicts with an uncommitted publication")
        published = verify_committed_candle_dataset(plan.paths.dataset_root)
        evidence = verify_gap_replacement_evidence(output, resolved, published)
    else:
        preflight_evidence(output)
    summary = {
        "dataset_id": plan.spec.dataset_id,
        "dataset_root": str(plan.paths.dataset_root),
        "execute": bool(args.execute),
        "existing_commit": plan.existing_commit,
        "existing_evidence": existing_evidence,
        "expected_minute_count": resolved.expected_minute_count,
        "parent_dataset_id": resolved.parent.manifest.dataset_id,
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "repaired_row_count": resolved.repaired_row_count,
        "required_free_bytes": plan.required_free_bytes,
        "status": "preflight-passed",
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    if published is not None and evidence is not None:
        artifact = output
    else:
        published = publish_preflighted_repair(
            resolved,
            lambda: probe_host_snapshot(args.store_root),
            lambda: time.time_ns() // 1_000_000,
        )
        evidence = build_gap_replacement_evidence(
            resolved,
            published,
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        artifact, receipt = publish_evidence(output, evidence)
    summary.update(
        {
            "artifact": str(artifact),
            "manifest_sha256": published.receipt.manifest_sha256,
            "receipt": str(output.with_suffix(output.suffix + ".receipt.json")),
            "replacement_row_count": published.manifest.row_count,
            "status": evidence["status"],
        }
    )
    print(json.dumps(summary))
    return 0


def _compact_history(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    resolved = preflight_history_compaction(
        tuple(args.dataset),
        args.capacity_evidence,
        args.store_root,
        snapshot,
        now_ms=observed_at_ms,
        software_identity=args.software_identity,
    )
    plan = resolved.plan
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing_evidence = output.exists() or receipt.exists()
    published = None
    evidence = None
    if existing_evidence:
        if not plan.existing_commit or not verify_evidence(output):
            raise ValueError("compaction evidence conflicts with an uncommitted publication")
        published = verify_compacted_candle_dataset(plan.paths.dataset_root)
        evidence = verify_compaction_evidence(output, resolved, published)
    else:
        preflight_evidence(output)
    summary = {
        "dataset_id": plan.spec.dataset_id,
        "dataset_root": str(plan.paths.dataset_root),
        "execute": bool(args.execute),
        "existing_commit": plan.existing_commit,
        "existing_evidence": existing_evidence,
        "expected_output_file_count": plan.expected_output_file_count,
        "input_file_count": plan.input_file_count,
        "parent_dataset_ids": list(plan.spec.parent_dataset_ids),
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "required_free_bytes": plan.required_free_bytes,
        "rows_per_file_target": plan.rows_per_file_target,
        "status": "preflight-passed",
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    if published is not None and evidence is not None:
        artifact = output
    else:
        published = publish_preflighted_compaction(
            resolved,
            lambda: probe_host_snapshot(args.store_root),
            lambda: time.time_ns() // 1_000_000,
        )
        evidence = build_compaction_evidence(
            resolved,
            published,
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        artifact, receipt = publish_evidence(output, evidence)
    summary.update(
        {
            "artifact": str(artifact),
            "manifest_sha256": published.receipt.manifest_sha256,
            "output_file_count": len(published.manifest.files),
            "receipt": str(output.with_suffix(output.suffix + ".receipt.json")),
            "status": evidence["status"],
        }
    )
    print(json.dumps(summary))
    return 0


def _catalog_register(args: argparse.Namespace) -> int:
    plan = preflight_catalog_registration(
        tuple(args.dataset),
        args.store_root,
        args.catalog,
        software_identity=args.software_identity,
    )
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing_evidence = output.exists() or receipt.exists()
    if existing_evidence:
        if not plan.existing_registration or not verify_evidence(output):
            raise ValueError("catalog evidence conflicts with an incomplete registration")
    else:
        preflight_evidence(output)
    summary = {
        "catalog": str(plan.catalog_path),
        "catalog_content_sha256_before": plan.before.content_sha256,
        "catalog_revision_before": plan.before.revision,
        "execute": bool(args.execute),
        "existing_evidence": existing_evidence,
        "existing_registration": plan.existing_registration,
        "new_dataset_ids": list(plan.new_dataset_ids),
        "requested_dataset_ids": list(plan.requested_dataset_ids),
        "status": "preflight-passed",
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    snapshot = register_catalog_datasets(
        plan,
        registered_at_ms=time.time_ns() // 1_000_000,
    )
    if existing_evidence:
        evidence = verify_catalog_registration_evidence(output, plan, snapshot)
        artifact = output
    else:
        evidence = build_catalog_registration_evidence(
            plan,
            snapshot,
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        artifact, receipt = publish_evidence(output, evidence)
    summary.update(
        {
            "artifact": str(artifact),
            "catalog_content_sha256": snapshot.content_sha256,
            "catalog_dataset_count": snapshot.dataset_count,
            "catalog_file_count": snapshot.file_count,
            "catalog_revision": snapshot.revision,
            "receipt": str(output.with_suffix(output.suffix + ".receipt.json")),
            "status": evidence["status"],
        }
    )
    print(json.dumps(summary))
    return 0


def _catalog_select(args: argparse.Namespace) -> int:
    request = load_catalog_selection_request(args.request)
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing_evidence = output.exists() or receipt.exists()
    if existing_evidence:
        if not verify_evidence(output):
            raise ValueError("catalog selection evidence receipt does not verify")
    else:
        preflight_evidence(output)
    selection = select_catalog_range(request, args.store_root, args.catalog)
    if existing_evidence:
        evidence = verify_catalog_selection_evidence(output, selection)
        artifact = output
    else:
        evidence = build_catalog_selection_evidence(
            selection,
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        artifact, receipt = publish_evidence(output, evidence)
    snapshot = verify_catalog(args.store_root, args.catalog)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "catalog_content_sha256": snapshot.content_sha256,
                "catalog_revision": snapshot.revision,
                "object_count": len(selection.objects),
                "receipt": str(output.with_suffix(output.suffix + ".receipt.json")),
                "request_sha256": request.request_sha256,
                "status": evidence["status"],
            }
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


def _rest_history_boundary(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    inventory_path = args.instrument_inventory.resolve()
    inventory = load_verified_public_inventory(inventory_path)
    payload = build_rest_history_boundary(
        lambda: BybitPublicClient(UrllibJsonTransport(base_url=args.base_url, max_attempts=1)),
        inventory,
        command=shlex.join(sys.argv),
        inventory_artifact=inventory_path.name,
        inventory_artifact_sha256=sha256_file(inventory_path),
        sample_size=args.sample_size,
        workers=args.workers,
        max_requests=args.max_requests,
    )
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "receipt": str(receipt),
                "request_audit": payload["request_audit"],
                "status": payload["status"],
                "summary": payload["summary"],
            }
        )
    )
    return 0


def _load_verified_json(path: Path, *, name: str) -> tuple[Path, dict[str, object]]:
    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise ValueError(f"{name} receipt verification failed: {resolved}")
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return resolved, raw


def _rest_throughput(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output, force=args.force)
    inventory_path, inventory = _load_verified_json(
        args.instrument_inventory, name="instrument inventory"
    )
    source_path, source_assessment = _load_verified_json(
        args.source_assessment, name="source assessment"
    )
    workstation_path, workstation = _load_verified_json(
        args.workstation_snapshot, name="workstation snapshot"
    )
    captured_at = workstation.get("observed_at_utc")
    if workstation.get("evidence_schema") != "grid.workstation-snapshot/v1" or not isinstance(
        captured_at, str
    ):
        raise ValueError("unsupported workstation snapshot evidence")
    payload = build_rest_throughput_evidence(
        lambda: BybitPublicClient(UrllibJsonTransport(base_url=args.base_url, max_attempts=1)),
        inventory,
        source_assessment,
        command=shlex.join(sys.argv),
        base_url=args.base_url,
        inventory_artifact=inventory_path.name,
        inventory_artifact_sha256=sha256_file(inventory_path),
        source_assessment_artifact=source_path.name,
        source_assessment_artifact_sha256=sha256_file(source_path),
        workstation_artifact=workstation_path.name,
        workstation_artifact_sha256=sha256_file(workstation_path),
        workstation_captured_at_utc=captured_at,
        profiles=args.profiles,
        stage_seconds=args.stage_seconds,
        cooldown_seconds=args.cooldown_seconds,
        sample_size=args.sample_size,
        max_requests=args.max_requests,
    )
    artifact, receipt = publish_evidence(output, payload, force=args.force)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "bootstrap_request_only_projection": payload["bootstrap_request_only_projection"],
                "receipt": str(receipt),
                "recommendation": payload["recommendation"],
                "request_audit": payload["request_audit"],
                "status": payload["status"],
            }
        )
    )
    return 0 if payload["status"] == "bounded-benchmark-complete" else 2


def _verify(args: argparse.Namespace) -> int:
    valid = verify_evidence(args.artifact)
    print(json.dumps({"artifact": str(args.artifact.resolve()), "valid": valid}))
    return 0 if valid else 2


def main() -> int:
    args = parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
