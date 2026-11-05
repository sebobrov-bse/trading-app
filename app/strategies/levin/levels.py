"""Daily level calculation from 1-minute candles.

Computes Volume Profile (POC, VAH, VAL) and Classic Pivot Points
(Pivot, R1, R2, S1, S2).
"""

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DailyLevels:
    """All levels computed for one trading day."""

    pivot: float
    r1: float
    r2: float
    s1: float
    s2: float
    poc: float
    vah: float
    val: float
    high_day: float
    low_day: float
    close_day: float


def calculate_daily_levels(
    day_candles: pd.DataFrame,
    n_bins: int = 100,
    va_percent: float = 0.70,
) -> DailyLevels | None:
    """Compute Volume Profile + Pivot levels for a single day.

    day_candles: 1m candles with columns high, low, close, volume.
    Returns None if there is no data.
    """
    if day_candles.empty:
        return None

    high_day = float(day_candles["high"].max())
    low_day = float(day_candles["low"].min())
    close_day = float(day_candles["close"].iloc[-1])

    if high_day <= low_day:
        return None

    # ---- Classic Pivot Points ----
    pivot = (high_day + low_day + close_day) / 3.0
    r1 = 2.0 * pivot - low_day
    s1 = 2.0 * pivot - high_day
    r2 = pivot + (high_day - low_day)
    s2 = pivot - (high_day - low_day)

    # ---- Volume Profile ----
    step = (high_day - low_day) / n_bins
    if step <= 0:
        return DailyLevels(
            pivot=pivot,
            r1=r1,
            r2=r2,
            s1=s1,
            s2=s2,
            poc=close_day,
            vah=close_day,
            val=close_day,
            high_day=high_day,
            low_day=low_day,
            close_day=close_day,
        )

    typical = (day_candles["high"] + day_candles["low"] + day_candles["close"]) / 3.0
    bin_idx = ((typical - low_day) / step).astype(int).clip(0, n_bins - 1)

    volume_by_bin = day_candles["volume"].groupby(bin_idx).sum()
    volume_by_bin = volume_by_bin.reindex(range(n_bins), fill_value=0)

    total_volume = float(volume_by_bin.sum())
    if total_volume <= 0:
        return DailyLevels(
            pivot=pivot,
            r1=r1,
            r2=r2,
            s1=s1,
            s2=s2,
            poc=close_day,
            vah=close_day,
            val=close_day,
            high_day=high_day,
            low_day=low_day,
            close_day=close_day,
        )

    poc_bin = int(volume_by_bin.idxmax())
    poc_price = low_day + (poc_bin + 0.5) * step

    target = total_volume * va_percent
    covered = float(volume_by_bin.iloc[poc_bin])
    lo = hi = poc_bin

    while covered < target and (lo > 0 or hi < n_bins - 1):
        vol_below = float(volume_by_bin.iloc[lo - 1]) if lo > 0 else -1.0
        vol_above = float(volume_by_bin.iloc[hi + 1]) if hi < n_bins - 1 else -1.0

        if vol_above >= vol_below:
            hi += 1
            covered += vol_above
        else:
            lo -= 1
            covered += vol_below

    vah = low_day + (hi + 1) * step
    val = low_day + lo * step

    return DailyLevels(
        pivot=pivot,
        r1=r1,
        r2=r2,
        s1=s1,
        s2=s2,
        poc=poc_price,
        vah=vah,
        val=val,
        high_day=high_day,
        low_day=low_day,
        close_day=close_day,
    )
