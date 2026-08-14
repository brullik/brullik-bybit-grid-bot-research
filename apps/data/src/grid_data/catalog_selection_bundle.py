"""Receipt-resumable catalog selections over several verified candle campaigns."""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_contracts.market import MINUTE_MS, DatasetType
from grid_market_store import stable_bucket
from grid_market_store.catalog import (
    CatalogSelection,
    CatalogSelectionRequest,
    select_catalog_ranges,
    selection_request_payload,
)

from grid_data.dataset_catalog import (
    build_catalog_selection_evidence,
    verify_catalog_selection_evidence,
)
from grid_data.evidence import publish_evidence, verify_evidence
from grid_data.history_campaign_publication import (
    verify_completed_history_campaign_publication,
)
from grid_data.instrument_registry import load_verified_instrument_registry

BUNDLE_REQUEST_CONTRACT: Final = "grid.canonical-catalog-selection-bundle-request/v1"
BUNDLE_PLAN_CONTRACT: Final = "grid.canonical-catalog-selection-bundle-plan/v1"
BUNDLE_MANIFEST_CONTRACT: Final = "grid.canonical-catalog-selection-bundle-manifest/v1"
BUNDLE_EVIDENCE_CONTRACT: Final = "grid.phase2-catalog-selection-bundle/v1"
MAX_BUNDLE_SOURCES: Final = 16
MAX_BUNDLE_SELECTIONS: Final = 512
_BUNDLE_ID_RE: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{2,79}$")
_GIT_IDENTITY_RE: Final = re.compile(r"^git:[0-9a-f]{40}$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_KIND_ORDER: Final = {"trade": 0, "mark": 1}
_DATASET_TYPE_BY_KIND: Final = {
    "trade": DatasetType.TRADE_KLINE_1M,
    "mark": DatasetType.MARK_KLINE_1M,
}


class CatalogSelectionBundleError(RuntimeError):
    """A multi-campaign selection bundle is incomplete, ambiguous, or substituted."""


@dataclass(frozen=True, slots=True)
class BundleSourceSpec:
    campaign_id: str
    start_time_ms: int
    end_time_ms: int


@dataclass(frozen=True, slots=True)
class CatalogSelectionBundleRequest:
    path: Path
    payload: dict[str, object]
    bundle_id: str
    catalog_revision: int
    catalog_content_sha256: str
    consumer_software_identity: str
    sources: tuple[BundleSourceSpec, ...]

    @property
    def request_sha256(self) -> str:
        return canonical_sha256(self.payload)


@dataclass(frozen=True, slots=True)
class PreparedBundleSelection:
    sequence: int
    campaign_id: str
    kind: str
    segment: int
    request: CatalogSelectionRequest
    selection: CatalogSelection


@dataclass(frozen=True, slots=True)
class PreparedCatalogSelectionBundle:
    request: CatalogSelectionBundleRequest
    output_root: Path
    plan_payload: dict[str, object]
    plan_sha256: str
    selections: tuple[PreparedBundleSelection, ...]
    source_bindings: tuple[dict[str, object], ...]
    instrument_count: int
    dataset_count: int


@dataclass(frozen=True, slots=True)
class CompletedCatalogSelectionBundle:
    root: Path
    plan_path: Path
    manifest_path: Path
    manifest_sha256: str
    selection_count: int
    dataset_count: int
    object_count: int
    row_count: int
    size_bytes: int


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogSelectionBundleError(f"bundle input is not valid JSON: {path.name}") from error
    if not isinstance(raw, dict):
        raise CatalogSelectionBundleError(f"bundle input must be a JSON object: {path.name}")
    return cast(dict[str, object], raw)


def _integer(name: str, value: object, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CatalogSelectionBundleError(f"{name} must be an exact integer >= {minimum}")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise CatalogSelectionBundleError(f"{name} must be non-empty trimmed text")
    return value


def _generated_at(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CatalogSelectionBundleError("bundle timestamp must be ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CatalogSelectionBundleError("bundle timestamp must be timezone-aware")
    return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _month_bounds(month: str) -> tuple[int, int]:
    if re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month) is None:
        raise CatalogSelectionBundleError("campaign job month is invalid")
    year, month_number = (int(value) for value in month.split("-"))
    start = datetime(year, month_number, 1, tzinfo=UTC)
    end = datetime(
        year,
        month_number,
        calendar.monthrange(year, month_number)[1],
        23,
        59,
        tzinfo=UTC,
    )
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def _month_key(timestamp_ms: int) -> str:
    value = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    return f"{value.year:04d}-{value.month:02d}"


def _next_month(month: str) -> str:
    year, month_number = (int(value) for value in month.split("-"))
    if month_number == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month_number + 1:02d}"


def _require_full_month_range(start_time_ms: int, end_time_ms: int) -> None:
    if start_time_ms % MINUTE_MS or end_time_ms % MINUTE_MS or end_time_ms < start_time_ms:
        raise CatalogSelectionBundleError("bundle source range must be ordered and minute-aligned")
    if _month_bounds(_month_key(start_time_ms))[0] != start_time_ms:
        raise CatalogSelectionBundleError("bundle source range must start at a UTC month boundary")
    if _month_bounds(_month_key(end_time_ms))[1] != end_time_ms:
        raise CatalogSelectionBundleError("bundle source range must end at a UTC month boundary")


def load_catalog_selection_bundle_request(path: Path) -> CatalogSelectionBundleRequest:
    """Parse the closed private request without coercion or implicit catalog selection."""

    resolved = path.resolve()
    raw = _load_json_object(resolved)
    expected = {
        "bundle_id",
        "catalog_content_sha256",
        "catalog_revision",
        "consumer_software_identity",
        "contract",
        "sources",
    }
    if set(raw) != expected or raw.get("contract") != BUNDLE_REQUEST_CONTRACT:
        raise CatalogSelectionBundleError("bundle request fields or contract do not match v1")
    bundle_id = _text("bundle_id", raw.get("bundle_id"))
    if _BUNDLE_ID_RE.fullmatch(bundle_id) is None:
        raise CatalogSelectionBundleError("bundle_id does not match the bounded v1 identifier")
    revision = _integer("catalog_revision", raw.get("catalog_revision"), minimum=1)
    catalog_hash = _text("catalog_content_sha256", raw.get("catalog_content_sha256"))
    if _SHA256_RE.fullmatch(catalog_hash) is None:
        raise CatalogSelectionBundleError("catalog_content_sha256 must be lowercase SHA-256")
    software_identity = _text("consumer_software_identity", raw.get("consumer_software_identity"))
    if _GIT_IDENTITY_RE.fullmatch(software_identity) is None:
        raise CatalogSelectionBundleError("consumer identity must be immutable git:<40 hex>")
    raw_sources = raw.get("sources")
    if not isinstance(raw_sources, list) or not 1 <= len(raw_sources) <= MAX_BUNDLE_SOURCES:
        raise CatalogSelectionBundleError("bundle sources must contain 1 through 16 items")
    sources = []
    for item in raw_sources:
        if not isinstance(item, dict) or set(item) != {
            "campaign_id",
            "end_time_ms",
            "start_time_ms",
        }:
            raise CatalogSelectionBundleError("bundle source fields do not match v1")
        campaign_id = _text("campaign_id", item.get("campaign_id"))
        if _BUNDLE_ID_RE.fullmatch(campaign_id) is None:
            raise CatalogSelectionBundleError("source campaign_id is invalid")
        start_time_ms = _integer("source start_time_ms", item.get("start_time_ms"))
        end_time_ms = _integer("source end_time_ms", item.get("end_time_ms"))
        _require_full_month_range(start_time_ms, end_time_ms)
        sources.append(BundleSourceSpec(campaign_id, start_time_ms, end_time_ms))
    if tuple(item.campaign_id for item in sources) != tuple(
        sorted({item.campaign_id for item in sources})
    ):
        raise CatalogSelectionBundleError("bundle sources must be sorted and unique by campaign_id")
    return CatalogSelectionBundleRequest(
        path=resolved,
        payload=raw,
        bundle_id=bundle_id,
        catalog_revision=revision,
        catalog_content_sha256=catalog_hash,
        consumer_software_identity=software_identity,
        sources=tuple(sources),
    )


def _campaign_id(path: Path) -> str:
    plan = _load_json_object(path / "plan.json")
    return _text("campaign_id", plan.get("campaign_id"))


def _paired_roots(
    campaign_roots: tuple[Path, ...],
    publication_roots: tuple[Path, ...],
) -> dict[str, tuple[Path, Path]]:
    if len(campaign_roots) != len(publication_roots) or not campaign_roots:
        raise CatalogSelectionBundleError(
            "campaign and publication roots must be non-empty one-to-one lists"
        )
    result: dict[str, tuple[Path, Path]] = {}
    for campaign_root, publication_root in zip(campaign_roots, publication_roots, strict=True):
        campaign = campaign_root.resolve()
        publication = publication_root.resolve()
        campaign_id = _campaign_id(campaign)
        if campaign_id in result:
            raise CatalogSelectionBundleError("campaign roots contain duplicate campaign_id")
        result[campaign_id] = (campaign, publication)
    return result


def _job_series_ids(job: dict[str, object], by_symbol: dict[str, object]) -> tuple[int, ...]:
    request = job.get("request")
    if not isinstance(request, dict):
        raise CatalogSelectionBundleError("campaign job request is invalid")
    raw_series = request.get("series")
    if not isinstance(raw_series, list) or not raw_series:
        raise CatalogSelectionBundleError("campaign job has no source series")
    instrument_ids = []
    for item in raw_series:
        if not isinstance(item, dict):
            raise CatalogSelectionBundleError("campaign series entry is invalid")
        symbol = _text("series symbol", item.get("symbol"))
        snapshot = by_symbol.get(symbol)
        instrument_id = getattr(snapshot, "instrument_id", None)
        if isinstance(instrument_id, bool) or not isinstance(instrument_id, int):
            raise CatalogSelectionBundleError("campaign symbol is absent from the bound registry")
        instrument_ids.append(instrument_id)
    if len(instrument_ids) != len(set(instrument_ids)):
        raise CatalogSelectionBundleError("campaign job repeats an instrument")
    return tuple(sorted(instrument_ids))


def _publication_jobs_by_source_job(plan: dict[str, object]) -> dict[str, dict[str, object]]:
    raw_jobs = plan.get("jobs")
    if not isinstance(raw_jobs, list):
        raise CatalogSelectionBundleError("publication plan has no job inventory")
    result: dict[str, dict[str, object]] = {}
    for value in raw_jobs:
        if not isinstance(value, dict):
            raise CatalogSelectionBundleError("publication job entry is invalid")
        item = cast(dict[str, object], value)
        job_id = _text("publication job_id", item.get("job_id"))
        if job_id in result:
            raise CatalogSelectionBundleError("publication plan repeats a source job")
        result[job_id] = item
    return result


def _source_months(
    source: BundleSourceSpec,
    source_plan: dict[str, object],
    publication_plan: dict[str, object],
    by_symbol: dict[str, object],
) -> tuple[dict[str, dict[str, tuple[tuple[str, ...], tuple[int, ...]]]], set[int]]:
    raw_jobs = source_plan.get("jobs")
    if not isinstance(raw_jobs, list):
        raise CatalogSelectionBundleError("source campaign plan has no job inventory")
    publication_by_job = _publication_jobs_by_source_job(publication_plan)
    monthly: dict[str, dict[str, tuple[tuple[str, ...], tuple[int, ...]]]] = {
        "trade": {},
        "mark": {},
    }
    monthly_work: dict[tuple[str, str], dict[str, set[object]]] = {}
    all_instruments: set[int] = set()
    for value in raw_jobs:
        if not isinstance(value, dict):
            raise CatalogSelectionBundleError("source campaign job entry is invalid")
        job = cast(dict[str, object], value)
        kind = _text("campaign job kind", job.get("kind"))
        if kind not in _KIND_ORDER:
            continue
        month = _text("campaign job month", job.get("month"))
        month_start, month_end = _month_bounds(month)
        if month_end < source.start_time_ms or month_start > source.end_time_ms:
            continue
        if month_start < source.start_time_ms or month_end > source.end_time_ms:
            raise CatalogSelectionBundleError("source range clips a campaign month partially")
        job_id = _text("campaign job_id", job.get("job_id"))
        published = publication_by_job.get(job_id)
        if published is None or published.get("kind") != kind:
            raise CatalogSelectionBundleError("publication is missing a selected source job")
        dataset_id = _text("publication dataset_id", published.get("dataset_id"))
        instrument_ids = _job_series_ids(job, by_symbol)
        bucket = _integer("campaign job bucket", job.get("bucket"))
        if bucket > 7 or {stable_bucket(value) for value in instrument_ids} != {bucket}:
            raise CatalogSelectionBundleError("campaign job bucket differs from stable identities")
        work = monthly_work.setdefault(
            (kind, month), {"dataset_ids": set(), "instrument_ids": set()}
        )
        work["dataset_ids"].add(dataset_id)
        work["instrument_ids"].update(instrument_ids)
        all_instruments.update(instrument_ids)
    for kind in _KIND_ORDER:
        for (item_kind, month), work in monthly_work.items():
            if item_kind != kind:
                continue
            dataset_ids = tuple(sorted(cast(set[str], work["dataset_ids"])))
            instrument_ids = tuple(sorted(cast(set[int], work["instrument_ids"])))
            monthly[kind][month] = (dataset_ids, instrument_ids)
    if not monthly["trade"] or set(monthly["trade"]) != set(monthly["mark"]):
        raise CatalogSelectionBundleError("source trade/mark month inventories differ")
    for month in monthly["trade"]:
        if monthly["trade"][month][1] != monthly["mark"][month][1]:
            raise CatalogSelectionBundleError("source trade/mark instrument topology differs")
    return monthly, all_instruments


def _segment_requests(
    source: BundleSourceSpec,
    monthly: dict[str, dict[str, tuple[tuple[str, ...], tuple[int, ...]]]],
    request: CatalogSelectionBundleRequest,
) -> tuple[tuple[str, int, CatalogSelectionRequest], ...]:
    result: list[tuple[str, int, CatalogSelectionRequest]] = []
    for kind in sorted(_KIND_ORDER, key=_KIND_ORDER.__getitem__):
        months = sorted(monthly[kind])
        segment = 0
        cursor = 0
        while cursor < len(months):
            first = months[cursor]
            instrument_ids = monthly[kind][first][1]
            dataset_ids = list(monthly[kind][first][0])
            last = first
            cursor += 1
            while (
                cursor < len(months)
                and months[cursor] == _next_month(last)
                and monthly[kind][months[cursor]][1] == instrument_ids
            ):
                last = months[cursor]
                dataset_ids.extend(monthly[kind][last][0])
                cursor += 1
            segment += 1
            start_time_ms = _month_bounds(first)[0]
            end_time_ms = _month_bounds(last)[1]
            result.append(
                (
                    kind,
                    segment,
                    CatalogSelectionRequest(
                        catalog_revision=request.catalog_revision,
                        catalog_content_sha256=request.catalog_content_sha256,
                        dataset_ids=tuple(sorted(dataset_ids)),
                        dataset_type=_DATASET_TYPE_BY_KIND[kind],
                        start_time_ms=start_time_ms,
                        end_time_ms=end_time_ms,
                        instrument_ids=instrument_ids,
                        consumer_software_identity=request.consumer_software_identity,
                    ),
                )
            )
    return tuple(result)


def _assert_cross_source_disjoint(
    source_months: dict[str, dict[str, dict[str, tuple[tuple[str, ...], tuple[int, ...]]]]],
) -> None:
    campaign_ids = sorted(source_months)
    for index, left_id in enumerate(campaign_ids):
        left = source_months[left_id]["trade"]
        for right_id in campaign_ids[index + 1 :]:
            right = source_months[right_id]["trade"]
            for month in set(left).intersection(right):
                if set(left[month][1]).intersection(right[month][1]):
                    raise CatalogSelectionBundleError(
                        "bundle sources overlap canonical instrument/minute key space"
                    )


def preflight_catalog_selection_bundle(
    request_path: Path,
    *,
    campaign_roots: tuple[Path, ...],
    publication_roots: tuple[Path, ...],
    instrument_registry_path: Path,
    store_root: Path,
    catalog_path: Path,
    output_root: Path,
) -> PreparedCatalogSelectionBundle:
    """Verify sources and resolve all exact v1 selections before any bundle output is written."""

    request = load_catalog_selection_bundle_request(request_path)
    registry = load_verified_instrument_registry(instrument_registry_path)
    by_symbol = cast(dict[str, object], registry.by_symbol())
    roots = _paired_roots(campaign_roots, publication_roots)
    if set(roots) != {item.campaign_id for item in request.sources}:
        raise CatalogSelectionBundleError("provided roots do not match the requested campaigns")

    source_bindings: list[dict[str, object]] = []
    source_months: dict[str, dict[str, dict[str, tuple[tuple[str, ...], tuple[int, ...]]]]] = {}
    all_instruments: set[int] = set()
    request_specs: list[tuple[str, str, int, CatalogSelectionRequest]] = []
    for source in request.sources:
        campaign_root, publication_root = roots[source.campaign_id]
        completed = verify_completed_history_campaign_publication(publication_root, campaign_root)
        source_plan_path = campaign_root / "plan.json"
        source_manifest_path = campaign_root / "manifest.json"
        publication_plan_path = publication_root / "plan.json"
        source_plan = _load_json_object(source_plan_path)
        publication_plan = _load_json_object(publication_plan_path)
        if source_plan.get("instrument_evidence_sha256") != registry.artifact_sha256:
            raise CatalogSelectionBundleError("source campaign binds another instrument registry")
        monthly, source_instruments = _source_months(
            source, source_plan, publication_plan, by_symbol
        )
        source_months[source.campaign_id] = monthly
        all_instruments.update(source_instruments)
        segments = _segment_requests(source, monthly, request)
        for kind, segment, selection_request in segments:
            request_specs.append((source.campaign_id, kind, segment, selection_request))
        source_bindings.append(
            {
                "campaign_id": source.campaign_id,
                "campaign_manifest_sha256": sha256_file(source_manifest_path),
                "campaign_plan_sha256": sha256_file(source_plan_path),
                "end_time_ms": source.end_time_ms,
                "instrument_count": len(source_instruments),
                "publication_manifest_sha256": completed.manifest_sha256,
                "publication_plan_sha256": sha256_file(publication_plan_path),
                "selection_count": len(segments),
                "start_time_ms": source.start_time_ms,
            }
        )
    _assert_cross_source_disjoint(source_months)
    request_specs.sort(key=lambda item: (item[0], _KIND_ORDER[item[1]], item[2]))
    if not 1 <= len(request_specs) <= MAX_BUNDLE_SELECTIONS:
        raise CatalogSelectionBundleError(
            "bundle resolves outside the 1 through 512 selection bound"
        )
    dataset_ids = [
        dataset_id
        for _campaign_id, _kind, _segment, item in request_specs
        for dataset_id in item.dataset_ids
    ]
    if not 1 <= len(dataset_ids) <= 10_000:
        raise CatalogSelectionBundleError("bundle dataset inventory exceeds the 10,000 bound")
    if len(dataset_ids) != len(set(dataset_ids)):
        raise CatalogSelectionBundleError("bundle selection requests repeat dataset identity")
    selections = select_catalog_ranges(
        tuple(item[3] for item in request_specs), store_root, catalog_path
    )
    prepared = tuple(
        PreparedBundleSelection(sequence, campaign_id, kind, segment, item_request, selection)
        for sequence, ((campaign_id, kind, segment, item_request), selection) in enumerate(
            zip(request_specs, selections, strict=True)
        )
    )
    plan_payload: dict[str, object] = {
        "bundle_id": request.bundle_id,
        "bundle_request": request.payload,
        "bundle_request_sha256": request.request_sha256,
        "catalog": {
            "content_sha256": request.catalog_content_sha256,
            "revision": request.catalog_revision,
        },
        "contract": BUNDLE_PLAN_CONTRACT,
        "dataset_count": len(dataset_ids),
        "instrument_count": len(all_instruments),
        "instrument_registry_sha256": registry.artifact_sha256,
        "selection_count": len(prepared),
        "selections": [
            {
                "campaign_id": item.campaign_id,
                "kind": item.kind,
                "request": selection_request_payload(item.request),
                "request_sha256": item.request.request_sha256,
                "segment": item.segment,
                "sequence": item.sequence,
            }
            for item in prepared
        ],
        "source_bindings": source_bindings,
        "selection_policy": {
            "catalog_verified_once": True,
            "cross_source_key_space": "disjoint-instrument-minute-by-month-v1",
            "month_topology": "contiguous-equal-instrument-inventory-v1",
            "selector": "grid.canonical-dataset-selection-request/v1",
        },
    }
    prepared_bundle = PreparedCatalogSelectionBundle(
        request=request,
        output_root=output_root.resolve(),
        plan_payload=plan_payload,
        plan_sha256=canonical_sha256(plan_payload),
        selections=prepared,
        source_bindings=tuple(source_bindings),
        instrument_count=len(all_instruments),
        dataset_count=len(dataset_ids),
    )
    _preflight_output_root(prepared_bundle)
    return prepared_bundle


def _selection_path(root: Path, sequence: int) -> Path:
    return root / "selections" / f"{sequence:04d}.json"


def _preflight_output_root(prepared: PreparedCatalogSelectionBundle) -> None:
    root = prepared.output_root
    if not root.exists():
        return
    if not root.is_dir() or root.is_symlink() or root.parent.is_symlink():
        raise CatalogSelectionBundleError("bundle output root must be a non-symlink directory")
    allowed = {
        "manifest.json",
        "manifest.json.receipt.json",
        "plan.json",
        "plan.json.receipt.json",
        "selections",
    }
    names = {path.name for path in root.iterdir()}
    if not names.issubset(allowed):
        raise CatalogSelectionBundleError("bundle output root contains orphan artifacts")
    plan_path = root / "plan.json"
    plan_receipt = plan_path.with_suffix(plan_path.suffix + ".receipt.json")
    if plan_path.exists() != plan_receipt.exists():
        raise CatalogSelectionBundleError("bundle plan artifact/receipt pair is incomplete")
    if plan_path.exists() and (
        not verify_evidence(plan_path) or _load_json_object(plan_path) != prepared.plan_payload
    ):
        raise CatalogSelectionBundleError(
            "existing bundle plan differs from deterministic preflight"
        )
    selection_dir = root / "selections"
    if selection_dir.exists():
        if not selection_dir.is_dir() or selection_dir.is_symlink():
            raise CatalogSelectionBundleError("bundle selections path must be a directory")
        selection_names = {path.name for path in selection_dir.iterdir()}
        expected = {
            name
            for item in prepared.selections
            for name in (
                f"{item.sequence:04d}.json",
                f"{item.sequence:04d}.json.receipt.json",
            )
        }
        if not selection_names.issubset(expected):
            raise CatalogSelectionBundleError("bundle selections contain orphan artifacts")
        for item in prepared.selections:
            artifact = _selection_path(root, item.sequence)
            receipt = artifact.with_suffix(artifact.suffix + ".receipt.json")
            if artifact.exists() != receipt.exists():
                raise CatalogSelectionBundleError("bundle selection artifact/receipt is incomplete")
    manifest_path = root / "manifest.json"
    manifest_receipt = manifest_path.with_suffix(manifest_path.suffix + ".receipt.json")
    if manifest_path.exists() != manifest_receipt.exists():
        raise CatalogSelectionBundleError("bundle manifest artifact/receipt pair is incomplete")
    if manifest_path.exists() and not verify_evidence(manifest_path):
        raise CatalogSelectionBundleError("existing bundle completion receipt does not verify")


def _publish_or_verify_selection(
    path: Path,
    prepared: PreparedBundleSelection,
    *,
    generated_at_utc: str,
) -> dict[str, object]:
    receipt = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists() or receipt.exists():
        if not verify_evidence(path):
            raise CatalogSelectionBundleError("existing bundle selection receipt does not verify")
        return verify_catalog_selection_evidence(path, prepared.selection)
    payload = build_catalog_selection_evidence(
        prepared.selection, generated_at_utc=generated_at_utc
    )
    publish_evidence(path, payload)
    return payload


def _manifest_payload(
    prepared: PreparedCatalogSelectionBundle,
    selection_payloads: tuple[tuple[PreparedBundleSelection, Path, dict[str, object]], ...],
    *,
    completed_at_utc: str,
) -> dict[str, object]:
    object_count = 0
    row_count = 0
    size_bytes = 0
    empty_object_count = 0
    bindings = []
    for item, path, payload in selection_payloads:
        selection = payload.get("selection")
        objects = payload.get("objects")
        if not isinstance(selection, dict) or not isinstance(objects, list):
            raise CatalogSelectionBundleError("selection evidence aggregate is invalid")
        item_object_count = _integer("selection object_count", selection.get("object_count"))
        item_row_count = _integer(
            "selection selected_row_inventory", selection.get("selected_row_inventory")
        )
        item_size_bytes = _integer(
            "selection selected_size_bytes", selection.get("selected_size_bytes")
        )
        object_count += item_object_count
        row_count += item_row_count
        size_bytes += item_size_bytes
        empty_object_count += sum(
            isinstance(value, dict) and value.get("row_count") == 0 for value in objects
        )
        content_sha256 = _text("selection content_sha256", payload.get("content_sha256"))
        if _SHA256_RE.fullmatch(content_sha256) is None:
            raise CatalogSelectionBundleError("selection content hash is invalid")
        bindings.append(
            {
                "artifact_sha256": sha256_file(path),
                "campaign_id": item.campaign_id,
                "content_sha256": content_sha256,
                "dataset_count": len(item.request.dataset_ids),
                "kind": item.kind,
                "object_count": item_object_count,
                "request_sha256": item.request.request_sha256,
                "row_count": item_row_count,
                "segment": item.segment,
                "sequence": item.sequence,
                "size_bytes": item_size_bytes,
            }
        )
    return {
        "bundle_id": prepared.request.bundle_id,
        "catalog": {
            "content_sha256": prepared.request.catalog_content_sha256,
            "revision": prepared.request.catalog_revision,
        },
        "completed_at_utc": completed_at_utc,
        "contract": BUNDLE_MANIFEST_CONTRACT,
        "dataset_count": prepared.dataset_count,
        "empty_object_count": empty_object_count,
        "instrument_count": prepared.instrument_count,
        "object_count": object_count,
        "plan_sha256": prepared.plan_sha256,
        "row_count": row_count,
        "selection_count": len(prepared.selections),
        "selections": bindings,
        "size_bytes": size_bytes,
        "source_bindings": list(prepared.source_bindings),
        "status": "complete",
    }


def execute_catalog_selection_bundle(
    prepared: PreparedCatalogSelectionBundle,
    *,
    generated_at_utc: str,
) -> CompletedCatalogSelectionBundle:
    """Publish a resumable private plan, selections, and receipt-last completion manifest."""

    generated_at = _generated_at(generated_at_utc)
    _preflight_output_root(prepared)
    root = prepared.output_root
    if root.exists() and (not root.is_dir() or root.is_symlink()):
        raise CatalogSelectionBundleError("bundle output root must be a non-symlink directory")
    root.mkdir(parents=True, exist_ok=True)
    plan_path = root / "plan.json"
    plan_receipt = plan_path.with_suffix(plan_path.suffix + ".receipt.json")
    if plan_path.exists() or plan_receipt.exists():
        if not verify_evidence(plan_path) or _load_json_object(plan_path) != prepared.plan_payload:
            raise CatalogSelectionBundleError(
                "existing bundle plan differs from deterministic preflight"
            )
    else:
        publish_evidence(plan_path, prepared.plan_payload)
    selection_dir = root / "selections"
    selection_dir.mkdir(exist_ok=True)
    payloads = []
    for item in prepared.selections:
        path = _selection_path(root, item.sequence)
        payload = _publish_or_verify_selection(path, item, generated_at_utc=generated_at)
        payloads.append((item, path, payload))
    manifest_path = root / "manifest.json"
    manifest_receipt = manifest_path.with_suffix(manifest_path.suffix + ".receipt.json")
    if manifest_path.exists() or manifest_receipt.exists():
        if not verify_evidence(manifest_path):
            raise CatalogSelectionBundleError("existing bundle completion receipt does not verify")
        existing = _load_json_object(manifest_path)
        completed_at = _text("completed_at_utc", existing.get("completed_at_utc"))
        expected = _manifest_payload(prepared, tuple(payloads), completed_at_utc=completed_at)
        if existing != expected:
            raise CatalogSelectionBundleError(
                "existing bundle manifest differs from verified inputs"
            )
        manifest = existing
    else:
        manifest = _manifest_payload(prepared, tuple(payloads), completed_at_utc=generated_at)
        publish_evidence(manifest_path, manifest)
    return CompletedCatalogSelectionBundle(
        root=root,
        plan_path=plan_path,
        manifest_path=manifest_path,
        manifest_sha256=sha256_file(manifest_path),
        selection_count=_integer("manifest selection_count", manifest.get("selection_count")),
        dataset_count=_integer("manifest dataset_count", manifest.get("dataset_count")),
        object_count=_integer("manifest object_count", manifest.get("object_count")),
        row_count=_integer("manifest row_count", manifest.get("row_count")),
        size_bytes=_integer("manifest size_bytes", manifest.get("size_bytes")),
    )


def build_catalog_selection_bundle_evidence(
    prepared: PreparedCatalogSelectionBundle,
    completed: CompletedCatalogSelectionBundle,
    *,
    generated_at_utc: str,
    software_identity: str,
) -> dict[str, object]:
    """Project a completed private bundle without source, dataset, or instrument identities."""

    generated_at = _generated_at(generated_at_utc)
    if _GIT_IDENTITY_RE.fullmatch(software_identity) is None:
        raise CatalogSelectionBundleError("bundle evidence identity must be git:<40 hex>")
    if completed.root != prepared.output_root or not verify_evidence(completed.manifest_path):
        raise CatalogSelectionBundleError("completed bundle receipt does not verify")
    manifest = _load_json_object(completed.manifest_path)
    if manifest.get("plan_sha256") != prepared.plan_sha256:
        raise CatalogSelectionBundleError("completed bundle binds another deterministic plan")
    by_kind = []
    raw_bindings = manifest.get("selections")
    if not isinstance(raw_bindings, list):
        raise CatalogSelectionBundleError("bundle manifest has no selection bindings")
    for kind in ("trade", "mark"):
        selected = [
            cast(dict[str, object], item)
            for item in raw_bindings
            if isinstance(item, dict) and item.get("kind") == kind
        ]
        by_kind.append(
            {
                "dataset_count": sum(
                    _integer("dataset_count", item.get("dataset_count")) for item in selected
                ),
                "kind": kind,
                "object_count": sum(
                    _integer("object_count", item.get("object_count")) for item in selected
                ),
                "row_count": sum(_integer("row_count", item.get("row_count")) for item in selected),
                "selection_count": len(selected),
                "size_bytes": sum(
                    _integer("size_bytes", item.get("size_bytes")) for item in selected
                ),
            }
        )
    source_chain = canonical_sha256(
        [
            {
                "campaign_manifest_sha256": item["campaign_manifest_sha256"],
                "campaign_plan_sha256": item["campaign_plan_sha256"],
                "publication_manifest_sha256": item["publication_manifest_sha256"],
                "publication_plan_sha256": item["publication_plan_sha256"],
            }
            for item in prepared.source_bindings
        ]
    )
    selection_chain = canonical_sha256(
        [
            {
                "artifact_sha256": item["artifact_sha256"],
                "content_sha256": item["content_sha256"],
                "request_sha256": item["request_sha256"],
            }
            for item in cast(list[dict[str, object]], raw_bindings)
        ]
    )
    payload: dict[str, object] = {
        "assurances": {
            "catalog_snapshot_bound": True,
            "cross_source_key_space_disjoint": True,
            "network_request_performed": False,
            "private_or_live_capability_used": False,
            "selection_receipts_verified": True,
            "source_campaigns_and_publications_verified": True,
        },
        "bindings": {
            "bundle_manifest_artifact_sha256": completed.manifest_sha256,
            "bundle_plan_sha256": prepared.plan_sha256,
            "bundle_request_sha256": prepared.request.request_sha256,
            "evidence_builder_software_identity": software_identity,
            "selection_chain_sha256": selection_chain,
            "source_chain_sha256": source_chain,
        },
        "catalog": {
            "content_sha256": prepared.request.catalog_content_sha256,
            "revision": prepared.request.catalog_revision,
        },
        "evidence_schema": BUNDLE_EVIDENCE_CONTRACT,
        "generated_at_utc": generated_at,
        "inventory": {
            "by_kind": by_kind,
            "dataset_count": completed.dataset_count,
            "empty_object_count": _integer(
                "manifest empty_object_count", manifest.get("empty_object_count")
            ),
            "instrument_count": prepared.instrument_count,
            "object_count": completed.object_count,
            "row_count": completed.row_count,
            "selection_count": completed.selection_count,
            "size_bytes": completed.size_bytes,
            "source_count": len(prepared.source_bindings),
        },
        "limitations": [
            "Catalog selection does not prove gap-free historical coverage or lifecycle reasons.",
            "The bundle is candle-only and does not accept funding chronology or cadence.",
            "Schema-only objects remain explicit and do not accept missing source history.",
            "This evidence does not close Gate 2, authorize Phase 3, or enable live execution.",
        ],
        "status": "verified-catalog-selection-bundle",
        "storage_policy": {
            "evidence_contains_account_data": False,
            "evidence_contains_dataset_identities": False,
            "evidence_contains_instrument_identities": False,
            "evidence_contains_market_values": False,
            "evidence_contains_request_time_bounds": False,
            "evidence_contains_runtime_paths": False,
            "runtime_catalog_or_market_artifacts_committed_to_git": False,
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload
