"""Convert a pandas DataFrame into a Backtrader PandasData feed."""

import backtrader as bt
import pandas as pd

REQUIRED_COLUMNS = ("open", "high", "low", "close", "volume")


def df_to_bt_feed(df: pd.DataFrame) -> bt.feeds.PandasData:
    """Validate a DataFrame and wrap it into a Backtrader feed.

    Checks:
    - non-empty
    - index is a DatetimeIndex
    - required columns are present
    - no NaN in the OHLCV columns

    Raises ValueError with a clear message on any problem.
    """
    if df.empty:
        raise ValueError("df is empty")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            f"df.index must be DatetimeIndex, got {type(df.index).__name__}"
        )

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"df missing columns: {missing}")

    if df[list(REQUIRED_COLUMNS)].isna().any().any():
        raise ValueError("df contains NaN in OHLCV columns")

    return bt.feeds.PandasData(dataname=df)