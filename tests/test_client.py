"""Tests that need no network and no API key."""

import pytest

import tradevodata as tv
from tradevodata.client import _check_as_of


class TestAsOfIsRequired:
    """The library's core promise: you cannot query without saying when."""

    def test_rejects_missing_dashes(self):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            _check_as_of("20240630")

    def test_rejects_non_string(self):
        with pytest.raises(ValueError):
            _check_as_of(20240630)  # type: ignore[arg-type]

    def test_accepts_iso_date(self):
        assert _check_as_of("2024-06-30") == "2024-06-30"

    def test_fundamentals_signature_has_no_as_of_default(self):
        import inspect

        sig = inspect.signature(tv.Client.fundamentals)
        assert sig.parameters["as_of"].default is inspect.Parameter.empty


class TestAuth:
    def test_no_key_raises_auth_error_pointing_at_the_free_sample(self):
        client = tv.Client(api_key=None)
        client.api_key = None  # ignore any ambient env var
        with pytest.raises(tv.AuthError, match="sample"):
            client.fundamentals("AAPL", as_of="2024-06-30")

    def test_env_var_is_picked_up(self, monkeypatch):
        monkeypatch.setenv("TRADEVODATA_API_KEY", "tvd_from_env")
        assert tv.Client().api_key == "tvd_from_env"


class TestConceptValidation:
    def test_unknown_concept_rejected_before_any_request(self):
        client = tv.Client(api_key="tvd_x")
        with pytest.raises(ValueError, match="concept must be one of"):
            client.fundamentals("AAPL", as_of="2024-06-30", concept="Ebitda")


class TestAsOfFilter:
    ROWS = [
        # AAPL FY2023 was filed 2023-11-03; FY2024 not until 2024-11-01.
        {"ticker": "AAPL", "concept": "Revenue", "period_end": "2023-09-30",
         "first_filed": "2023-11-03", "original_value": 383285000000},
        {"ticker": "AAPL", "concept": "Revenue", "period_end": "2024-09-28",
         "first_filed": "2024-11-01", "original_value": 391035000000},
    ]

    def test_excludes_values_not_yet_public(self):
        out = tv.as_of_filter(self.ROWS, as_of="2024-06-30")
        assert len(out) == 1
        assert out[0]["period_end"] == "2023-09-30"

    def test_includes_on_the_filing_day_itself(self):
        out = tv.as_of_filter(self.ROWS, as_of="2024-11-01")
        assert out[0]["period_end"] == "2024-09-28"

    def test_day_before_filing_still_sees_the_older_year(self):
        out = tv.as_of_filter(self.ROWS, as_of="2024-10-31")
        assert out[0]["period_end"] == "2023-09-30"

    def test_before_any_filing_returns_nothing(self):
        assert tv.as_of_filter(self.ROWS, as_of="2020-01-01") == []

    def test_rejects_bad_as_of(self):
        with pytest.raises(ValueError):
            tv.as_of_filter(self.ROWS, as_of="not-a-date")
