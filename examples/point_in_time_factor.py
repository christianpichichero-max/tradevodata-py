"""Build a cross-sectional factor snapshot using only values public by an as-of date."""

from __future__ import annotations

import argparse

import tradevodata as tv


def main(as_of: str, limit: int) -> None:
    try:
        import pandas as pd  # noqa: F401
    except ImportError as exc:
        raise SystemExit('Install pandas first: pip install "tradevodata[pandas]"') from exc

    sample = tv.sample(to_pandas=True)
    known = tv.as_of_filter(sample, as_of=as_of)
    if known.empty:
        raise SystemExit(f"No sample fundamentals were public by {as_of}.")

    values = known.pivot(index="ticker", columns="concept", values="original_value")
    required = ["Revenue", "NetIncome", "Assets", "StockholdersEquity", "OperatingCashFlow"]
    missing = [column for column in required if column not in values.columns]
    if missing:
        raise SystemExit(f"Sample is missing required concept(s): {', '.join(missing)}")

    factors = values.copy()
    factors.columns.name = None
    factors["net_margin"] = factors["NetIncome"] / factors["Revenue"]
    factors["cash_margin"] = factors["OperatingCashFlow"] / factors["Revenue"]
    factors["return_on_assets"] = factors["NetIncome"] / factors["Assets"]
    factors["return_on_equity"] = factors["NetIncome"] / factors["StockholdersEquity"]

    score_columns = ["net_margin", "cash_margin", "return_on_assets", "return_on_equity"]
    ranks = factors[score_columns].rank(pct=True)
    factors["quality_score"] = ranks.mean(axis=1)

    shown = factors.sort_values("quality_score", ascending=False).head(limit)
    percent_columns = score_columns + ["quality_score"]
    print(f"\nPoint-in-time quality snapshot as of {as_of}")
    print(f"Using {len(known):,} filed values across {known['ticker'].nunique()} sample companies.\n")
    print(shown[percent_columns].map(lambda value: f"{value:.1%}" if value == value else "—").to_string())
    print("\nEducational example only; this is not an investment recommendation or a return backtest.")


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--as-of", default="2024-06-30")
    argument_parser.add_argument("--limit", type=int, default=10)
    parsed = argument_parser.parse_args()
    main(parsed.as_of, parsed.limit)
