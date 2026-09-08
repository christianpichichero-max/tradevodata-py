"""Point-in-time US equity fundamentals from SEC EDGAR.

Every value carries the date it actually became public, so a backtest can only see what was
knowable at the time.

    import tradevodata as tv

    df = tv.sample()                                   # free, no key
    tv.Client().fundamentals("AAPL", as_of="2024-06-30")

Docs: https://tradevodata.com/docs
"""

from .client import (
    AuthError,
    Client,
    NotFoundError,
    QuotaError,
    TradevoDataError,
    as_of_filter,
    sample,
)

__version__ = "0.2.0"
__all__ = [
    "Client",
    "sample",
    "as_of_filter",
    "TradevoDataError",
    "AuthError",
    "QuotaError",
    "NotFoundError",
    "__version__",
]
