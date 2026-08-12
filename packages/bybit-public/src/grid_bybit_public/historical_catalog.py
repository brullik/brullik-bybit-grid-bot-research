"""Read-only client for Bybit's public Historical Market Data product catalog."""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

CATALOG_ENDPOINT = "https://api2.bybit.com/quote/public/support/download/list-products"
PRODUCT_ID_RE = re.compile(r"^[a-z0-9_]+$")
KNOWN_BUSINESS_TYPES = frozenset({"contract", "option", "spot"})


class HistoricalCatalogError(RuntimeError):
    """The public Historical Market Data catalog is missing or malformed."""


@dataclass(frozen=True, slots=True)
class HistoricalDataProduct:
    product_id: str
    name: str
    description: str
    category: str
    business_types: tuple[str, ...]
    intervals: tuple[str, ...]
    period_count: int


class BybitHistoricalDataCatalog:
    """Fetch exactly one allowlisted, unauthenticated Bybit catalog endpoint."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        fetch_json: Callable[[str], Mapping[str, Any]] | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("catalog timeout must be positive")
        self._timeout_seconds = timeout_seconds
        self._fetch_json = fetch_json or self._urllib_fetch

    def products(self) -> tuple[HistoricalDataProduct, ...]:
        payload = self._fetch_json(CATALOG_ENDPOINT)
        if payload.get("ret_code") != 0:
            raise HistoricalCatalogError(
                f"Bybit historical catalog ret_code={payload.get('ret_code')!r}"
            )
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise HistoricalCatalogError("historical catalog result must be an object")
        raw_products = result.get("products")
        if not isinstance(raw_products, list) or not raw_products:
            raise HistoricalCatalogError("historical catalog products must be a non-empty array")

        products = tuple(self._product(item) for item in raw_products)
        product_ids = [product.product_id for product in products]
        if len(product_ids) != len(set(product_ids)):
            raise HistoricalCatalogError("historical catalog contains duplicate product IDs")
        return tuple(sorted(products, key=lambda product: product.product_id))

    @staticmethod
    def _product(raw: Any) -> HistoricalDataProduct:
        if not isinstance(raw, Mapping):
            raise HistoricalCatalogError("historical catalog product must be an object")
        product_id = _required_text(raw, "id")
        category = _required_text(raw, "category")
        if not PRODUCT_ID_RE.fullmatch(product_id) or not PRODUCT_ID_RE.fullmatch(category):
            raise HistoricalCatalogError("historical catalog IDs must be lowercase tokens")

        raw_business_types = _required_text(raw, "bizTypes").split(",")
        business_types = tuple(sorted(set(raw_business_types)))
        if any(
            not value or value not in KNOWN_BUSINESS_TYPES for value in raw_business_types
        ) or len(business_types) != len(raw_business_types):
            raise HistoricalCatalogError("historical catalog business types are invalid")

        raw_intervals = raw.get("intervals")
        if not isinstance(raw_intervals, str):
            raise HistoricalCatalogError("historical catalog intervals must be text")
        intervals = tuple(value for value in raw_intervals.split(",") if value)
        if len(intervals) != len(set(intervals)):
            raise HistoricalCatalogError("historical catalog intervals must be unique")

        periods = raw.get("periods")
        if not isinstance(periods, list):
            raise HistoricalCatalogError("historical catalog periods must be an array")
        return HistoricalDataProduct(
            product_id=product_id,
            name=_required_text(raw, "productName"),
            description=_required_text(raw, "productDesc"),
            category=category,
            business_types=business_types,
            intervals=intervals,
            period_count=len(periods),
        )

    def _urllib_fetch(self, url: str) -> Mapping[str, Any]:
        if url != CATALOG_ENDPOINT:
            raise HistoricalCatalogError("refusing a non-allowlisted historical catalog URL")
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "brullik-grid-data/0.2",
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                final_url = urllib.parse.urlparse(response.geturl())
                if (
                    final_url.scheme != "https"
                    or final_url.netloc != "api2.bybit.com"
                    or final_url.path != "/quote/public/support/download/list-products"
                ):
                    raise HistoricalCatalogError(
                        "historical catalog redirected outside its allowlisted endpoint"
                    )
                payload = json.load(response)
        except HistoricalCatalogError:
            raise
        except Exception as error:
            raise HistoricalCatalogError("failed to read Bybit historical catalog") from error
        if not isinstance(payload, Mapping):
            raise HistoricalCatalogError("historical catalog response root must be an object")
        return payload


def _required_text(item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        raise HistoricalCatalogError(f"historical catalog field {key!r} must be non-empty text")
    return value
