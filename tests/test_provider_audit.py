"""Tests for the shareable provider-audit example."""

import argparse
import csv

from examples import audit_provider_csv as provider_audit


SAMPLE_ROW = {
    "ticker": "AAPL",
    "concept": "Revenue",
    "period_end": "2023-09-30",
    "first_filed": "2023-11-03",
    "original_value": 100.0,
    "latest_value": 120.0,
    "restated": True,
}


def arguments(path, **overrides):
    values = {
        "csv": str(path),
        "ticker_col": "ticker",
        "concept_col": "concept",
        "period_end_col": "period_end",
        "value_col": "value",
        "available_col": "filed",
        "reliable_col": None,
        "tolerance": 0.005,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def write_provider(path, value):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["ticker", "concept", "period_end", "filed", "value"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "ticker": "AAPL",
                "concept": "revenue",
                "period_end": "2023-09-30",
                "filed": "2023-11-03",
                "value": value,
            }
        )


def test_provider_using_first_reported_value_passes(tmp_path, monkeypatch):
    provider = tmp_path / "provider.csv"
    write_provider(provider, 100)
    monkeypatch.setattr(provider_audit.tv, "sample", lambda to_pandas=False: [SAMPLE_ROW])

    assert provider_audit.audit(arguments(provider)) == 0


def test_provider_using_revised_value_only_is_flagged(tmp_path, monkeypatch):
    provider = tmp_path / "provider.csv"
    write_provider(provider, 120)
    monkeypatch.setattr(provider_audit.tv, "sample", lambda to_pandas=False: [SAMPLE_ROW])

    assert provider_audit.audit(arguments(provider)) == 1


def test_missing_availability_column_is_unverified(tmp_path, monkeypatch):
    provider = tmp_path / "provider.csv"
    write_provider(provider, 100)
    monkeypatch.setattr(provider_audit.tv, "sample", lambda to_pandas=False: [SAMPLE_ROW])

    assert provider_audit.audit(arguments(provider, available_col=None)) == 1


def test_value_tolerance_is_relative_not_one_whole_unit():
    assert provider_audit.close(100.4, 100.0, tolerance=0.005)
    assert not provider_audit.close(6.9, 6.0, tolerance=0.005)
