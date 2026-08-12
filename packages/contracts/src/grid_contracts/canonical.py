"""Canonical serialization and hashing for immutable evidence.

Binary floating-point values are deliberately rejected. Persisted values that can
affect execution or hashing must cross this boundary as Decimal or canonical text.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a value has no supported canonical representation."""


def decimal_text(value: Decimal) -> str:
    """Return a non-exponent, representation-independent decimal string."""

    if not value.is_finite():
        raise CanonicalizationError("non-finite Decimal values are forbidden")
    if value == 0:
        return "0"
    text = format(value.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def canonical_value(value: Any) -> Any:
    """Convert a supported object into JSON-compatible canonical primitives."""

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return canonical_value(dataclasses.asdict(value))
    if isinstance(value, Enum):
        return canonical_value(value.value)
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalizationError("naive datetimes are forbidden")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, float):
        raise CanonicalizationError("binary floating-point values are forbidden")
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError("canonical mapping keys must be strings")
            result[key] = canonical_value(item)
        return result
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray | str):
        return [canonical_value(item) for item in value]
    raise CanonicalizationError(f"unsupported canonical type: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize a value as deterministic UTF-8 JSON without insignificant space."""

    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
