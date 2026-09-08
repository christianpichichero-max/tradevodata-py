# tradevodata

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/christianpichichero-max/tradevodata-py/blob/main/examples/lookahead_bias_demo.ipynb)

Point-in-time US equity fundamentals from SEC EDGAR. Every value carries the date it actually
became public, so a backtest can only see what was knowable at the time.

## See the bug before installing anything

The no-signup Colab experiment joins the same fundamentals two ways. The ordinary
period-end join uses a value that was **not public yet in 47 of 413 ticker-months (11%)**.
The point-in-time join removes those future values. [Run the 3-minute proof in
Colab](https://colab.research.google.com/github/christianpichichero-max/tradevodata-py/blob/main/examples/lookahead_bias_demo.ipynb).

```bash
pip install tradevodata
```

## The free sample needs no key

```python
import tradevodata as tv

rows = tv.sample()        # 40 large caps, ~3,280 rows, CC0, no signup
```

Returns a pandas `DataFrame` if pandas is installed, otherwise a plain list of dicts — so
the line above works on a bare install. Force either shape with `to_pandas=True/False`.

Same columns and the same semantics as the paid dataset, so you can write and verify your
join logic before paying for anything.

## `as_of` is required, on purpose

```python
import tradevodata as tv

client = tv.Client(api_key="tvd_...")     # or set TRADEVODATA_API_KEY

client.fundamentals("AAPL", as_of="2024-06-30")  # annual (default)
client.fundamentals("AAPL", as_of="2024-06-30", period="quarterly")
```

There is no way to ask this library "what is Apple's revenue?" — only "what was Apple's
revenue *knowable on this date?*". On 2024-06-30 the answer is FY2023, because the FY2024 10-K
had not been filed yet. That distinction is the entire product, and a default value for
`as_of` is how lookahead bias gets written by accident.

## Whole-universe cross-section

One call per rebalance date, instead of looping tickers:

```python
snap = client.snapshot(
    as_of="2024-06-30", concept="Revenue", period="quarterly", to_pandas=True
)
```

## Bulk

```python
client.download("tradevodata_annual.csv.gz")
client.download("tradevodata_quarterly.csv.gz", period="quarterly")
```

## Doing the point-in-time join yourself

If you're working from `sample()` or a bulk download, the as-of join is yours to do —
`as_of_filter` does it correctly:

```python
rows = tv.sample()
knowable = tv.as_of_filter(rows, as_of="2020-03-31")
```

Keeps only rows whose `first_filed <= as_of`, then the newest fiscal period per
ticker/concept. That is the same logic the API applies server-side.

## What each row tells you

| column | meaning |
|---|---|
| `first_filed` | the date the value became public — the point-in-time stamp |
| `original_value` | what was first reported. Use this for backtests |
| `latest_value` | the current revision. **May post-date your `as_of` — not PIT-safe** |
| `restated` | a later filing revised this by more than 0.5% |
| `lag_days` | days from period end to first publication |
| `qa_status` | `clean`, or `FLAG:` + reasons. We flag; we never silently drop |
| `fiscal_period` | `FY` for annual rows; `Q1`–`Q4` for quarterly rows |
| `period_start` | start of a quarterly duration; null for instant concepts |
| `ytd_value` | source year-to-date value when a discrete quarter is derived |
| `derivation` | `reported`, `ytd_diff`, or `fy_minus_9m` |

The client raises a `UserWarning` when rows come back flagged or when your `as_of` runs past
our data cutoff. Silence it with `Client(warn_on_flags=False)` if you're handling `qa_status`
yourself.

## Honest limits

- Annual data comes from 10-K/10-K/A filings. Quarterly data is requested explicitly with
  `period="quarterly"` and includes accepted 10-Q/10-Q/A facts plus supported Q4 derivations.
- Quarterly depth varies by filer and tag availability; do not assume every company has 48 quarters.
- **US only**, and **no delisted companies** — so mind survivorship bias if you build universes
  from this alone. We fix lookahead bias; that is a different problem.
- 16 annual concepts and 7 quarterly concepts, with up to 12 fiscal years of history where
  SEC XBRL coverage supports it.
- Filing lag averages 66 days across the universe (median 60, max 120). The 40-company sample
  averages 43 — large caps file fastest, so the sample is *better* than the whole.

If you need delisted coverage or a survivorship-bias-free historical universe, this dataset does
not provide it; use a provider that explicitly includes inactive securities.

## Zero dependencies

Standard library only. `pandas` is opt-in:

```bash
pip install "tradevodata[pandas]"
```

## See the bug for yourself

The [Colab notebook](examples/lookahead_bias_demo.ipynb) runs the experiment on the free
sample — no key, no signup, no install. It joins fundamentals both ways at every month-end
and counts the disagreements. On the 40-company sample: **47 of 413 ticker-months (11%) use a
revenue number that was not yet public.**

## Audit another provider

If you already have a fundamentals CSV, the local audit checks whether it exposes a real
availability date and whether revised values appear where the free sample recorded a
different first-reported value:

```bash
python examples/audit_provider_csv.py provider.csv \
  --ticker-col ticker --concept-col concept --period-end-col period_end \
  --value-col value --available-col filed
```

Nothing is uploaded. The script runs locally and explains every check it can and cannot
verify.

## Build a point-in-time factor snapshot

```bash
pip install "tradevodata[pandas]"
python examples/point_in_time_factor.py --as-of 2024-06-30
```

This produces margins and return-on-capital measures using only annual values that had been
filed by the requested date.

## Links

- Product — https://tradevodata.com/?utm_source=github&utm_medium=repo&utm_campaign=python-client
- Docs — https://tradevodata.com/docs?utm_source=github&utm_medium=repo&utm_campaign=python-client
- Free CC0 sample — https://github.com/christianpichichero-max/pit-fundamentals
- Methodology — how each number is derived from raw filings, so you can check any row

MIT licensed. Data sourced from SEC EDGAR (public domain). This is a dataset, not investment
advice.
