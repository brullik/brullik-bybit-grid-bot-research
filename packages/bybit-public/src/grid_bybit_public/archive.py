"""Read-only inventory of the official public.bybit.com archive indexes."""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from html.parser import HTMLParser

SYMBOL_RE = re.compile(r"^[A-Z0-9_-]+$")
DIRECTORY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ArchiveIndexError(RuntimeError):
    pass


class ArchivePathNotFound(ArchiveIndexError):
    pass


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        for key, value in attrs:
            if key == "href" and value:
                self.hrefs.append(value)


def parse_directory_links(html: str) -> tuple[str, ...]:
    parser = _Links()
    parser.feed(html)
    return tuple(parser.hrefs)


@dataclass(frozen=True, slots=True)
class TradeArchiveCoverage:
    symbol: str
    first_date: str | None
    last_date: str | None
    file_count: int
    missing_dates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProductIndexSummary:
    product: str
    child_link_count: int
    trailing_slash_child_count: int
    sample_links: tuple[str, ...]


def summarize_trade_files(symbol: str, links: Iterable[str]) -> TradeArchiveCoverage:
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError("invalid Bybit archive symbol")
    pattern = re.compile(rf"^{re.escape(symbol)}(\d{{4}}-\d{{2}}-\d{{2}})\.csv\.gz$")
    dates = sorted(
        {
            date.fromisoformat(match.group(1))
            for link in links
            if (match := pattern.fullmatch(urllib.parse.unquote(link).rsplit("/", 1)[-1]))
        }
    )
    if not dates:
        return TradeArchiveCoverage(symbol, None, None, 0, ())
    actual = set(dates)
    missing: list[str] = []
    current = dates[0]
    while current <= dates[-1]:
        if current not in actual:
            missing.append(current.isoformat())
        current += timedelta(days=1)
    return TradeArchiveCoverage(
        symbol=symbol,
        first_date=dates[0].isoformat(),
        last_date=dates[-1].isoformat(),
        file_count=len(dates),
        missing_dates=tuple(missing),
    )


class BybitArchiveIndex:
    def __init__(
        self,
        *,
        base_url: str = "https://public.bybit.com",
        timeout_seconds: float = 30.0,
        fetch_text: Callable[[str], str] | None = None,
    ) -> None:
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme != "https" or parsed.netloc != "public.bybit.com":
            raise ValueError("archive base URL must be https://public.bybit.com")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._fetch_text = fetch_text or self._urllib_fetch

    def products(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                product
                for link in self._links("/")
                if link.endswith("/") and DIRECTORY_RE.fullmatch(product := link.removesuffix("/"))
            )
        )

    def product_summary(self, product: str, *, sample_limit: int = 20) -> ProductIndexSummary:
        if not DIRECTORY_RE.fullmatch(product):
            raise ValueError("invalid Bybit archive product")
        if not 1 <= sample_limit <= 100:
            raise ValueError("sample_limit must be between 1 and 100")
        links = tuple(
            sorted(
                urllib.parse.unquote(link).rsplit("/", 1)[-1] or urllib.parse.unquote(link)
                for link in self._links(f"/{product}/")
                if link not in ("../", "/")
            )
        )
        return ProductIndexSummary(
            product=product,
            child_link_count=len(links),
            trailing_slash_child_count=sum(link.endswith("/") for link in links),
            sample_links=links[:sample_limit],
        )

    def trading_symbols(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                link.removesuffix("/")
                for link in self._links("/trading/")
                if link.endswith("/") and SYMBOL_RE.fullmatch(link.removesuffix("/"))
            )
        )

    def trade_coverage(self, symbol: str) -> TradeArchiveCoverage:
        if not SYMBOL_RE.fullmatch(symbol):
            raise ValueError("invalid Bybit archive symbol")
        return summarize_trade_files(symbol, self._links(f"/trading/{symbol}/"))

    def _links(self, path: str) -> tuple[str, ...]:
        try:
            return parse_directory_links(self._fetch_text(f"{self._base_url}{path}"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise ArchivePathNotFound(f"Bybit archive path does not exist: {path}") from error
            raise ArchiveIndexError(f"failed to read Bybit archive index {path}") from error
        except Exception as error:
            raise ArchiveIndexError(f"failed to read Bybit archive index {path}") from error

    def _urllib_fetch(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={"Accept": "text/html", "User-Agent": "brullik-grid-data/0.2"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            if response.geturl().split("/", 3)[:3] != ["https:", "", "public.bybit.com"]:
                raise ArchiveIndexError("archive request redirected outside public.bybit.com")
            body: bytes = response.read()
            return body.decode("utf-8")
