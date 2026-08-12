"""Bound actual Bybit V5 history depth without retaining market values."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from grid_bybit_public import BybitPublicError
from grid_bybit_public.transport import TransportError
from grid_contracts.canonical import canonical_sha256
from grid_contracts.market import MINUTE_MS

DatasetName = Literal["funding", "mark_price_1m", "trade_price_1m"]

DATASETS: tuple[DatasetName, ...] = ("funding", "mark_price_1m", "trade_price_1m")
CHECKPOINT_PERIOD_DAYS = 365
CHECKPOINT_WINDOW_DAYS = 7
LAUNCH_WINDOW_MINUTES = 1_000
DAY_MS = 24 * 60 * MINUTE_MS
MAX_REQUEST_LIMIT = 5_000
MAX_SAMPLE_SIZE = 20
MAX_WORKERS = 16


@dataclass(frozen=True, slots=True)
class ProbeTarget:
    symbol: str
    status: str
    launch_time_ms: int
    delivery_time_ms: int | None
    funding_interval_minutes: int
    probe_start_ms: int
    probe_end_ms: int


class HistoryClient(Protocol):
    def kline_page(
        self,
        *,
        kind: Literal["trade", "mark"],
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 1000,
    ) -> tuple[tuple[str, ...], ...]: ...

    def funding_page(
        self,
        *,
        symbol: str,
        start_ms: int,
        end_ms: int,
        category: Literal["linear", "inverse"] = "linear",
        limit: int = 200,
    ) -> tuple[Mapping[str, Any], ...]: ...


def build_rest_history_boundary(
    client_factory: Callable[[], HistoryClient],
    inventory: Mapping[str, Any],
    *,
    command: str,
    inventory_artifact: str,
    inventory_artifact_sha256: str,
    sample_size: int = 8,
    workers: int = 8,
    max_requests: int = 1_000,
) -> dict[str, Any]:
    """Probe bounded history endpoints and persist no market values."""
    if not 2 <= sample_size <= MAX_SAMPLE_SIZE:
        raise ValueError(f"sample_size must be in [2, {MAX_SAMPLE_SIZE}]")
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be in [1, {MAX_WORKERS}]")
    if not 1 <= max_requests <= MAX_REQUEST_LIMIT:
        raise ValueError(f"max_requests must be in [1, {MAX_REQUEST_LIMIT}]")
    targets, eligible_counts = _select_targets(inventory, sample_size)
    planned_upper_bound = sum(_planned_requests(target) for target in targets)
    if planned_upper_bound > max_requests:
        raise ValueError(
            "planned REST boundary requests exceed max_requests: "
            f"{planned_upper_bound} > {max_requests}"
        )

    worker_count = min(workers, len(targets))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = tuple(
            executor.map(lambda target: _probe_target(client_factory(), target), targets)
        )
    results = tuple(sorted(results, key=lambda item: item["symbol"]))
    actual_requests = sum(
        int(dataset["request_count"])
        for result in results
        for dataset in result["datasets"].values()
    )
    if actual_requests > planned_upper_bound or actual_requests > max_requests:
        raise RuntimeError("actual request count exceeded its preflighted bound")

    summary = _summary(results)
    status = "bounded-sample-complete" if summary["error_count"] == 0 else "bounded-sample-partial"
    payload: dict[str, Any] = {
        "command": command,
        "content_sha256": "",
        "evidence_schema": "grid.bybit-rest-history-boundary/v1",
        "fetched_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "inventory_source": {
            "artifact": inventory_artifact,
            "artifact_sha256": inventory_artifact_sha256,
            "evidence_schema": inventory["evidence_schema"],
            "fetched_at_utc": inventory["fetched_at_utc"],
            "inventory_status": inventory.get("inventory_status"),
        },
        "limitations": [
            (
                "The result is a deterministic launch-time-stratified sample, not "
                "full-universe coverage."
            ),
            (
                "Earliest observed timestamps are bounded by current lifecycle metadata and the "
                "endpoint behavior observed at fetch time."
            ),
            (
                "Annual and terminal seven-day checkpoints can expose sampled empty periods but "
                "cannot prove that every minute between checkpoints is present."
            ),
            "Current launch, delivery, status, and funding interval fields are not dated history.",
            (
                "Launch-window pages are processed in memory and annual checkpoints request at "
                "most one row; only timestamps and hashes are persisted, not market values."
            ),
            "This evidence does not authorize the Phase 2 full-history downloader or close Gate 1.",
        ],
        "request_audit": {
            "actual_request_count": actual_requests,
            "annual_checkpoint_page_limit": 1,
            "checkpoint_period_days": CHECKPOINT_PERIOD_DAYS,
            "checkpoint_window_days": CHECKPOINT_WINDOW_DAYS,
            "launch_window_funding_page_limit": 200,
            "launch_window_kline_page_limit": 1_000,
            "launch_window_minutes": LAUNCH_WINDOW_MINUTES,
            "max_requests": max_requests,
            "planned_request_upper_bound": planned_upper_bound,
            "terminal_checkpoint_enabled": True,
            "transport_max_attempts": 1,
            "worker_count": worker_count,
        },
        "selection": {
            "algorithm": "equal-status-launch-time-stratified-v1",
            "eligible_status_counts": eligible_counts,
            "requested_sample_size": sample_size,
            "selected_sample_size": len(targets),
            "selected_status_counts": dict(
                sorted(Counter(target.status for target in targets).items())
            ),
            "symbols": [target.symbol for target in targets],
        },
        "source_policy": {
            "funding": "/v5/market/funding/history",
            "mark_price_1m": "/v5/market/mark-price-kline",
            "trade_price_1m": "/v5/market/kline",
        },
        "sources": {
            "funding_documentation": (
                "https://bybit-exchange.github.io/docs/v5/market/history-fund-rate"
            ),
            "mark_price_documentation": (
                "https://bybit-exchange.github.io/docs/v5/market/mark-kline"
            ),
            "trade_price_documentation": "https://bybit-exchange.github.io/docs/v5/market/kline",
        },
        "status": status,
        "storage_policy": {
            "market_rows_persisted": False,
            "market_values_persisted": False,
            "response_content_hashes_persisted": True,
            "tick_rows_requested": False,
        },
        "summary": summary,
        "symbols": list(results),
    }
    hash_input = dict(payload)
    hash_input.pop("content_sha256")
    payload["content_sha256"] = canonical_sha256(hash_input)
    return payload


def _inventory_snapshot_ms(inventory: Mapping[str, Any]) -> int:
    raw = inventory.get("fetched_at_utc")
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise ValueError("inventory fetched_at_utc must be UTC text")
    try:
        value = datetime.fromisoformat(raw.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError("inventory fetched_at_utc is invalid") from error
    if value.tzinfo != UTC:
        raise ValueError("inventory fetched_at_utc must resolve to UTC")
    return int(value.timestamp() * 1_000)


def _select_targets(
    inventory: Mapping[str, Any], sample_size: int
) -> tuple[tuple[ProbeTarget, ...], dict[str, int]]:
    raw_records = inventory.get("records")
    if inventory.get("evidence_schema") != "grid.bybit-public-inventory/v1" or not isinstance(
        raw_records, list
    ):
        raise ValueError("unsupported instrument inventory evidence")
    snapshot_ms = _inventory_snapshot_ms(inventory)
    candidates: dict[str, list[ProbeTarget]] = {"Closed": [], "Trading": []}
    symbols: set[str] = set()
    for raw in raw_records:
        if not isinstance(raw, Mapping):
            raise ValueError("instrument inventory records must be objects")
        if not (
            raw.get("contract_type") == "LinearPerpetual"
            and raw.get("quote_coin") == "USDT"
            and raw.get("settle_coin") == "USDT"
        ):
            continue
        symbol = raw.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol in symbols:
            raise ValueError("inventory USDT perpetual symbols must be unique non-empty text")
        symbols.add(symbol)
        status = raw.get("status")
        if status not in candidates:
            continue
        launch_ms = raw.get("launch_time_ms")
        delivery_ms = raw.get("delivery_time_ms")
        funding_interval = raw.get("funding_interval_minutes")
        if (
            not isinstance(launch_ms, int)
            or launch_ms < 0
            or (delivery_ms is not None and not isinstance(delivery_ms, int))
            or not isinstance(funding_interval, int)
            or funding_interval <= 0
        ):
            raise ValueError("inventory record has invalid lifecycle or funding metadata")
        active_end_exclusive = snapshot_ms
        if delivery_ms not in (None, 0):
            active_end_exclusive = min(active_end_exclusive, delivery_ms)
        probe_start = launch_ms // MINUTE_MS * MINUTE_MS
        probe_end = (active_end_exclusive - 1) // MINUTE_MS * MINUTE_MS
        if probe_end < probe_start:
            continue
        candidates[status].append(
            ProbeTarget(
                symbol=symbol,
                status=status,
                launch_time_ms=launch_ms,
                delivery_time_ms=delivery_ms,
                funding_interval_minutes=funding_interval,
                probe_start_ms=probe_start,
                probe_end_ms=probe_end,
            )
        )
    for values in candidates.values():
        values.sort(key=lambda target: (target.launch_time_ms, target.symbol))
    eligible_counts = {status: len(values) for status, values in sorted(candidates.items())}
    if sum(eligible_counts.values()) < sample_size:
        raise ValueError("inventory has too few eligible Trading/Closed USDT perpetuals")

    desired = {"Closed": sample_size // 2, "Trading": sample_size - sample_size // 2}
    selected: list[ProbeTarget] = []
    for status in ("Trading", "Closed"):
        count = min(desired[status], len(candidates[status]))
        selected.extend(_rank_sample(candidates[status], count))
    if len(selected) < sample_size:
        selected_symbols = {target.symbol for target in selected}
        remaining = sorted(
            (
                target
                for values in candidates.values()
                for target in values
                if target.symbol not in selected_symbols
            ),
            key=lambda target: (target.launch_time_ms, target.symbol),
        )
        selected.extend(_rank_sample(remaining, sample_size - len(selected)))
    return tuple(sorted(selected, key=lambda target: target.symbol)), eligible_counts


def _rank_sample(values: Sequence[ProbeTarget], count: int) -> tuple[ProbeTarget, ...]:
    if count <= 0:
        return ()
    if count >= len(values):
        return tuple(values)
    if count == 1:
        return (values[0],)
    positions = tuple(index * (len(values) - 1) // (count - 1) for index in range(count))
    return tuple(values[position] for position in positions)


def _checkpoint_windows(target: ProbeTarget) -> tuple[tuple[str, int, int], ...]:
    period_ms = CHECKPOINT_PERIOD_DAYS * DAY_MS
    window_ms = CHECKPOINT_WINDOW_DAYS * DAY_MS
    launch_end = min(
        target.probe_end_ms,
        target.probe_start_ms + (LAUNCH_WINDOW_MINUTES - 1) * MINUTE_MS,
    )
    windows: list[tuple[str, int, int]] = []
    checkpoint_start = target.probe_start_ms + period_ms
    while checkpoint_start <= target.probe_end_ms:
        checkpoint_end = min(
            target.probe_end_ms,
            checkpoint_start + window_ms - MINUTE_MS,
        )
        windows.append(("annual", checkpoint_start, checkpoint_end))
        checkpoint_start += period_ms
    if launch_end < target.probe_end_ms and (not windows or windows[-1][2] < target.probe_end_ms):
        terminal_start = max(
            launch_end + MINUTE_MS,
            target.probe_end_ms - window_ms + MINUTE_MS,
        )
        windows.append(("terminal", terminal_start, target.probe_end_ms))
    return tuple(windows)


def _checkpoint_count(target: ProbeTarget) -> int:
    return 1 + len(_checkpoint_windows(target))


def _planned_requests(target: ProbeTarget) -> int:
    return len(DATASETS) * _checkpoint_count(target)


def _probe_target(client: HistoryClient, target: ProbeTarget) -> dict[str, Any]:
    return {
        "datasets": {dataset: _probe_dataset(client, target, dataset) for dataset in DATASETS},
        "delivery_time_ms": target.delivery_time_ms,
        "funding_interval_minutes": target.funding_interval_minutes,
        "launch_time_ms": target.launch_time_ms,
        "probe_end_ms": target.probe_end_ms,
        "probe_start_ms": target.probe_start_ms,
        "status": target.status,
        "symbol": target.symbol,
    }


def _probe_dataset(
    client: HistoryClient, target: ProbeTarget, dataset: DatasetName
) -> dict[str, Any]:
    request_count = 0
    checkpoints: list[dict[str, Any]] = []
    earliest_time: int | None = None
    launch_hash: str | None = None
    launch_window_nonempty = False

    def observe(start_ms: int, end_ms: int, *, launch_window: bool) -> dict[str, Any]:
        nonlocal request_count
        request_count += 1
        return _observe(
            client,
            target.symbol,
            dataset,
            start_ms,
            end_ms,
            launch_window=launch_window,
        )

    try:
        launch_end = min(
            target.probe_end_ms,
            target.probe_start_ms + (LAUNCH_WINDOW_MINUTES - 1) * MINUTE_MS,
        )
        launch_observation = observe(
            target.probe_start_ms,
            launch_end,
            launch_window=True,
        )
        launch_hash = str(launch_observation["response_content_sha256"])
        launch_window_nonempty = bool(launch_observation["nonempty"])
        if launch_window_nonempty:
            observed = launch_observation["earliest_observed_time_ms"]
            if not isinstance(observed, int):
                raise RuntimeError("non-empty launch observation has no timestamp")
            earliest_time = observed
        availability = "available" if launch_window_nonempty else "unavailable"

        for checkpoint_kind, checkpoint_start, checkpoint_end in _checkpoint_windows(target):
            observation = observe(checkpoint_start, checkpoint_end, launch_window=False)
            observed = observation["earliest_observed_time_ms"]
            if isinstance(observed, int):
                availability = "available"
                earliest_time = observed if earliest_time is None else min(earliest_time, observed)
            checkpoints.append(
                {
                    "end_ms": checkpoint_end,
                    "kind": checkpoint_kind,
                    "nonempty": observation["nonempty"],
                    "observed_time_ms": observed,
                    "response_content_sha256": observation["response_content_sha256"],
                    "start_ms": checkpoint_start,
                }
            )
    except (BybitPublicError, TransportError) as error:
        availability = "error"
        error_text: str | None = str(error)
        observation_semantics = "error"
    else:
        error_text = None
        if launch_window_nonempty:
            observation_semantics = "exact-within-launch-window"
        elif availability == "available":
            observation_semantics = "sampled-checkpoint-not-exact-boundary"
        else:
            observation_semantics = "none-observed-in-probed-windows"

    return {
        "checkpoint_empty_count": sum(not item["nonempty"] for item in checkpoints),
        "checkpoint_nonempty_count": sum(bool(item["nonempty"]) for item in checkpoints),
        "checkpoints": checkpoints,
        "delay_after_probe_start_minutes": (
            None if earliest_time is None else (earliest_time - target.probe_start_ms) // MINUTE_MS
        ),
        "earliest_observed_time_ms": earliest_time,
        "error": error_text,
        "launch_window_nonempty": launch_window_nonempty,
        "launch_window_response_content_sha256": launch_hash,
        "observation_semantics": observation_semantics,
        "request_count": request_count,
        "status": availability,
    }


def _observe(
    client: HistoryClient,
    symbol: str,
    dataset: DatasetName,
    start_ms: int,
    end_ms: int,
    *,
    launch_window: bool,
) -> dict[str, Any]:
    if dataset == "funding":
        raw_rows: Sequence[Any] = client.funding_page(
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=200 if launch_window else 1,
        )
        timestamps: list[int] = []
        for row in raw_rows:
            if not isinstance(row, Mapping) or row.get("symbol") != symbol:
                raise BybitPublicError("funding response symbol mismatch")
            raw_timestamp = row.get("fundingRateTimestamp")
            if not isinstance(raw_timestamp, str):
                raise BybitPublicError("funding timestamp must be text")
            try:
                timestamps.append(int(raw_timestamp))
            except ValueError as error:
                raise BybitPublicError("funding timestamp must be integer text") from error
    else:
        kind: Literal["mark", "trade"] = "mark" if dataset == "mark_price_1m" else "trade"
        raw_rows = client.kline_page(
            kind=kind,
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            limit=1_000 if launch_window else 1,
        )
        timestamps = [int(row[0]) for row in raw_rows]
    if timestamps != sorted(timestamps, reverse=True) or len(timestamps) != len(set(timestamps)):
        raise BybitPublicError("history endpoint returned non-unique reverse timestamps")
    if any(not start_ms <= timestamp <= end_ms for timestamp in timestamps):
        raise BybitPublicError("history endpoint returned a timestamp outside requested bounds")
    if any(timestamp % MINUTE_MS for timestamp in timestamps):
        raise BybitPublicError("history endpoint returned a non-minute-aligned timestamp")
    return {
        "earliest_observed_time_ms": min(timestamps) if timestamps else None,
        "nonempty": bool(timestamps),
        "response_content_sha256": canonical_sha256(raw_rows),
    }


def _summary(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    dataset_summaries: dict[str, Any] = {}
    error_count = 0
    for dataset in DATASETS:
        entries = [result["datasets"][dataset] for result in results]
        counts = Counter(str(entry["status"]) for entry in entries)
        semantics_counts = Counter(str(entry["observation_semantics"]) for entry in entries)
        error_count += counts["error"]
        earliest = [
            int(entry["earliest_observed_time_ms"])
            for entry in entries
            if entry["earliest_observed_time_ms"] is not None
        ]
        delays = [
            int(entry["delay_after_probe_start_minutes"])
            for entry in entries
            if entry["delay_after_probe_start_minutes"] is not None
        ]
        dataset_summaries[dataset] = {
            "earliest_observed_time_ms": min(earliest) if earliest else None,
            "largest_delay_after_probe_start_minutes": max(delays) if delays else None,
            "observation_semantics_counts": {
                semantics: semantics_counts[semantics]
                for semantics in (
                    "error",
                    "exact-within-launch-window",
                    "none-observed-in-probed-windows",
                    "sampled-checkpoint-not-exact-boundary",
                )
            },
            "status_counts": {
                status: counts[status] for status in ("available", "error", "unavailable")
            },
            "total_checkpoint_empty_count": sum(
                int(entry["checkpoint_empty_count"]) for entry in entries
            ),
            "total_checkpoint_nonempty_count": sum(
                int(entry["checkpoint_nonempty_count"]) for entry in entries
            ),
        }
    return {
        "dataset_summaries": dataset_summaries,
        "error_count": error_count,
        "selected_symbol_count": len(results),
    }
