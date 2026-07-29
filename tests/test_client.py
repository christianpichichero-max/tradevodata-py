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


class TestDateRepresentationAgnostic:
    """A parsed date and a string date must produce the SAME point-in-time answer.

    Before this, sample() handed back strings while a pandas user would naturally parse them,
    and as_of_filter compared raw values — so the two callers could get fiscal years a full
    year apart from identical data. A silent off-by-one in a PIT join is precisely the bug
    this library exists to prevent, so it is worth a test of its own.
    """

    import datetime as _dt

    STR_ROWS = [
        {"ticker": "AAPL", "concept": "Revenue", "period_end": "2023-09-30",
         "first_filed": "2023-11-03", "original_value": 383285000000},
        {"ticker": "AAPL", "concept": "Revenue", "period_end": "2024-09-28",
         "first_filed": "2024-11-01", "original_value": 391035000000},
    ]
    DATE_ROWS = [
        {"ticker": "AAPL", "concept": "Revenue", "period_end": _dt.date(2023, 9, 30),
         "first_filed": _dt.date(2023, 11, 3), "original_value": 383285000000},
        {"ticker": "AAPL", "concept": "Revenue", "period_end": _dt.date(2024, 9, 28),
         "first_filed": _dt.date(2024, 11, 1), "original_value": 391035000000},
    ]

    def test_strings_and_dates_agree(self):
        a = tv.as_of_filter(self.STR_ROWS, as_of="2024-06-30")
        b = tv.as_of_filter(self.DATE_ROWS, as_of="2024-06-30")
        assert len(a) == len(b) == 1
        assert a[0]["original_value"] == b[0]["original_value"] == 383285000000

    def test_datetimes_respect_the_filing_boundary(self):
        import datetime as dt
        rows = [{**r, "first_filed": dt.datetime.combine(r["first_filed"], dt.time(0)),
                 "period_end": dt.datetime.combine(r["period_end"], dt.time(0))}
                for r in self.DATE_ROWS]
        assert tv.as_of_filter(rows, as_of="2024-10-31")[0]["original_value"] == 383285000000
        assert tv.as_of_filter(rows, as_of="2024-11-01")[0]["original_value"] == 391035000000


class TestCredentialSafety:
    def test_repr_does_not_leak_the_key(self):
        c = tv.Client(api_key="tvd_supersecret_value_abcdef123456")
        assert "supersecret" not in repr(c)
        assert "tvd_supe" in repr(c)  # enough to identify which key, not enough to use it

    def test_str_does_not_leak_the_key(self):
        c = tv.Client(api_key="tvd_supersecret_value_abcdef123456")
        assert "supersecret" not in str(c)


class TestCsvCoercion:
    """'False' is a truthy string. Left uncoerced, every row reads as restated."""

    def test_booleans_become_real_booleans(self):
        from tradevodata.client import _coerce
        r = _coerce({"restated": "False", "filed_reliable": "True"})
        assert r["restated"] is False
        assert r["filed_reliable"] is True

    def test_numbers_become_numbers(self):
        from tradevodata.client import _coerce
        r = _coerce({"original_value": "383285000000", "fiscal_year": "2023", "lag_days": "34"})
        assert r["original_value"] == 383285000000.0
        assert r["fiscal_year"] == 2023 and r["lag_days"] == 34

    def test_blanks_survive_untouched(self):
        from tradevodata.client import _coerce
        r = _coerce({"original_value": "", "lag_days": ""})
        assert r["original_value"] == "" and r["lag_days"] == ""
