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
from grid_market_store import (
    verify_committed_candle_dataset,
    verify_committed_funding_dataset,
    verify_compacted_candle_dataset,
)
from grid_market_store.catalog import (
    CatalogRegistrationRequest,
    catalog_registration_request_payload,
    load_catalog_registration_request,
    load_catalog_selection_request,
    preflight_catalog_registration,
    register_catalog_datasets,
    select_catalog_range,
    verify_catalog,
)

from grid_data import __version__
from grid_data.announcement_archive_depth import (
    build_announcement_archive_depth_evidence,
)
from grid_data.archive_inventory import (
    build_archive_coverage_matrix,
    build_archive_inventory,
    load_verified_public_inventory,
)
from grid_data.dataset_catalog import (
    build_catalog_registration_evidence,
    build_catalog_selection_evidence,
    build_full_history_catalog_evidence,
    verify_catalog_registration_evidence,
    verify_catalog_selection_evidence,
)
from grid_data.evidence import preflight_evidence, publish_evidence, verify_evidence
from grid_data.funding_acquisition import (
    execute_funding_job,
    preflight_funding_job,
    verify_completed_funding_job,
)
from grid_data.funding_compaction import (
    build_funding_compaction_evidence,
    preflight_funding_compaction,
    publish_preflighted_funding_compaction,
    verify_funding_compaction_evidence,
)
from grid_data.funding_compaction_candidate_audit import (
    build_funding_compaction_candidate_audit,
    build_funding_compaction_candidate_evidence,
    verify_funding_compaction_candidate_audit,
    verify_funding_compaction_candidate_evidence,
)
from grid_data.funding_coverage_audit import build_completed_funding_coverage_audit
from grid_data.funding_pilot_evidence import build_funding_pilot_evidence
from grid_data.funding_publication import (
    preflight_completed_funding_publication,
    publish_preflighted_funding,
)
from grid_data.funding_repair_candidate_audit import (
    FundingRepairCandidateInput,
    build_funding_repair_candidate_audit,
    build_funding_repair_candidate_evidence,
    verify_funding_repair_candidate_audit,
    verify_funding_repair_candidate_evidence,
)
from grid_data.funding_repair_coverage_audit import (
    build_funding_repair_coverage_audit,
    verify_funding_repair_coverage_audit,
)
from grid_data.funding_repair_execution import (
    execute_funding_repair,
    preflight_funding_repair_execution,
    verify_funding_repair_execution,
)
from grid_data.funding_repair_plan import build_funding_repair_plan
from grid_data.funding_repair_publication import (
    build_funding_repair_execution_public_evidence,
    build_funding_repair_replacement_evidence,
    preflight_repaired_funding_publication,
    publish_preflighted_funding_repair,
    verify_funding_repair_execution_public_evidence,
    verify_funding_repair_replacement_evidence,
)
from grid_data.funding_request import resolve_funding_request
from grid_data.funding_source_boundary import (
    execute_funding_source_boundary,
    preflight_funding_source_boundary,
    verify_completed_funding_source_boundary,
)
from grid_data.funding_source_boundary_evidence import (
    build_funding_source_boundary_evidence,
)
from grid_data.history_acquisition import (
    execute_history_job,
    preflight_history_job,
    verify_completed_history_job,
)
from grid_data.history_campaign import (
    execute_history_campaign,
    preflight_history_campaign,
    verify_completed_history_campaign,
)
from grid_data.history_campaign_boundary_diagnostic import (
    build_history_campaign_boundary_diagnostic,
)
from grid_data.history_campaign_coverage_audit import build_history_campaign_coverage_audit
from grid_data.history_campaign_evidence import build_history_campaign_evidence
from grid_data.history_campaign_publication import (
    execute_history_campaign_publication,
    load_prepared_history_campaign_publication,
    preflight_history_campaign_publication,
    prepare_history_campaign_publication_plan,
    verify_completed_history_campaign_publication,
)
from grid_data.history_campaign_publication_evidence import (
    build_history_campaign_publication_evidence,
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
from grid_data.history_repair_public_evidence import (
    build_candle_repair_execution_public_evidence,
    verify_candle_repair_execution_public_evidence,
)
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
from grid_data.instrument_timeline import (
    build_instrument_timeline,
    build_instrument_timeline_summary,
    load_verified_instrument_timeline,
)
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

    timeline = commands.add_parser(
        "instrument-timeline",
        help="publish an immutable point-in-time timeline from verified instrument registries",
    )
    timeline.add_argument(
        "--instrument-registry",
        action="append",
        type=Path,
        required=True,
        help="verified registry snapshot; repeat in any order",
    )
    timeline.add_argument("--output", type=Path, required=True)
    timeline.set_defaults(handler=_instrument_timeline)

    timeline_verify = commands.add_parser(
        "verify-instrument-timeline",
        help="verify a receipt-committed instrument timeline and temporal semantics",
    )
    timeline_verify.add_argument("timeline", type=Path)
    timeline_verify.set_defaults(handler=_verify_instrument_timeline)

    timeline_summary = commands.add_parser(
        "instrument-timeline-summary",
        help="publish bounded GitHub-safe instrument timeline evidence",
    )
    timeline_summary.add_argument("--timeline", type=Path, required=True)
    timeline_summary.add_argument("--software-identity", required=True)
    timeline_summary.add_argument("--output", type=Path, required=True)
    timeline_summary.set_defaults(handler=_instrument_timeline_summary)

    announcement_depth = commands.add_parser(
        "announcement-archive-depth",
        help="probe only official announcement first/last pages for lifecycle source depth",
    )
    announcement_depth.add_argument("--instrument-registry", type=Path, required=True)
    announcement_depth.add_argument(
        "--instrument-id",
        action="append",
        type=int,
        required=True,
        help="selected public registry identity; repeat without publishing identities",
    )
    announcement_depth.add_argument("--software-identity", required=True)
    announcement_depth.add_argument("--output", type=Path, required=True)
    announcement_depth.set_defaults(handler=_announcement_archive_depth)

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

    history_campaign = commands.add_parser(
        "history-campaign",
        help="preflight or execute a resumable multi-month public trade/mark/funding campaign",
    )
    history_campaign.add_argument("--request", type=Path, required=True)
    history_campaign.add_argument("--instrument-registry", type=Path, required=True)
    history_campaign.add_argument("--capacity-evidence", type=Path, required=True)
    history_campaign.add_argument("--staging-root", type=Path, required=True)
    history_campaign.add_argument(
        "--funding-source-boundary-root",
        type=Path,
        help=(
            "optional completed receipt-verified source-boundary root used to clip and bind "
            "funding starts"
        ),
    )
    history_campaign.add_argument(
        "--execute",
        action="store_true",
        help="write campaign/child receipts and call public endpoints; omitted means preflight",
    )
    history_campaign.set_defaults(handler=_history_campaign)

    campaign_verify = commands.add_parser(
        "verify-history-campaign",
        help="verify a completed campaign and every receipt-committed child job",
    )
    campaign_verify.add_argument("campaign_root", type=Path)
    campaign_verify.set_defaults(handler=_verify_history_campaign)

    campaign_evidence = commands.add_parser(
        "history-campaign-evidence",
        help="publish a receipt-verified GitHub-safe summary of one completed campaign",
    )
    campaign_evidence.add_argument("--campaign-root", type=Path, required=True)
    campaign_evidence.add_argument("--software-identity", required=True)
    campaign_evidence.add_argument("--output", type=Path, required=True)
    campaign_evidence.add_argument(
        "--require-complete-throttling-evidence",
        action="store_true",
        help=(
            "fail unless every child has execution timing and every completed page response "
            "has a sanitized adaptive observation"
        ),
    )
    campaign_evidence.set_defaults(handler=_history_campaign_evidence)

    campaign_publish = commands.add_parser(
        "publish-history-campaign",
        help="preflight or sequentially publish every completed campaign child as canonical",
    )
    campaign_publish.add_argument("--campaign-root", type=Path, required=True)
    campaign_publish.add_argument("--instrument-registry", type=Path, required=True)
    campaign_publish.add_argument("--capacity-evidence", type=Path, required=True)
    campaign_publish.add_argument("--store-root", type=Path, required=True)
    campaign_publish.add_argument("--software-identity", required=True)
    campaign_publish_mode = campaign_publish.add_mutually_exclusive_group()
    campaign_publish_mode.add_argument(
        "--prepare-plan",
        action="store_true",
        help=(
            "persist only the receipt-bound aggregate plan after semantic preflight; "
            "write no canonical datasets"
        ),
    )
    campaign_publish_mode.add_argument(
        "--execute",
        action="store_true",
        help=(
            "write canonical datasets and aggregate receipts; with --publication-root, "
            "resume from its receipt-bound prepared plan"
        ),
    )
    campaign_publish.add_argument(
        "--publication-root",
        type=Path,
        help="prepared publication root; valid only together with --execute",
    )
    campaign_publish.set_defaults(handler=_publish_history_campaign)

    campaign_publication_verify = commands.add_parser(
        "verify-history-campaign-publication",
        help="verify aggregate publication, source campaign lineage, and canonical datasets",
    )
    campaign_publication_verify.add_argument("publication_root", type=Path)
    campaign_publication_verify.add_argument("--campaign-root", type=Path, required=True)
    campaign_publication_verify.set_defaults(handler=_verify_history_campaign_publication)

    campaign_publication_evidence = commands.add_parser(
        "history-campaign-publication-evidence",
        help="publish a receipt-verified GitHub-safe canonical campaign summary",
    )
    campaign_publication_evidence.add_argument("--publication-root", type=Path, required=True)
    campaign_publication_evidence.add_argument("--campaign-root", type=Path, required=True)
    campaign_publication_evidence.add_argument("--software-identity", required=True)
    campaign_publication_evidence.add_argument("--output", type=Path, required=True)
    campaign_publication_evidence.set_defaults(handler=_history_campaign_publication_evidence)

    campaign_coverage_audit = commands.add_parser(
        "audit-history-campaign",
        help="audit every canonical campaign child under unchanged candle/funding policy",
    )
    campaign_coverage_audit.add_argument("--publication-root", type=Path, required=True)
    campaign_coverage_audit.add_argument("--campaign-root", type=Path, required=True)
    campaign_coverage_audit.add_argument("--instrument-registry", type=Path, required=True)
    campaign_coverage_audit.add_argument("--capacity-evidence", type=Path, required=True)
    campaign_coverage_audit.add_argument("--store-root", type=Path, required=True)
    campaign_coverage_audit.add_argument("--publisher-software-identity", required=True)
    campaign_coverage_audit.add_argument("--audit-software-identity", required=True)
    campaign_coverage_audit.add_argument("--output", type=Path, required=True)
    campaign_coverage_audit.set_defaults(handler=_audit_history_campaign)

    campaign_boundary_diagnostic = commands.add_parser(
        "diagnose-history-campaign-boundaries",
        help="classify canonical candle gaps without downloading or decoding Landing rows",
    )
    campaign_boundary_diagnostic.add_argument("--publication-root", type=Path, required=True)
    campaign_boundary_diagnostic.add_argument("--campaign-root", type=Path, required=True)
    campaign_boundary_diagnostic.add_argument("--instrument-registry", type=Path, required=True)
    campaign_boundary_diagnostic.add_argument("--coverage-audit", type=Path, required=True)
    campaign_boundary_diagnostic.add_argument("--software-identity", required=True)
    campaign_boundary_diagnostic.add_argument("--output", type=Path, required=True)
    campaign_boundary_diagnostic.set_defaults(handler=_diagnose_history_campaign_boundaries)

    funding_boundary = commands.add_parser(
        "funding-source-boundary",
        help="preflight or discover earliest receipt-verified public funding settlements",
    )
    funding_boundary.add_argument("--request", type=Path, required=True)
    funding_boundary.add_argument("--instrument-registry", type=Path, required=True)
    funding_boundary.add_argument("--output-root", type=Path, required=True)
    funding_boundary.add_argument("--software-identity", required=True)
    funding_boundary.add_argument(
        "--execute",
        action="store_true",
        help="write timestamp-only discovery receipts and call the public endpoint",
    )
    funding_boundary.set_defaults(handler=_funding_source_boundary)

    verify_funding_boundary = commands.add_parser(
        "verify-funding-source-boundary",
        help="verify one completed timestamp-only funding source-boundary discovery",
    )
    verify_funding_boundary.add_argument("job_root", type=Path)
    verify_funding_boundary.set_defaults(handler=_verify_funding_source_boundary)

    funding_boundary_evidence = commands.add_parser(
        "funding-source-boundary-evidence",
        help="publish a receipt-verified GitHub-safe funding boundary summary",
    )
    funding_boundary_evidence.add_argument("--job-root", type=Path, required=True)
    funding_boundary_evidence.add_argument("--software-identity", required=True)
    funding_boundary_evidence.add_argument("--output", type=Path, required=True)
    funding_boundary_evidence.set_defaults(handler=_funding_source_boundary_evidence)

    funding = commands.add_parser(
        "funding-history",
        help="preflight or execute one bounded receipt-resumable public Bybit funding job",
    )
    funding.add_argument("--request", type=Path, required=True)
    funding.add_argument("--instrument-registry", type=Path, required=True)
    funding.add_argument("--capacity-evidence", type=Path, required=True)
    funding.add_argument("--staging-root", type=Path, required=True)
    funding.add_argument(
        "--execute",
        action="store_true",
        help="mutate Funding Landing and make public requests; omitted means preflight",
    )
    funding.set_defaults(handler=_funding_history)

    funding_verify = commands.add_parser(
        "verify-funding-history",
        help="verify a completed funding job, predecessor evidence, receipts, and allowlist",
    )
    funding_verify.add_argument("job_root", type=Path)
    funding_verify.set_defaults(handler=_verify_funding_history)

    funding_publish = commands.add_parser(
        "publish-funding-history",
        help="preflight or receipt-last publish verified funding Landing as canonical Parquet",
    )
    funding_publish.add_argument("--job-root", type=Path, required=True)
    funding_publish.add_argument("--instrument-registry", type=Path, required=True)
    funding_publish.add_argument("--capacity-evidence", type=Path, required=True)
    funding_publish.add_argument("--store-root", type=Path, required=True)
    funding_publish.add_argument("--software-identity", required=True)
    funding_publish.add_argument(
        "--execute",
        action="store_true",
        help="write canonical funding Parquet and receipt; omitted means preflight",
    )
    funding_publish.set_defaults(handler=_publish_funding_history)

    funding_canonical_verify = commands.add_parser(
        "verify-canonical-funding",
        help="verify one receipt-committed canonical funding dataset and exact allowlist",
    )
    funding_canonical_verify.add_argument("dataset_root", type=Path)
    funding_canonical_verify.set_defaults(handler=_verify_canonical_funding)

    funding_pilot_evidence = commands.add_parser(
        "funding-pilot-evidence",
        help="publish GitHub-safe hashes/counts for one verified canonical public funding pilot",
    )
    funding_pilot_evidence.add_argument("--job-root", type=Path, required=True)
    funding_pilot_evidence.add_argument("--instrument-registry", type=Path, required=True)
    funding_pilot_evidence.add_argument("--capacity-evidence", type=Path, required=True)
    funding_pilot_evidence.add_argument("--store-root", type=Path, required=True)
    funding_pilot_evidence.add_argument("--software-identity", required=True)
    funding_pilot_evidence.add_argument("--output", type=Path, required=True)
    funding_pilot_evidence.set_defaults(handler=_funding_pilot_evidence)

    funding_coverage_audit = commands.add_parser(
        "audit-funding-history",
        help="audit exact funding source parity, range enumeration, and stable chronology",
    )
    funding_coverage_audit.add_argument("--job-root", type=Path, required=True)
    funding_coverage_audit.add_argument("--instrument-registry", type=Path, required=True)
    funding_coverage_audit.add_argument("--capacity-evidence", type=Path, required=True)
    funding_coverage_audit.add_argument("--store-root", type=Path, required=True)
    funding_coverage_audit.add_argument("--publisher-software-identity", required=True)
    funding_coverage_audit.add_argument("--audit-software-identity", required=True)
    funding_coverage_audit.add_argument("--output", type=Path, required=True)
    funding_coverage_audit.set_defaults(handler=_audit_funding_history)

    funding_repair_plan = commands.add_parser(
        "plan-funding-repair",
        help=(
            "plan bounded source discovery for isolated funding chronology gaps without "
            "accepting cadence changes"
        ),
    )
    funding_repair_plan.add_argument("--coverage-audit", type=Path, required=True)
    funding_repair_plan.add_argument("--job-root", type=Path, required=True)
    funding_repair_plan.add_argument("--instrument-registry", type=Path, required=True)
    funding_repair_plan.add_argument("--capacity-evidence", type=Path, required=True)
    funding_repair_plan.add_argument("--store-root", type=Path, required=True)
    funding_repair_plan.add_argument("--planner-software-identity", required=True)
    funding_repair_plan.add_argument("--output", type=Path, required=True)
    funding_repair_plan.set_defaults(handler=_plan_funding_repair)

    funding_repair_execute = commands.add_parser(
        "execute-funding-repair",
        help=(
            "preflight or execute every standard public request in a verified funding "
            "repair discovery plan"
        ),
    )
    funding_repair_execute.add_argument("--repair-plan", type=Path, required=True)
    funding_repair_execute.add_argument("--coverage-audit", type=Path, required=True)
    funding_repair_execute.add_argument("--job-root", type=Path, required=True)
    funding_repair_execute.add_argument("--instrument-registry", type=Path, required=True)
    funding_repair_execute.add_argument("--capacity-evidence", type=Path, required=True)
    funding_repair_execute.add_argument("--store-root", type=Path, required=True)
    funding_repair_execute.add_argument("--repair-staging-root", type=Path, required=True)
    funding_repair_execute.add_argument("--executor-software-identity", required=True)
    funding_repair_execute.add_argument("--output", type=Path, required=True)
    funding_repair_execute.add_argument(
        "--execute",
        action="store_true",
        help=(
            "make bounded public requests and write private Landing/evidence; omitted is preflight"
        ),
    )
    funding_repair_execute.set_defaults(handler=_execute_funding_repair)

    funding_repair_public_evidence = commands.add_parser(
        "funding-repair-execution-evidence",
        help="publish identifier- and value-free aggregate evidence for a verified execution",
    )
    funding_repair_public_evidence.add_argument("--repair-execution", type=Path, required=True)
    funding_repair_public_evidence.add_argument("--repair-plan", type=Path, required=True)
    funding_repair_public_evidence.add_argument("--coverage-audit", type=Path, required=True)
    funding_repair_public_evidence.add_argument("--job-root", type=Path, required=True)
    funding_repair_public_evidence.add_argument("--instrument-registry", type=Path, required=True)
    funding_repair_public_evidence.add_argument("--capacity-evidence", type=Path, required=True)
    funding_repair_public_evidence.add_argument("--store-root", type=Path, required=True)
    funding_repair_public_evidence.add_argument("--repair-staging-root", type=Path, required=True)
    funding_repair_public_evidence.add_argument("--output", type=Path, required=True)
    funding_repair_public_evidence.set_defaults(handler=_funding_repair_execution_evidence)

    funding_repair_publish = commands.add_parser(
        "publish-funding-repair",
        help="preflight or publish a passed funding repair as a new immutable child dataset",
    )
    funding_repair_publish.add_argument("--repair-execution", type=Path, required=True)
    funding_repair_publish.add_argument("--repair-plan", type=Path, required=True)
    funding_repair_publish.add_argument("--coverage-audit", type=Path, required=True)
    funding_repair_publish.add_argument("--job-root", type=Path, required=True)
    funding_repair_publish.add_argument("--instrument-registry", type=Path, required=True)
    funding_repair_publish.add_argument("--capacity-evidence", type=Path, required=True)
    funding_repair_publish.add_argument("--store-root", type=Path, required=True)
    funding_repair_publish.add_argument("--repair-staging-root", type=Path, required=True)
    funding_repair_publish.add_argument("--software-identity", required=True)
    funding_repair_publish.add_argument("--output", type=Path, required=True)
    funding_repair_publish.add_argument(
        "--execute",
        action="store_true",
        help="publish repair child and lineage evidence; omitted is no-mutation preflight",
    )
    funding_repair_publish.set_defaults(handler=_publish_funding_repair)

    funding_repair_audit = commands.add_parser(
        "audit-funding-repair",
        help="audit exact source parity and chronology of a committed funding repair child",
    )
    funding_repair_audit.add_argument("--repair-execution", type=Path, required=True)
    funding_repair_audit.add_argument("--repair-plan", type=Path, required=True)
    funding_repair_audit.add_argument("--original-coverage-audit", type=Path, required=True)
    funding_repair_audit.add_argument("--job-root", type=Path, required=True)
    funding_repair_audit.add_argument("--instrument-registry", type=Path, required=True)
    funding_repair_audit.add_argument("--capacity-evidence", type=Path, required=True)
    funding_repair_audit.add_argument("--store-root", type=Path, required=True)
    funding_repair_audit.add_argument("--repair-staging-root", type=Path, required=True)
    funding_repair_audit.add_argument("--replacement-evidence", type=Path, required=True)
    funding_repair_audit.add_argument("--publisher-software-identity", required=True)
    funding_repair_audit.add_argument("--audit-software-identity", required=True)
    funding_repair_audit.add_argument("--output", type=Path, required=True)
    funding_repair_audit.set_defaults(handler=_audit_funding_repair)

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

    repair_public_evidence = commands.add_parser(
        "history-repair-execution-evidence",
        help="publish identifier- and value-free aggregate evidence for a verified 1m repair",
    )
    repair_public_evidence.add_argument("--repair-execution", type=Path, required=True)
    repair_public_evidence.add_argument("--repair-plan", type=Path, required=True)
    repair_public_evidence.add_argument("--coverage-audit", type=Path, required=True)
    repair_public_evidence.add_argument("--job-root", type=Path, required=True)
    repair_public_evidence.add_argument("--instrument-registry", type=Path, required=True)
    repair_public_evidence.add_argument("--capacity-evidence", type=Path, required=True)
    repair_public_evidence.add_argument("--store-root", type=Path, required=True)
    repair_public_evidence.add_argument("--repair-staging-root", type=Path, required=True)
    repair_public_evidence.add_argument("--output", type=Path, required=True)
    repair_public_evidence.set_defaults(handler=_history_repair_execution_evidence)

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

    funding_compact = commands.add_parser(
        "compact-funding",
        help="preflight or compact immutable canonical funding fragments into a new child",
    )
    funding_compact.add_argument(
        "--dataset",
        action="append",
        required=True,
        help="parent funding dataset ID; repeat for each immutable fragment",
    )
    funding_compact.add_argument("--capacity-evidence", type=Path, required=True)
    funding_compact.add_argument("--store-root", type=Path, required=True)
    funding_compact.add_argument("--software-identity", required=True)
    funding_compact.add_argument("--output", type=Path, required=True)
    funding_compact.add_argument(
        "--execute",
        action="store_true",
        help="publish compacted funding Parquet and evidence; omitted is no-mutation preflight",
    )
    funding_compact.set_defaults(handler=_compact_funding)

    funding_compaction_audit = commands.add_parser(
        "audit-funding-compaction-candidates",
        help="classify every receipt-verified same-partition funding parent pair",
    )
    funding_compaction_audit.add_argument("--store-root", type=Path, required=True)
    funding_compaction_audit.add_argument("--software-identity", required=True)
    funding_compaction_audit.add_argument("--output", type=Path, required=True)
    funding_compaction_audit.add_argument(
        "--execute",
        action="store_true",
        help="write the detailed private audit and receipt; omitted is no-mutation preflight",
    )
    funding_compaction_audit.set_defaults(handler=_audit_funding_compaction_candidates)

    funding_compaction_evidence = commands.add_parser(
        "funding-compaction-candidate-evidence",
        help="publish a GitHub-safe aggregate from a verified private candidate audit",
    )
    funding_compaction_evidence.add_argument("--audit", type=Path, required=True)
    funding_compaction_evidence.add_argument("--store-root", type=Path, required=True)
    funding_compaction_evidence.add_argument("--software-identity", required=True)
    funding_compaction_evidence.add_argument("--output", type=Path, required=True)
    funding_compaction_evidence.set_defaults(handler=_funding_compaction_candidate_evidence)

    funding_repair_candidate_audit = commands.add_parser(
        "audit-funding-repair-candidates",
        help="classify receipt-verified blocked funding audits before repair discovery",
    )
    funding_repair_candidate_audit.add_argument(
        "--coverage-audit", type=Path, action="append", required=True
    )
    funding_repair_candidate_audit.add_argument(
        "--job-root", type=Path, action="append", required=True
    )
    funding_repair_candidate_audit.add_argument(
        "--instrument-registry", type=Path, action="append", required=True
    )
    funding_repair_candidate_audit.add_argument("--capacity-evidence", type=Path, required=True)
    funding_repair_candidate_audit.add_argument("--store-root", type=Path, required=True)
    funding_repair_candidate_audit.add_argument("--software-identity", required=True)
    funding_repair_candidate_audit.add_argument("--output", type=Path, required=True)
    funding_repair_candidate_audit.add_argument(
        "--execute",
        action="store_true",
        help="write the detailed private audit and receipt; omitted is no-mutation preflight",
    )
    funding_repair_candidate_audit.set_defaults(handler=_audit_funding_repair_candidates)

    funding_repair_candidate_evidence = commands.add_parser(
        "funding-repair-candidate-evidence",
        help="publish a GitHub-safe aggregate from a verified private repair audit",
    )
    funding_repair_candidate_evidence.add_argument("--audit", type=Path, required=True)
    funding_repair_candidate_evidence.add_argument(
        "--coverage-audit", type=Path, action="append", required=True
    )
    funding_repair_candidate_evidence.add_argument(
        "--job-root", type=Path, action="append", required=True
    )
    funding_repair_candidate_evidence.add_argument(
        "--instrument-registry", type=Path, action="append", required=True
    )
    funding_repair_candidate_evidence.add_argument("--capacity-evidence", type=Path, required=True)
    funding_repair_candidate_evidence.add_argument("--store-root", type=Path, required=True)
    funding_repair_candidate_evidence.add_argument("--software-identity", required=True)
    funding_repair_candidate_evidence.add_argument("--output", type=Path, required=True)
    funding_repair_candidate_evidence.set_defaults(handler=_funding_repair_candidate_evidence)

    catalog_registration_request = commands.add_parser(
        "catalog-registration-request",
        help="build a receipt-bound registration request from one verified campaign publication",
    )
    catalog_registration_request.add_argument("--publication-root", type=Path, required=True)
    catalog_registration_request.add_argument("--campaign-root", type=Path, required=True)
    catalog_registration_request.add_argument("--software-identity", required=True)
    catalog_registration_request.add_argument("--output", type=Path, required=True)
    catalog_registration_request.set_defaults(handler=_catalog_registration_request)

    catalog_register = commands.add_parser(
        "catalog-register",
        help="preflight or atomically register receipt-verified canonical datasets",
    )
    catalog_registration_source = catalog_register.add_mutually_exclusive_group(required=True)
    catalog_registration_source.add_argument(
        "--dataset",
        action="append",
        help="dataset ID; repeat and include any unregistered lineage parents",
    )
    catalog_registration_source.add_argument(
        "--request",
        type=Path,
        help="closed JSON request for registrations too large for the command line",
    )
    catalog_register.add_argument("--store-root", type=Path, required=True)
    catalog_register.add_argument("--catalog", type=Path, required=True)
    catalog_register.add_argument(
        "--software-identity",
        help="required with --dataset; file-backed requests contain their immutable identity",
    )
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

    full_history_catalog_evidence = commands.add_parser(
        "full-history-catalog-evidence",
        help="publish an identifier-free aggregate of one registration and four selections",
    )
    full_history_catalog_evidence.add_argument("--registration-request", type=Path, required=True)
    full_history_catalog_evidence.add_argument("--registration", type=Path, required=True)
    full_history_catalog_evidence.add_argument(
        "--selection", type=Path, action="append", required=True
    )
    full_history_catalog_evidence.add_argument("--software-identity", required=True)
    full_history_catalog_evidence.add_argument("--output", type=Path, required=True)
    full_history_catalog_evidence.set_defaults(handler=_full_history_catalog_evidence)

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


def _instrument_timeline(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    payload = build_instrument_timeline(tuple(args.instrument_registry))
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "receipt": str(receipt),
                "summary": payload["summary"],
            }
        )
    )
    return 0


def _verify_instrument_timeline(args: argparse.Namespace) -> int:
    verified = load_verified_instrument_timeline(args.timeline)
    print(
        json.dumps(
            {
                "artifact": str(verified.path),
                "artifact_sha256": verified.artifact_sha256,
                "coverage_instrument_count": len(verified.coverage),
                "snapshot_count": len(verified.snapshots),
                "valid": True,
            }
        )
    )
    return 0


def _instrument_timeline_summary(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    verified = load_verified_instrument_timeline(args.timeline)
    payload = build_instrument_timeline_summary(
        verified,
        software_identity=args.software_identity,
    )
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "blocker_codes": payload["blocker_codes"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


def _announcement_archive_depth(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    client = BybitPublicClient(UrllibJsonTransport(max_attempts=1))
    payload = build_announcement_archive_depth_evidence(
        client,
        instrument_registry_path=args.instrument_registry,
        instrument_ids=tuple(args.instrument_id),
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        software_identity=args.software_identity,
    )
    artifact, receipt = publish_evidence(output, payload)
    process = payload["process"]
    assert isinstance(process, dict)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "content_sha256": payload["content_sha256"],
                "receipt": str(receipt),
                "response_count": process["response_count"],
                "status": payload["status"],
            }
        )
    )
    return 2 if payload["status"] == "blocked-insufficient-official-announcement-history" else 0


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


def _history_campaign(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.staging_root)
    now_ms = time.time_ns() // 1_000_000
    preflight_started_ns = time.perf_counter_ns()
    plan = preflight_history_campaign(
        args.request,
        instrument_registry_path=args.instrument_registry,
        capacity_evidence_path=args.capacity_evidence,
        staging_root=args.staging_root,
        snapshot=snapshot,
        now_ms=now_ms,
        closed_before_ms=closed_before_now_ms(now_ms),
        funding_source_boundary_root=args.funding_source_boundary_root,
    )
    preflight_elapsed_ms = max(
        1,
        (time.perf_counter_ns() - preflight_started_ns + 999_999) // 1_000_000,
    )
    pending_jobs = sum(not job.existing_complete for job in plan.jobs)
    summary = {
        "campaign_root": str(plan.campaign_root),
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
        "job_count": len(plan.jobs),
        "pending_job_count": pending_jobs,
        "pending_page_count": sum(job.pending_page_count for job in plan.jobs),
        "plan_sha256": plan.plan_sha256,
        "preflight_elapsed_ms": preflight_elapsed_ms,
        "planned_page_count": sum(job.planned_page_count for job in plan.jobs),
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "request_sha256": plan.request_sha256,
        "required_free_bytes": plan.required_free_bytes,
        "status": "preflight-passed",
    }
    if "funding_source_boundary" in plan.plan_payload:
        summary["funding_source_boundary"] = plan.plan_payload["funding_source_boundary"]
    if not args.execute:
        print(json.dumps(summary))
        return 0
    completed = execute_history_campaign(
        plan,
        kline_client_factory=lambda: BybitPublicClient(
            UrllibJsonTransport(base_url="https://api.bybit.com", max_attempts=1)
        ),
        funding_client_factory=lambda: BybitPublicClient(
            UrllibJsonTransport(base_url="https://api.bybit.com", max_attempts=1)
        ),
        snapshot_provider=lambda: probe_host_snapshot(args.staging_root),
        progress=lambda job, completed_job: print(
            json.dumps(
                {
                    "event": "campaign-job-complete",
                    "job_count": len(plan.jobs),
                    "job_id": job.job_id,
                    "kind": job.kind,
                    "page_count": completed_job.page_count,
                    "row_count": completed_job.row_count,
                    "sequence": job.sequence,
                }
            ),
            flush=True,
        ),
    )
    summary.update(
        {
            "http_request_count": completed.http_request_count,
            "manifest": str(completed.manifest_path),
            "manifest_sha256": completed.manifest_sha256,
            "page_count": completed.page_count,
            "row_count": completed.row_count,
            "status": "complete",
        }
    )
    print(json.dumps(summary))
    return 0


def _verify_history_campaign(args: argparse.Namespace) -> int:
    completed = verify_completed_history_campaign(args.campaign_root)
    print(
        json.dumps(
            {
                "campaign_root": str(completed.campaign_root),
                "http_request_count": completed.http_request_count,
                "job_count": completed.job_count,
                "manifest_sha256": completed.manifest_sha256,
                "page_count": completed.page_count,
                "row_count": completed.row_count,
                "valid": True,
            }
        )
    )
    return 0


def _funding_source_boundary(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.output_root)
    observed_at_ms = time.time_ns() // 1_000_000
    plan = preflight_funding_source_boundary(
        args.request,
        instrument_registry_path=args.instrument_registry,
        output_root=args.output_root,
        snapshot=snapshot,
        now_ms=observed_at_ms,
        software_identity=args.software_identity,
    )
    summary = {
        "execute": bool(args.execute),
        "existing_complete": plan.existing_complete,
        "job_root": str(plan.job_root),
        "max_http_attempts": (len(plan.series) * plan.max_pages_per_symbol * plan.max_attempts),
        "plan_sha256": plan.plan_sha256,
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "required_free_bytes": plan.required_free_bytes,
        "status": "preflight-passed",
        "symbol_count": len(plan.series),
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    completed = execute_funding_source_boundary(
        plan,
        client_factory=lambda: BybitPublicClient(
            UrllibJsonTransport(base_url="https://api.bybit.com", max_attempts=1)
        ),
        snapshot_provider=lambda: probe_host_snapshot(args.output_root),
    )
    verified = verify_completed_funding_source_boundary(completed.job_root)
    summary.update(
        {
            "event_count": verified.event_count,
            "manifest_sha256": verified.manifest_sha256,
            "page_count": verified.page_count,
            "status": "complete",
        }
    )
    print(json.dumps(summary))
    return 0


def _verify_funding_source_boundary(args: argparse.Namespace) -> int:
    verified = verify_completed_funding_source_boundary(args.job_root)
    print(
        json.dumps(
            {
                "event_count": verified.event_count,
                "manifest_sha256": verified.manifest_sha256,
                "page_count": verified.page_count,
                "status": "verified",
                "symbol_count": verified.symbol_count,
            }
        )
    )
    return 0


def _funding_source_boundary_evidence(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    payload = build_funding_source_boundary_evidence(
        args.job_root,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        software_identity=args.software_identity,
    )
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "content_sha256": payload["content_sha256"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


def _history_campaign_evidence(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    payload = build_history_campaign_evidence(
        args.campaign_root,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        software_identity=args.software_identity,
        require_complete_throttling_evidence=args.require_complete_throttling_evidence,
    )
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "content_sha256": payload["content_sha256"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


def _publish_history_campaign(args: argparse.Namespace) -> int:
    if args.publication_root is not None and not args.execute:
        raise ValueError("--publication-root requires --execute")
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    if args.publication_root is None:
        plan = preflight_history_campaign_publication(
            args.campaign_root,
            instrument_registry_path=args.instrument_registry,
            capacity_evidence_path=args.capacity_evidence,
            store_root=args.store_root,
            snapshot=snapshot,
            now_ms=observed_at_ms,
            software_identity=args.software_identity,
        )
        verification_mode = "whole-campaign-semantic-preflight-v1"
    else:
        plan = load_prepared_history_campaign_publication(
            args.campaign_root,
            args.publication_root,
            instrument_registry_path=args.instrument_registry,
            capacity_evidence_path=args.capacity_evidence,
            store_root=args.store_root,
            snapshot=snapshot,
            now_ms=observed_at_ms,
            software_identity=args.software_identity,
        )
        verification_mode = "prepared-plan-receipt-resume-v1"
    summary = {
        "dataset_count": len(plan.jobs),
        "execute": bool(args.execute),
        "existing_commit_count": sum(job.existing_commit for job in plan.jobs),
        "existing_complete": plan.existing_complete,
        "pending_dataset_count": sum(not job.existing_commit for job in plan.jobs),
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "publication_root": str(plan.publication_root),
        "required_free_bytes": plan.required_free_bytes,
        "row_count": sum(job.row_count for job in plan.jobs),
        "source_campaign_manifest_sha256": plan.source_campaign_manifest_sha256,
        "status": "preflight-passed",
        "verification_mode": verification_mode,
    }
    if args.prepare_plan:
        prepare_history_campaign_publication_plan(plan)
        summary.update({"prepared_plan": True, "status": "plan-prepared"})
        print(json.dumps(summary))
        return 0
    if not args.execute:
        print(json.dumps(summary))
        return 0
    completed = execute_history_campaign_publication(
        plan,
        snapshot_provider=lambda: probe_host_snapshot(args.store_root),
        now_ms=lambda: time.time_ns() // 1_000_000,
        progress=lambda child, published: print(
            json.dumps(
                {
                    "dataset_count": len(plan.jobs),
                    "dataset_id": published.manifest.dataset_id,
                    "event": "campaign-publication-complete",
                    "existing_commit": child.existing_commit,
                    "kind": child.kind,
                    "row_count": published.manifest.row_count,
                    "sequence": child.sequence,
                }
            ),
            flush=True,
        ),
    )
    summary.update(
        {
            "file_count": completed.file_count,
            "manifest": str(completed.manifest_path),
            "manifest_sha256": completed.manifest_sha256,
            "parquet_bytes": completed.parquet_bytes,
            "status": "complete",
        }
    )
    print(json.dumps(summary))
    return 0


def _verify_history_campaign_publication(args: argparse.Namespace) -> int:
    completed = verify_completed_history_campaign_publication(
        args.publication_root,
        args.campaign_root,
    )
    print(
        json.dumps(
            {
                "dataset_count": completed.dataset_count,
                "file_count": completed.file_count,
                "manifest_sha256": completed.manifest_sha256,
                "parquet_bytes": completed.parquet_bytes,
                "publication_root": str(completed.publication_root),
                "row_count": completed.row_count,
                "valid": True,
            }
        )
    )
    return 0


def _history_campaign_publication_evidence(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    payload = build_history_campaign_publication_evidence(
        args.publication_root,
        args.campaign_root,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        software_identity=args.software_identity,
    )
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "content_sha256": payload["content_sha256"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


def _audit_history_campaign(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    audit = build_history_campaign_coverage_audit(
        args.publication_root,
        args.campaign_root,
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
                "content_sha256": audit.payload["content_sha256"],
                "inventory": audit.payload["inventory"],
                "receipt": str(receipt),
                "status": audit.payload["status"],
            }
        )
    )
    return 0 if audit.passed else 2


def _diagnose_history_campaign_boundaries(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    diagnostic = build_history_campaign_boundary_diagnostic(
        args.publication_root,
        args.campaign_root,
        args.instrument_registry,
        args.coverage_audit,
        diagnostic_software_identity=args.software_identity,
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    )
    artifact, receipt = publish_evidence(output, diagnostic.payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "content_sha256": diagnostic.payload["content_sha256"],
                "receipt": str(receipt),
                "result": diagnostic.payload["result"],
                "status": diagnostic.payload["status"],
            }
        )
    )
    return 2 if diagnostic.unresolved else 0


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


def _funding_history(args: argparse.Namespace) -> int:
    resolved = resolve_funding_request(
        args.request,
        instrument_registry_path=args.instrument_registry,
        capacity_evidence_path=args.capacity_evidence,
    )
    snapshot = probe_host_snapshot(args.staging_root)
    now_ms = time.time_ns() // 1_000_000
    plan = preflight_funding_job(
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
    completed = execute_funding_job(
        plan,
        lambda: BybitPublicClient(
            UrllibJsonTransport(base_url="https://api.bybit.com", max_attempts=1)
        ),
        lambda: probe_host_snapshot(args.staging_root),
    )
    summary.update(
        {
            "boundary_evidence_sha256": completed.boundary_evidence_sha256,
            "manifest": str(completed.manifest_path),
            "manifest_sha256": completed.manifest_sha256,
            "page_count": completed.page_count,
            "row_count": completed.row_count,
            "status": "complete",
        }
    )
    print(json.dumps(summary))
    return 0


def _verify_funding_history(args: argparse.Namespace) -> int:
    completed = verify_completed_funding_job(args.job_root)
    print(
        json.dumps(
            {
                "boundary_evidence_sha256": completed.boundary_evidence_sha256,
                "job_root": str(completed.job_root),
                "manifest_sha256": completed.manifest_sha256,
                "page_count": completed.page_count,
                "row_count": completed.row_count,
                "valid": True,
            }
        )
    )
    return 0


def _publish_funding_history(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    resolved = preflight_completed_funding_publication(
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
        "boundary_evidence_sha256": resolved.verified.completed.boundary_evidence_sha256,
        "dataset_id": plan.spec.dataset_id,
        "dataset_root": str(plan.paths.dataset_root),
        "execute": bool(args.execute),
        "existing_commit": plan.existing_commit,
        "funding_manifest_sha256": resolved.verified.completed.manifest_sha256,
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
    published = publish_preflighted_funding(
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


def _verify_canonical_funding(args: argparse.Namespace) -> int:
    published = verify_committed_funding_dataset(args.dataset_root)
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


def _funding_pilot_evidence(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    resolved = preflight_completed_funding_publication(
        args.store_root,
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        snapshot,
        now_ms=observed_at_ms,
        software_identity=args.software_identity,
    )
    if not resolved.plan.existing_commit:
        raise ValueError("pilot evidence requires the exact canonical funding publication to exist")
    published = verify_committed_funding_dataset(resolved.plan.paths.dataset_root)
    payload = build_funding_pilot_evidence(
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


def _audit_funding_history(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    audit = build_completed_funding_coverage_audit(
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


def _plan_funding_repair(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    plan = build_funding_repair_plan(
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
                "candidate_settlement_count": plan.candidate_count,
                "dataset_id": plan.payload["dataset_id"],
                "planned_max_http_requests": plan.planned_max_http_requests,
                "receipt": str(receipt),
                "status": plan.payload["status"],
                "task_count": plan.task_count,
            }
        )
    )
    return 0


def _execute_funding_repair(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.repair_staging_root)
    observed_at_ms = time.time_ns() // 1_000_000
    preflight = preflight_funding_repair_execution(
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
        verified_execution = verify_funding_repair_execution(
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
            raise ValueError("existing funding repair execution uses a different software identity")
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
        result = execute_funding_repair(
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
    summary.update(
        {
            "artifact": str(artifact),
            "limits": payload["limits"],
            "receipt": str(output.with_suffix(output.suffix + ".receipt.json")),
            "status": payload["status"],
        }
    )
    print(json.dumps(summary))
    return 0 if payload["status"] == "passed" else 2


def _funding_repair_execution_evidence(args: argparse.Namespace) -> int:
    verified = verify_funding_repair_execution(
        args.repair_execution,
        args.repair_plan,
        args.coverage_audit,
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        args.store_root,
        args.repair_staging_root,
    )
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    if output.exists() or receipt.exists():
        payload = verify_funding_repair_execution_public_evidence(output, verified)
        artifact = output
    else:
        preflight_evidence(output)
        payload = build_funding_repair_execution_public_evidence(
            verified,
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "limits": payload["limits"],
                "receipt": str(output.with_suffix(output.suffix + ".receipt.json")),
                "status": payload["status"],
                "storage_policy": payload["storage_policy"],
            }
        )
    )
    return 0


def _publish_funding_repair(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    resolved = preflight_repaired_funding_publication(
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
            raise ValueError("funding repair evidence conflicts with an uncommitted publication")
        published = verify_committed_funding_dataset(plan.paths.dataset_root)
        evidence = verify_funding_repair_replacement_evidence(
            output,
            resolved,
            published,
        )
    else:
        preflight_evidence(output)
    summary = {
        "dataset_id": plan.spec.dataset_id,
        "dataset_root": str(plan.paths.dataset_root),
        "execute": bool(args.execute),
        "existing_commit": plan.existing_commit,
        "existing_evidence": existing_evidence,
        "parent_dataset_id": resolved.parent.manifest.dataset_id,
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "repaired_row_count": resolved.repaired_row_count,
        "required_free_bytes": plan.required_free_bytes,
        "restated_interval_count": resolved.restated_interval_count,
        "status": "preflight-passed",
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    if published is not None and evidence is not None:
        artifact = output
    else:
        published = publish_preflighted_funding_repair(
            resolved,
            lambda: probe_host_snapshot(args.store_root),
            lambda: time.time_ns() // 1_000_000,
        )
        evidence = build_funding_repair_replacement_evidence(
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


def _audit_funding_repair(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing = output.exists() or receipt.exists()
    if existing:
        audit = verify_funding_repair_coverage_audit(
            output,
            args.repair_execution,
            args.repair_plan,
            args.original_coverage_audit,
            args.job_root,
            args.instrument_registry,
            args.capacity_evidence,
            args.store_root,
            args.repair_staging_root,
            args.replacement_evidence,
            expected_publisher_software_identity=args.publisher_software_identity,
            expected_audit_software_identity=args.audit_software_identity,
        )
        artifact = output
    else:
        preflight_evidence(output)
        audit = build_funding_repair_coverage_audit(
            args.repair_execution,
            args.repair_plan,
            args.original_coverage_audit,
            args.job_root,
            args.instrument_registry,
            args.capacity_evidence,
            args.store_root,
            args.repair_staging_root,
            args.replacement_evidence,
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
                "existing": existing,
                "quality": audit.payload["quality"],
                "receipt": str(receipt),
                "status": audit.payload["status"],
            }
        )
    )
    return 0 if audit.passed else 2


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


def _history_repair_execution_evidence(args: argparse.Namespace) -> int:
    verified = verify_gap_repair_execution(
        args.repair_execution,
        args.repair_plan,
        args.coverage_audit,
        args.job_root,
        args.instrument_registry,
        args.capacity_evidence,
        args.store_root,
        args.repair_staging_root,
    )
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    if output.exists() or receipt.exists():
        payload = verify_candle_repair_execution_public_evidence(output, verified)
        artifact = output
    else:
        preflight_evidence(output)
        payload = build_candle_repair_execution_public_evidence(
            verified,
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "limits": payload["limits"],
                "outcome": payload["outcome"],
                "receipt": str(output.with_suffix(output.suffix + ".receipt.json")),
                "status": payload["status"],
                "storage_policy": payload["storage_policy"],
            }
        )
    )
    return 0


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


def _compact_funding(args: argparse.Namespace) -> int:
    snapshot = probe_host_snapshot(args.store_root)
    observed_at_ms = time.time_ns() // 1_000_000
    resolved = preflight_funding_compaction(
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
            raise ValueError(
                "funding compaction evidence conflicts with an uncommitted publication"
            )
        published = verify_committed_funding_dataset(plan.paths.dataset_root)
        evidence = verify_funding_compaction_evidence(output, resolved, published)
    else:
        preflight_evidence(output)
    summary = {
        "dataset_id": plan.spec.dataset_id,
        "dataset_root": str(plan.paths.dataset_root),
        "execute": bool(args.execute),
        "existing_commit": plan.existing_commit,
        "existing_evidence": existing_evidence,
        "expected_output_file_count": 1,
        "input_file_count": resolved.input_file_count,
        "parent_dataset_ids": list(plan.spec.parent_dataset_ids),
        "planned_peak_memory_bytes": plan.planned_peak_memory_bytes,
        "required_free_bytes": plan.required_free_bytes,
        "status": "preflight-passed",
    }
    if not args.execute:
        print(json.dumps(summary))
        return 0
    if published is not None and evidence is not None:
        artifact = output
    else:
        published = publish_preflighted_funding_compaction(
            resolved,
            lambda: probe_host_snapshot(args.store_root),
            lambda: time.time_ns() // 1_000_000,
        )
        evidence = build_funding_compaction_evidence(
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


def _audit_funding_compaction_candidates(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing = output.exists() or receipt.exists()
    if existing:
        payload = verify_funding_compaction_candidate_audit(output, args.store_root)
        if payload["auditor_software_identity"] != args.software_identity:
            raise ValueError("existing funding candidate audit uses another software identity")
    else:
        preflight_evidence(output)
        payload = build_funding_compaction_candidate_audit(
            args.store_root,
            auditor_software_identity=args.software_identity,
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    if args.execute and not existing:
        artifact, receipt = publish_evidence(output, payload)
    else:
        artifact = output
    summary = {
        "artifact": str(artifact) if args.execute or existing else None,
        "classification_counts": payload["classification_counts"],
        "dataset_count": payload["dataset_count"],
        "execute": bool(args.execute),
        "existing_audit": existing,
        "multi_parent_partition_count": payload["multi_parent_partition_count"],
        "pair_count": payload["pair_count"],
        "partition_count": payload["partition_count"],
        "receipt": str(receipt) if args.execute or existing else None,
        "status": payload["status"],
    }
    print(json.dumps(summary))
    return 0


def _funding_compaction_candidate_evidence(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing = output.exists() or receipt.exists()
    if existing:
        payload = verify_funding_compaction_candidate_evidence(
            output,
            args.audit,
            args.store_root,
        )
        bindings = payload["bindings"]
        if (
            not isinstance(bindings, dict)
            or bindings.get("publisher_software_identity") != args.software_identity
        ):
            raise ValueError("existing funding candidate evidence uses another software identity")
        artifact = output
    else:
        preflight_evidence(output)
        payload = build_funding_compaction_candidate_evidence(
            args.audit,
            args.store_root,
            publisher_software_identity=args.software_identity,
        )
        artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "classification_counts": payload["classification_counts"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


def _funding_repair_candidate_inputs(
    args: argparse.Namespace,
) -> tuple[FundingRepairCandidateInput, ...]:
    audits = args.coverage_audit
    job_roots = args.job_root
    registries = args.instrument_registry
    if not (len(audits) == len(job_roots) == len(registries)):
        raise ValueError("coverage-audit, job-root, and instrument-registry counts must match")
    return tuple(
        FundingRepairCandidateInput(audit, job_root, registry)
        for audit, job_root, registry in zip(audits, job_roots, registries, strict=True)
    )


def _audit_funding_repair_candidates(args: argparse.Namespace) -> int:
    candidates = _funding_repair_candidate_inputs(args)
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing = output.exists() or receipt.exists()
    if existing:
        payload = verify_funding_repair_candidate_audit(
            output,
            candidates,
            args.capacity_evidence,
            args.store_root,
        )
        if payload["auditor_software_identity"] != args.software_identity:
            raise ValueError("existing funding repair audit uses another software identity")
    else:
        preflight_evidence(output)
        payload = build_funding_repair_candidate_audit(
            candidates,
            args.capacity_evidence,
            args.store_root,
            auditor_software_identity=args.software_identity,
            generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    if args.execute and not existing:
        artifact, receipt = publish_evidence(output, payload)
    else:
        artifact = output
    print(
        json.dumps(
            {
                "artifact": str(artifact) if args.execute or existing else None,
                "audit_count": payload["audit_count"],
                "classification_counts": payload["classification_counts"],
                "execute": bool(args.execute),
                "existing_audit": existing,
                "receipt": str(receipt) if args.execute or existing else None,
                "status": payload["status"],
            }
        )
    )
    return 0


def _funding_repair_candidate_evidence(args: argparse.Namespace) -> int:
    candidates = _funding_repair_candidate_inputs(args)
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing = output.exists() or receipt.exists()
    if existing:
        payload = verify_funding_repair_candidate_evidence(
            output,
            args.audit,
            candidates,
            args.capacity_evidence,
            args.store_root,
        )
        bindings = payload["bindings"]
        if (
            not isinstance(bindings, dict)
            or bindings.get("publisher_software_identity") != args.software_identity
        ):
            raise ValueError(
                "existing funding repair candidate evidence uses another software identity"
            )
        artifact = output
    else:
        preflight_evidence(output)
        payload = build_funding_repair_candidate_evidence(
            args.audit,
            candidates,
            args.capacity_evidence,
            args.store_root,
            publisher_software_identity=args.software_identity,
        )
        artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "classification_counts": payload["classification_counts"],
                "receipt": str(receipt),
                "status": payload["status"],
            }
        )
    )
    return 0


def _catalog_registration_request(args: argparse.Namespace) -> int:
    completed = verify_completed_history_campaign_publication(
        args.publication_root,
        args.campaign_root,
    )
    request = CatalogRegistrationRequest(
        dataset_ids=tuple(
            sorted(item.manifest.dataset_id for item in completed.published_datasets)
        ),
        software_identity=args.software_identity,
    )
    if len(request.dataset_ids) != completed.dataset_count:
        raise ValueError("publication dataset inventory is not unique")
    output = args.output.resolve()
    receipt = output.with_suffix(output.suffix + ".receipt.json")
    existing = output.exists() or receipt.exists()
    if existing:
        if not verify_evidence(output):
            raise ValueError("existing catalog registration request receipt does not verify")
        stored = load_catalog_registration_request(output)
        if stored != request:
            raise ValueError("existing catalog registration request no longer matches publication")
        artifact = output
    else:
        preflight_evidence(output)
        artifact, receipt = publish_evidence(
            output,
            catalog_registration_request_payload(request),
        )
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "dataset_count": len(request.dataset_ids),
                "publication_manifest_sha256": completed.manifest_sha256,
                "receipt": str(receipt),
                "request_sha256": request.request_sha256,
                "status": "registration-request-ready",
            }
        )
    )
    return 0


def _catalog_register(args: argparse.Namespace) -> int:
    if args.request is not None:
        if args.software_identity is not None:
            raise ValueError("--software-identity must not override a file-backed request")
        if not verify_evidence(args.request):
            raise ValueError("catalog registration request receipt does not verify")
        request = load_catalog_registration_request(args.request)
        dataset_ids = request.dataset_ids
        software_identity = request.software_identity
        request_sha256: str | None = request.request_sha256
    else:
        if args.software_identity is None:
            raise ValueError("--software-identity is required with --dataset")
        dataset_ids = tuple(args.dataset)
        software_identity = args.software_identity
        request_sha256 = None
    plan = preflight_catalog_registration(
        dataset_ids,
        args.store_root,
        args.catalog,
        software_identity=software_identity,
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
        "request_sha256": request_sha256,
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


def _full_history_catalog_evidence(args: argparse.Namespace) -> int:
    output, _receipt = preflight_evidence(args.output)
    payload = build_full_history_catalog_evidence(
        args.registration_request,
        args.registration,
        tuple(args.selection),
        generated_at_utc=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        software_identity=args.software_identity,
    )
    artifact, receipt = publish_evidence(output, payload)
    print(
        json.dumps(
            {
                "artifact": str(artifact),
                "content_sha256": payload["content_sha256"],
                "receipt": str(receipt),
                "status": payload["status"],
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
