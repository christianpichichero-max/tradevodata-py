"""Audit a fundamentals CSV for point-in-time evidence and silent restatements.

The file stays local. This script compares overlapping rows with Tradevo Data's free CC0
sample and checks whether the provider exposes a real availability/filing timestamp.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import statistics
from pathlib import Path
from typing import Any

import tradevodata as tv


ALIASES = {
    "revenue": "Revenue",
    "revenues": "Revenue",
    "netincome": "NetIncome",
    "net_income": "NetIncome",
    "assets": "Assets",
    "stockholdersequity": "StockholdersEquity",
    "stockholders_equity": "StockholdersEquity",
    "equity": "StockholdersEquity",
    "operatingcashflow": "OperatingCashFlow",
    "operating_cash_flow": "OperatingCashFlow",
    "epsdiluted": "EPSDiluted",
    "diluted_eps": "EPSDiluted",
    "dilutedshares": "DilutedShares",
    "diluted_shares": "DilutedShares",
}


def concept_name(value: str) -> str:
    compact = value.strip().replace(" ", "").replace("-", "").lower()
    return ALIASES.get(compact, value.strip())


def day(value: Any) -> str:
    return str(value or "").strip()[:10]


def number(value: Any) -> float | None:
    try:
        parsed = float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def close(left: float, right: float, tolerance: float) -> bool:
    return math.isclose(left, right, rel_tol=tolerance, abs_tol=1e-9)


def parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(day(value))
    except ValueError:
        return None


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def require_columns(fieldnames: list[str], columns: list[str]) -> None:
    missing = [column for column in columns if column not in fieldnames]
    if missing:
        raise SystemExit(f"Missing column(s): {', '.join(missing)}")


def audit(args: argparse.Namespace) -> int:
    with Path(args.csv).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        required = [args.ticker_col, args.concept_col, args.period_end_col, args.value_col]
        require_columns(fields, required)
        if args.available_col:
            require_columns(fields, [args.available_col])
        if args.reliable_col:
            require_columns(fields, [args.reliable_col])
        provider = list(reader)

    sample = tv.sample(to_pandas=False)
    sample_index = {
        (str(row["ticker"]).upper(), str(row["concept"]), day(row["period_end"])): row
        for row in sample
    }

    overlap = 0
    restated_overlap = 0
    matches_original = 0
    matches_latest_only = 0
    matches_neither = 0
    invalid_values = 0
    lags: list[int] = []
    negative_lags = 0
    invalid_dates = 0
    skipped_unreliable = 0

    for row in provider:
        key = (
            str(row[args.ticker_col]).strip().upper(),
            concept_name(str(row[args.concept_col])),
            day(row[args.period_end_col]),
        )
        reference = sample_index.get(key)
        provider_value = number(row[args.value_col])
        if provider_value is None:
            invalid_values += 1
        if reference is not None and provider_value is not None:
            overlap += 1
            original = float(reference["original_value"])
            latest = float(reference["latest_value"])
            if truthy(reference.get("restated")):
                restated_overlap += 1
                if close(provider_value, original, args.tolerance):
                    matches_original += 1
                elif close(provider_value, latest, args.tolerance):
                    matches_latest_only += 1
                else:
                    matches_neither += 1

        if args.available_col:
            if args.reliable_col and not truthy(row[args.reliable_col]):
                skipped_unreliable += 1
                continue
            period_end = parse_date(row[args.period_end_col])
            available = parse_date(row[args.available_col])
            if period_end is None or available is None:
                invalid_dates += 1
            else:
                lag = (available - period_end).days
                lags.append(lag)
                if lag < 0:
                    negative_lags += 1

    print("Point-in-time provider audit")
    print(f"  Provider rows: {len(provider):,}")
    print(f"  Rows overlapping the 40-company sample: {overlap:,}")
    if invalid_values:
        print(f"  Rows with an unreadable value: {invalid_values:,}")

    print("\nAvailability-date check")
    status = 0
    if not args.available_col:
        print("  UNVERIFIED: no availability/filing-date column was supplied.")
        print("  A period-end date cannot prove when a value became public.")
        status = 1
    elif not lags:
        print("  FAILED: no valid period-end/availability-date pairs were found.")
        status = 1
    else:
        positive = sum(lag > 0 for lag in lags)
        print(f"  Valid timestamp pairs: {len(lags):,}")
        print(f"  Values published after period end: {positive:,} ({positive / len(lags):.0%})")
        print(
            f"  Filing lag: mean {statistics.mean(lags):.1f} days; "
            f"median {statistics.median(lags):.1f}; max {max(lags)}"
        )
        if invalid_dates:
            print(f"  Invalid date pairs: {invalid_dates:,}")
        if skipped_unreliable:
            print(f"  Rows excluded by {args.reliable_col}: {skipped_unreliable:,}")
        if negative_lags:
            print(f"  WARNING: {negative_lags:,} values appear available before period end.")
            status = 1

    print("\nRestatement check")
    if restated_overlap == 0:
        print("  INCONCLUSIVE: no materially restated sample rows overlap this file.")
    else:
        print(f"  Restated overlapping rows: {restated_overlap:,}")
        print(f"  Match first-reported value: {matches_original:,}")
        print(f"  Match current revised value only: {matches_latest_only:,}")
        print(f"  Match neither within tolerance: {matches_neither:,}")
        if matches_latest_only:
            print("  WARNING: revised values may be overwriting what was originally known.")
            status = 1

    print("\nInterpretation")
    if status == 0:
        print("  No point-in-time red flag was found in the checks this file supports.")
        print("  This is evidence, not a certification; inspect source methodology too.")
    else:
        print("  This file cannot yet be treated as lookahead-safe without further evidence.")
    return status


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("csv", help="Provider CSV to audit; it never leaves this machine")
    result.add_argument("--ticker-col", default="ticker")
    result.add_argument("--concept-col", default="concept")
    result.add_argument("--period-end-col", default="period_end")
    result.add_argument("--value-col", default="value")
    result.add_argument(
        "--available-col",
        help="Column containing the date the value became public, such as filed or accepted",
    )
    result.add_argument(
        "--reliable-col",
        help="Optional boolean column; exclude rows marked false from filing-lag statistics",
    )
    result.add_argument(
        "--tolerance",
        type=float,
        default=0.005,
        help="Relative value-match tolerance (default: 0.005, or 0.5%%)",
    )
    return result


if __name__ == "__main__":
    raise SystemExit(audit(parser().parse_args()))
