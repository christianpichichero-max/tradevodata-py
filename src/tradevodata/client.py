"""Client for the Tradevo Data point-in-time fundamentals API.

The one design rule here: ``as_of`` is a required argument on every query that returns
values. You cannot ask this library "what is Apple's revenue?" — only "what was Apple's
revenue *knowable on this date?*". That is the whole point of point-in-time data, and making
it a keyword with a default is how lookahead bias gets written by accident.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import warnings
from dataclasses import dataclass
from typing import Any, Iterable

__all__ = ["Client", "sample", "TradevoDataError", "AuthError", "QuotaError", "NotFoundError"]

BASE_URL = "https://tradevodata.com"
SAMPLE_URL = (
    "https://raw.githubusercontent.com/christianpichichero-max/"
    "pit-fundamentals/main/data/pit_fundamentals_history.csv"
)
CONCEPTS = (
    "Revenue",
    "NetIncome",
    "Assets",
    "StockholdersEquity",
    "OperatingCashFlow",
    "EPSDiluted",
    "DilutedShares",
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TradevoDataError(RuntimeError):
    """Base error for this client."""


class AuthError(TradevoDataError):
    """Missing, invalid, or deactivated API key."""


class QuotaError(TradevoDataError):
    """Daily request or download quota exhausted. Carries ``retry_after`` seconds."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NotFoundError(TradevoDataError):
    """Ticker is not in the universe."""


def _check_as_of(as_of: str) -> str:
    if not isinstance(as_of, str) or not _DATE_RE.match(as_of):
        raise ValueError(
            f"as_of must be a YYYY-MM-DD string, got {as_of!r}. It is required on purpose: "
            "every value this API returns is scoped to what was public on that date."
        )
    return as_of


def _has_pandas() -> bool:
    try:
        import pandas  # noqa: F401
        return True
    except ImportError:
        return False


def _shape(rows: Iterable[dict[str, Any]], to_pandas: bool | None):
    """Return a DataFrame when pandas is available, else the plain list of dicts.

    to_pandas=None (the default) means "use pandas if it is installed". This package
    advertises zero dependencies, so the documented first line has to work on a bare
    install — defaulting to True made `tv.sample()` raise ImportError there.
    Passing to_pandas=True explicitly still raises if pandas is genuinely missing, because
    at that point the caller has asked for something we cannot deliver.
    """
    rows = list(rows)
    if to_pandas is False:
        return rows
    if not _has_pandas():
        if to_pandas is True:
            raise ImportError(
                "pandas was requested but is not installed. "
                'Install it with: pip install "tradevodata[pandas]"'
            )
        return rows
    import pandas as pd
    return pd.DataFrame(rows)


@dataclass
class Client:
    """Talks to the Tradevo Data API.

    The key is read from ``TRADEVODATA_API_KEY`` when not passed explicitly. You do not need
    one to use :func:`sample`.
    """

    api_key: str | None = None
    base_url: str = BASE_URL
    timeout: int = 60
    warn_on_flags: bool = True

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("TRADEVODATA_API_KEY")
        self.base_url = self.base_url.rstrip("/")

    # ------------------------------------------------------------------ internals

    def _request(self, path: str, params: dict[str, str] | None = None) -> tuple[Any, dict]:
        if not self.api_key:
            raise AuthError(
                "No API key. Pass Client(api_key=...) or set TRADEVODATA_API_KEY. "
                "The free 40-company sample needs no key — use tradevodata.sample()."
            )
        url = f"{self.base_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={"x-api-key": self.api_key, "accept": "application/json",
                     "user-agent": "tradevodata-python"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8")), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            try:
                message = json.loads(body).get("error", body)
            except json.JSONDecodeError:
                message = body or exc.reason
            if exc.code in (401, 403):
                raise AuthError(message) from None
            if exc.code == 404:
                raise NotFoundError(message) from None
            if exc.code == 429:
                retry = exc.headers.get("retry-after")
                raise QuotaError(message, int(retry) if retry and retry.isdigit() else None) from None
            raise TradevoDataError(f"HTTP {exc.code}: {message}") from None
        except urllib.error.URLError as exc:
            raise TradevoDataError(f"Could not reach {self.base_url}: {exc.reason}") from None

    def _warn(self, payload: dict) -> None:
        """Surface the API's own honesty signals instead of letting them pass silently."""
        if not self.warn_on_flags:
            return
        if payload.get("coverage_warning"):
            warnings.warn(payload["coverage_warning"], stacklevel=3)
        rows = payload.get("fundamentals") or payload.get("rows") or []
        flagged = [r for r in rows if (r.get("qa_status") or "clean") != "clean"]
        if flagged:
            reasons = sorted({f for r in flagged
                              for f in r["qa_status"].removeprefix("FLAG:").split(";")})
            warnings.warn(
                f"{len(flagged)} of {len(rows)} rows carry a QA flag ({', '.join(reasons)}). "
                "Rows are flagged, never silently dropped — inspect qa_status before relying "
                "on them.",
                stacklevel=3,
            )

    # -------------------------------------------------------------------- public

    def fundamentals(
        self,
        ticker: str,
        as_of: str,
        concept: str | None = None,
        to_pandas: bool | None = False,
    ):
        """Latest values for ``ticker`` that were already public on ``as_of``.

        ``as_of`` is required: this returns what was knowable that day, not today's numbers.
        """
        _check_as_of(as_of)
        if concept is not None and concept not in CONCEPTS:
            raise ValueError(f"concept must be one of {CONCEPTS}, got {concept!r}")
        params = {"ticker": ticker.upper(), "as_of": as_of}
        if concept:
            params["concept"] = concept
        payload, _ = self._request("/v1/fundamentals", params)
        self._warn(payload)
        return _shape(payload["fundamentals"], to_pandas) if to_pandas is not False else payload

    def snapshot(self, as_of: str, concept: str | None = None, to_pandas: bool | None = False):
        """The whole-universe cross-section as it stood on ``as_of``.

        One call per rebalance date — the shape a cross-sectional backtest actually wants.
        """
        _check_as_of(as_of)
        if concept is not None and concept not in CONCEPTS:
            raise ValueError(f"concept must be one of {CONCEPTS}, got {concept!r}")
        params = {"as_of": as_of}
        if concept:
            params["concept"] = concept
        payload, _ = self._request("/v1/snapshot", params)
        self._warn(payload)
        return _shape(payload["rows"], to_pandas) if to_pandas is not False else payload

    def download(self, path: str | None = None, to_pandas: bool | None = False):
        """The entire dataset as one gzipped CSV.

        Writes to ``path`` if given. Capped at a few downloads per key per day, so cache it.
        """
        if not self.api_key:
            raise AuthError("No API key. Set TRADEVODATA_API_KEY or pass Client(api_key=...).")
        req = urllib.request.Request(
            f"{self.base_url}/v1/download",
            headers={"x-api-key": self.api_key, "user-agent": "tradevodata-python"},
        )
        try:
            with urllib.request.urlopen(req, timeout=max(self.timeout, 300)) as resp:
                blob = resp.read()
                meta = dict(resp.headers)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            if exc.code == 429:
                raise QuotaError(body) from None
            if exc.code in (401, 403):
                raise AuthError(body) from None
            raise TradevoDataError(f"HTTP {exc.code}: {body}") from None
        if path:
            with open(path, "wb") as fh:
                fh.write(blob)
            return {"path": path, "bytes": len(blob),
                    "rows": meta.get("x-dataset-rows"), "sha256": meta.get("x-dataset-sha256")}
        text = gzip.decompress(blob).decode("utf-8")
        rows = list(csv.DictReader(io.StringIO(text)))
        return _shape(rows, to_pandas)

    def health(self) -> dict:
        """Dataset liveness: row count and database reachability."""
        req = urllib.request.Request(f"{self.base_url}/v1/health",
                                     headers={"user-agent": "tradevodata-python"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))


def sample(to_pandas: bool | None = None):
    """The free 40-company CC0 sample. No API key, no signup.

    Same columns and same point-in-time semantics as the paid dataset, so you can write and
    verify your join logic before paying for anything.
    """
    req = urllib.request.Request(SAMPLE_URL, headers={"user-agent": "tradevodata-python"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode("utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    for r in rows:
        for key in ("original_value", "latest_value"):
            if r.get(key):
                try:
                    r[key] = float(r[key])
                except ValueError:
                    pass
        for key in ("fiscal_year", "lag_days"):
            if r.get(key):
                try:
                    r[key] = int(r[key])
                except ValueError:
                    pass
        r["restated"] = str(r.get("restated", "")).lower() == "true"
        r["filed_reliable"] = str(r.get("filed_reliable", "")).lower() == "true"
    return _shape(rows, to_pandas)


def as_of_filter(rows, as_of: str):
    """Keep only rows that were already public on ``as_of``, newest period per concept.

    Useful when working from :func:`sample` or a bulk download, where the point-in-time join
    is yours to do. Accepts a list of dicts or a pandas DataFrame and returns the same type.
    """
    _check_as_of(as_of)
    is_df = hasattr(rows, "to_dict") and hasattr(rows, "columns")
    records = rows.to_dict("records") if is_df else list(rows)
    knowable = [r for r in records if str(r.get("first_filed", "")) <= as_of]
    best: dict[tuple, dict] = {}
    for r in knowable:
        key = (r.get("ticker"), r.get("concept"))
        cur = best.get(key)
        if cur is None or str(r.get("period_end", "")) > str(cur.get("period_end", "")):
            best[key] = r
    out = sorted(best.values(), key=lambda r: (str(r.get("ticker")), str(r.get("concept"))))
    return _shape(out, True) if is_df else out
