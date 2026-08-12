"""Verified stable identities and dated metadata for Bybit linear instruments."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Final, cast

from grid_contracts.canonical import canonical_sha256, sha256_file
from grid_contracts.market import InstrumentSnapshot

from grid_data.archive_inventory import load_verified_public_inventory
from grid_data.evidence import verify_evidence

INSTRUMENT_REGISTRY_CONTRACT: Final = "grid.instrument-registry/v1"
IDENTITY_ALGORITHM: Final = "bybit-linear-source-symbol-id-v1"
UINT32_MAX: Final = (1 << 32) - 1
SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_SNAPSHOT_FIELDS: Final = frozenset(InstrumentSnapshot.__dataclass_fields__)


class InstrumentRegistryError(ValueError):
    """Instrument evidence cannot establish a stable, exact registry snapshot."""


@dataclass(frozen=True, slots=True)
class VerifiedInstrumentRegistry:
    path: Path
    artifact_sha256: str
    payload: dict[str, object]
    snapshots: tuple[InstrumentSnapshot, ...]

    def by_symbol(self) -> dict[str, InstrumentSnapshot]:
        return {item.symbol: item for item in self.snapshots}


def _snapshot_time_ms(raw: object) -> int:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise InstrumentRegistryError("inventory fetched_at_utc must be UTC text")
    try:
        observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise InstrumentRegistryError("inventory fetched_at_utc is invalid") from error
    if observed.tzinfo is None or observed.utcoffset() != UTC.utcoffset(observed):
        raise InstrumentRegistryError("inventory fetched_at_utc must resolve to UTC")
    return int(observed.timestamp() * 1000)


def _integer(name: str, value: object, *, allow_none: bool = False) -> int | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise InstrumentRegistryError(f"{name} must be an integer")
    return value


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise InstrumentRegistryError(f"{name} must be non-empty trimmed text")
    return value


def _decimal(name: str, value: object) -> Decimal:
    raw = _text(name, value)
    try:
        parsed = Decimal(raw)
    except InvalidOperation as error:
        raise InstrumentRegistryError(f"{name} must be exact decimal text") from error
    if not parsed.is_finite():
        raise InstrumentRegistryError(f"{name} must be finite")
    return parsed


def _delivery_time(record: dict[str, object]) -> int | None:
    raw = _integer("delivery_time_ms", record.get("delivery_time_ms"), allow_none=True)
    # Bybit represents a perpetual contract's absent delivery date as the numeric sentinel 0.
    return None if raw == 0 else raw


def _funding_interval(record: dict[str, object]) -> int | None:
    raw = _integer(
        "funding_interval_minutes",
        record.get("funding_interval_minutes"),
        allow_none=True,
    )
    # Dated/non-funding linear products use the same zero-as-not-applicable sentinel.
    return None if raw == 0 else raw


def _snapshot_from_inventory(
    record: dict[str, object], snapshot_time_ms: int
) -> InstrumentSnapshot:
    source_symbol_id = _integer("source_symbol_id", record.get("source_symbol_id"))
    assert source_symbol_id is not None
    if not 1 <= source_symbol_id <= UINT32_MAX:
        raise InstrumentRegistryError("source_symbol_id must fit the registry UInt32 identity")
    source_hash = _text("source_payload_sha256", record.get("source_payload_sha256"))
    if not SHA256_RE.fullmatch(source_hash):
        raise InstrumentRegistryError("source_payload_sha256 must be lowercase SHA-256")
    try:
        return InstrumentSnapshot(
            snapshot_time_ms=snapshot_time_ms,
            category="linear",
            instrument_id=source_symbol_id,
            source_symbol_id=source_symbol_id,
            symbol=_text("symbol", record.get("symbol")),
            contract_type=_text("contract_type", record.get("contract_type")),
            status=_text("status", record.get("status")),
            base_coin=_text("base_coin", record.get("base_coin")),
            quote_coin=_text("quote_coin", record.get("quote_coin")),
            settle_coin=_text("settle_coin", record.get("settle_coin")),
            launch_time_ms=cast(int, _integer("launch_time_ms", record.get("launch_time_ms"))),
            delivery_time_ms=_delivery_time(record),
            tick_size=_decimal("tick_size", record.get("tick_size")),
            quantity_step=_decimal("quantity_step", record.get("quantity_step")),
            min_order_quantity=_decimal("min_order_quantity", record.get("min_order_quantity")),
            max_order_quantity=_decimal("max_order_quantity", record.get("max_order_quantity")),
            min_leverage=_decimal("min_leverage", record.get("min_leverage")),
            max_leverage=_decimal("max_leverage", record.get("max_leverage")),
            funding_interval_minutes=_funding_interval(record),
            source_payload_sha256=source_hash,
        )
    except ValueError as error:
        raise InstrumentRegistryError("inventory row violates the instrument contract") from error


def _snapshot_payload(snapshot: InstrumentSnapshot) -> dict[str, object]:
    payload = asdict(snapshot)
    for name in (
        "tick_size",
        "quantity_step",
        "min_order_quantity",
        "max_order_quantity",
        "min_leverage",
        "max_leverage",
    ):
        payload[name] = format(cast(Decimal, payload[name]), "f")
    return cast(dict[str, object], payload)


def build_instrument_registry(
    inventory: dict[str, Any], *, inventory_artifact_sha256: str
) -> dict[str, object]:
    """Build a deterministic current-snapshot registry without renumbering source identities."""

    if inventory.get("evidence_schema") != "grid.bybit-public-inventory/v1":
        raise InstrumentRegistryError("unsupported public inventory evidence")
    if not SHA256_RE.fullmatch(inventory_artifact_sha256):
        raise InstrumentRegistryError("inventory artifact binding must be lowercase SHA-256")
    raw_records = inventory.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise InstrumentRegistryError("instrument inventory records must be a non-empty array")
    if any(not isinstance(item, dict) for item in raw_records):
        raise InstrumentRegistryError("instrument inventory records must be objects")
    snapshot_time_ms = _snapshot_time_ms(inventory.get("fetched_at_utc"))
    snapshots = tuple(
        sorted(
            (
                _snapshot_from_inventory(cast(dict[str, object], item), snapshot_time_ms)
                for item in raw_records
            ),
            key=lambda item: item.instrument_id,
        )
    )
    identities = [item.instrument_id for item in snapshots]
    symbols = [item.symbol for item in snapshots]
    if len(identities) != len(set(identities)):
        raise InstrumentRegistryError("Bybit linear source_symbol_id values are not unique")
    if len(symbols) != len(set(symbols)):
        raise InstrumentRegistryError("Bybit linear symbols are not unique in one snapshot")
    eligible = tuple(
        item
        for item in snapshots
        if item.contract_type == "LinearPerpetual"
        and item.quote_coin == "USDT"
        and item.settle_coin == "USDT"
    )
    if not eligible:
        raise InstrumentRegistryError("registry has no USDT linear perpetual instruments")
    source_content_sha = inventory.get("content_sha256")
    if not isinstance(source_content_sha, str) or not SHA256_RE.fullmatch(source_content_sha):
        raise InstrumentRegistryError("inventory has no verified embedded content hash")
    payload: dict[str, object] = {
        "evidence_schema": INSTRUMENT_REGISTRY_CONTRACT,
        "identity_policy": {
            "algorithm": IDENTITY_ALGORITHM,
            "category": "linear",
            "instrument_id_expression": "source_symbol_id",
            "range": "uint32-positive",
        },
        "records": [_snapshot_payload(item) for item in snapshots],
        "source_inventory": {
            "artifact_sha256": inventory_artifact_sha256,
            "content_sha256": source_content_sha,
            "evidence_schema": inventory["evidence_schema"],
            "fetched_at_utc": inventory["fetched_at_utc"],
            "inventory_status": inventory.get("inventory_status"),
        },
        "summary": {
            "instrument_count": len(snapshots),
            "maximum_instrument_id": max(identities),
            "minimum_instrument_id": min(identities),
            "usdt_linear_perpetual_count": len(eligible),
        },
    }
    payload["content_sha256"] = canonical_sha256(payload)
    return payload


def _snapshot_from_registry(record: object) -> InstrumentSnapshot:
    if not isinstance(record, dict) or set(record) != _SNAPSHOT_FIELDS:
        raise InstrumentRegistryError("registry record fields do not match v1")
    typed = cast(dict[str, object], record)
    decimal_names = (
        "tick_size",
        "quantity_step",
        "min_order_quantity",
        "max_order_quantity",
        "min_leverage",
        "max_leverage",
    )
    values = dict(typed)
    for name in decimal_names:
        values[name] = _decimal(name, values[name])
    for name in (
        "snapshot_time_ms",
        "instrument_id",
        "source_symbol_id",
        "launch_time_ms",
    ):
        values[name] = _integer(name, values[name])
    values["delivery_time_ms"] = _integer(
        "delivery_time_ms", values["delivery_time_ms"], allow_none=True
    )
    values["funding_interval_minutes"] = _integer(
        "funding_interval_minutes", values["funding_interval_minutes"], allow_none=True
    )
    try:
        snapshot = InstrumentSnapshot(**values)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise InstrumentRegistryError("registry record violates v1 logical fields") from error
    if (
        snapshot.category != "linear"
        or snapshot.instrument_id != snapshot.source_symbol_id
        or not 1 <= snapshot.instrument_id <= UINT32_MAX
    ):
        raise InstrumentRegistryError("registry record violates the v1 identity algorithm")
    return snapshot


def load_verified_instrument_registry(path: Path) -> VerifiedInstrumentRegistry:
    """Verify the evidence receipt, embedded hash, identity policy, rows, and summary."""

    resolved = path.resolve()
    if not verify_evidence(resolved):
        raise InstrumentRegistryError(f"instrument registry receipt does not verify: {resolved}")
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InstrumentRegistryError("instrument registry is not valid JSON") from error
    if not isinstance(raw, dict) or raw.get("evidence_schema") != INSTRUMENT_REGISTRY_CONTRACT:
        raise InstrumentRegistryError("unsupported instrument registry contract")
    payload = cast(dict[str, object], raw)
    embedded_hash = payload.get("content_sha256")
    hash_input = dict(payload)
    hash_input.pop("content_sha256", None)
    if embedded_hash != canonical_sha256(hash_input):
        raise InstrumentRegistryError("instrument registry embedded hash does not verify")
    if payload.get("identity_policy") != {
        "algorithm": IDENTITY_ALGORITHM,
        "category": "linear",
        "instrument_id_expression": "source_symbol_id",
        "range": "uint32-positive",
    }:
        raise InstrumentRegistryError("instrument registry identity policy does not match v1")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise InstrumentRegistryError("instrument registry has no records")
    snapshots = tuple(_snapshot_from_registry(item) for item in raw_records)
    identities = [item.instrument_id for item in snapshots]
    symbols = [item.symbol for item in snapshots]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise InstrumentRegistryError("instrument registry identities are not sorted and unique")
    if len(symbols) != len(set(symbols)):
        raise InstrumentRegistryError("instrument registry symbols are not unique")
    eligible_count = sum(
        item.contract_type == "LinearPerpetual"
        and item.quote_coin == "USDT"
        and item.settle_coin == "USDT"
        for item in snapshots
    )
    if payload.get("summary") != {
        "instrument_count": len(snapshots),
        "maximum_instrument_id": max(identities),
        "minimum_instrument_id": min(identities),
        "usdt_linear_perpetual_count": eligible_count,
    }:
        raise InstrumentRegistryError("instrument registry summary does not verify")
    source = payload.get("source_inventory")
    if not isinstance(source, dict) or any(
        not isinstance(source.get(name), str) or not SHA256_RE.fullmatch(source[name])
        for name in ("artifact_sha256", "content_sha256")
    ):
        raise InstrumentRegistryError("instrument registry source binding is invalid")
    return VerifiedInstrumentRegistry(
        path=resolved,
        artifact_sha256=sha256_file(resolved),
        payload=payload,
        snapshots=snapshots,
    )


def build_verified_registry_from_inventory(path: Path) -> dict[str, object]:
    """Load a receipted public inventory and build its deterministic registry payload."""

    resolved = path.resolve()
    inventory = load_verified_public_inventory(resolved)
    return build_instrument_registry(
        inventory,
        inventory_artifact_sha256=sha256_file(resolved),
    )
