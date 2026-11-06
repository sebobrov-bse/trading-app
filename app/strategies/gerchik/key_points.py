"""Key point detection and trend determination for the Gerchik system.

Two kinds of key points:
- stop:           stop of a trend move (3+ bars + impulse + reversal).
- correction_end: end of a correction after a 5+ bar move (fib 23.6-61.8%).

`determine_trend` uses the NEAREST key point (not the strongest), because
trend is defined by the latest structure.
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

import numpy as np
import pandas as pd

from app.strategies.gerchik.config import GerchikConfig

logger = logging.getLogger(__name__)

Direction = Literal["up", "down"]
Trend = Literal["UP", "DOWN", "NEUTRAL"]


@dataclass(frozen=True)
class KeyPoint:
    price: float
    kind: Literal["stop", "correction_end"]
    direction: Direction  # direction of movement BEFORE the point
    date: date
    strength: float  # size of the move in ATR units


def _ts_to_date(ts) -> Optional[date]:
    if ts is None:
        return None
    if hasattr(ts, "date"):
        return ts.date()
    return None


# ---------------------------------------------------------------------------
#  Trend stops
# ---------------------------------------------------------------------------


def _is_stop_bar(
    daily_bars: pd.DataFrame,
    idx: int,
    is_up_move: bool,
    config: GerchikConfig,
) -> bool:
    """Check if bar at idx signals a stop of an up/down move.

    For up move:
      - bearish close (close < open), OR
      - long upper shadow (upper > long_tail_threshold * range).
    For down move:
      - bullish close (close > open), OR
      - long lower shadow (lower > long_tail_threshold * range).

    Note on interpretation: 'tail against direction' = the wick that
    shows rejection. For up move that's the upper wick (price tried
    higher, got pushed back down). This is the standard Gerchik signal.
    """
    if idx >= len(daily_bars):
        return False

    o = float(daily_bars["open"].iloc[idx])
    h = float(daily_bars["high"].iloc[idx])
    l = float(daily_bars["low"].iloc[idx])
    c = float(daily_bars["close"].iloc[idx])
    rng = h - l

    if rng <= 0:
        return False

    if is_up_move:
        if c < o:
            return True
        upper_shadow = h - max(o, c)
        if upper_shadow > config.long_tail_threshold * rng:
            return True
    else:
        if c > o:
            return True
        lower_shadow = min(o, c) - l
        if lower_shadow > config.long_tail_threshold * rng:
            return True

    return False


def _find_trend_stops(
    daily_bars: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[KeyPoint]:
    """Scan for strong runs, then confirm with a stop bar."""
    out: list[KeyPoint] = []
    if atr <= 0 or len(daily_bars) < config.n_strong + 1:
        return out

    n = len(daily_bars)
    closes = daily_bars["close"].to_numpy(dtype=float)
    opens = daily_bars["open"].to_numpy(dtype=float)
    highs = daily_bars["high"].to_numpy(dtype=float)
    lows = daily_bars["low"].to_numpy(dtype=float)
    ranges = highs - lows
    dates = daily_bars.index

    i = 0
    while i < n - config.n_strong:
        is_up = closes[i] > opens[i]
        is_down = closes[i] < opens[i]
        if not (is_up or is_down):
            i += 1
            continue

        # Extend the run.
        j = i
        while j < n:
            if is_up and closes[j] > opens[j]:
                j += 1
            elif is_down and closes[j] < opens[j]:
                j += 1
            else:
                break

        run_len = j - i
        if run_len < config.n_strong:
            i = j
            continue

        # Impulse: at least one bar with range > k_impulse * ATR.
        has_impulse = any(ranges[k] > config.k_impulse * atr for k in range(i, j))
        # Path: sum of |close - open|.
        total_path = float(sum(abs(closes[k] - opens[k]) for k in range(i, j)))

        if not has_impulse or total_path < config.k_strong_path * atr:
            i = j
            continue

        # Stop bar must be the NEXT bar (j).
        if j >= n:
            break

        if _is_stop_bar(daily_bars, j, is_up, config):
            last_idx = j - 1
            price = float(highs[last_idx]) if is_up else float(lows[last_idx])
            out.append(
                KeyPoint(
                    price=price,
                    kind="stop",
                    direction="up" if is_up else "down",
                    date=_ts_to_date(dates[last_idx]),
                    strength=total_path / atr,
                )
            )

        i = j

    return out


# ---------------------------------------------------------------------------
#  Correction ends
# ---------------------------------------------------------------------------


def _find_local_pivots(
    highs: np.ndarray,
    lows: np.ndarray,
    window: int = 2,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Local pivots with given window (default 2 bars on each side)."""
    piv_h: list[tuple[int, float]] = []
    piv_l: list[tuple[int, float]] = []
    n = len(highs)
    for i in range(window, n - window):
        if all(highs[i] >= highs[i - k] for k in range(1, window + 1)) and all(
            highs[i] >= highs[i + k] for k in range(1, window + 1)
        ):
            piv_h.append((i, float(highs[i])))
        if all(lows[i] <= lows[i - k] for k in range(1, window + 1)) and all(
            lows[i] <= lows[i + k] for k in range(1, window + 1)
        ):
            piv_l.append((i, float(lows[i])))
    return piv_h, piv_l


def _find_correction_ends(
    daily_bars: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[KeyPoint]:
    """Find 5+ bar moves followed by a 23.6-61.8% retrace that reverses."""
    out: list[KeyPoint] = []
    if atr <= 0 or len(daily_bars) < 15:
        return out

    n = len(daily_bars)
    highs = daily_bars["high"].to_numpy(dtype=float)
    lows = daily_bars["low"].to_numpy(dtype=float)
    closes = daily_bars["close"].to_numpy(dtype=float)
    opens = daily_bars["open"].to_numpy(dtype=float)
    dates = daily_bars.index

    piv_h, piv_l = _find_local_pivots(highs, lows, window=2)
    min_move_bars = 5
    max_wait = 15
    min_move_size = config.k_strong_path * atr * 0.5

    # Up moves: low -> high, then pullback low.
    for i_low, low_p in piv_l:
        # Find the next high pivot after min_move_bars.
        for i_high, high_p in piv_h:
            if i_high < i_low + min_move_bars - 1:
                continue
            if i_high >= n - 2:
                break
            move_size = high_p - low_p
            if move_size < min_move_size:
                continue

            pb_low = high_p
            pb_idx = None
            for j in range(i_high + 1, min(n, i_high + max_wait)):
                if lows[j] < pb_low:
                    pb_low = float(lows[j])
                    pb_idx = j
                retrace = (high_p - pb_low) / move_size if move_size > 0 else 0.0
                if retrace > config.fib_max:
                    break
                if retrace < config.fib_min:
                    continue
                # In fib band — check resume.
                if j + 1 < n and (
                    (closes[j] > opens[j] and closes[j + 1] > opens[j + 1]) or highs[j] > high_p
                ):
                    out.append(
                        KeyPoint(
                            price=pb_low,
                            kind="correction_end",
                            direction="up",
                            date=_ts_to_date(dates[pb_idx]),
                            strength=move_size / atr,
                        )
                    )
                    break
            break  # one high per low

    # Down moves: high -> low, then pullback high.
    for i_high, high_p in piv_h:
        for i_low, low_p in piv_l:
            if i_low < i_high + min_move_bars - 1:
                continue
            if i_low >= n - 2:
                break
            move_size = high_p - low_p
            if move_size < min_move_size:
                continue

            pb_high = low_p
            pb_idx = None
            for j in range(i_low + 1, min(n, i_low + max_wait)):
                if highs[j] > pb_high:
                    pb_high = float(highs[j])
                    pb_idx = j
                retrace = (pb_high - low_p) / move_size if move_size > 0 else 0.0
                if retrace > config.fib_max:
                    break
                if retrace < config.fib_min:
                    continue
                if j + 1 < n and (
                    (closes[j] < opens[j] and closes[j + 1] < opens[j + 1]) or lows[j] < low_p
                ):
                    out.append(
                        KeyPoint(
                            price=pb_high,
                            kind="correction_end",
                            direction="down",
                            date=_ts_to_date(dates[pb_idx]),
                            strength=move_size / atr,
                        )
                    )
                    break
            break

    return out


# ---------------------------------------------------------------------------
#  Public: find_key_points
# ---------------------------------------------------------------------------


def find_key_points(
    daily_bars: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[KeyPoint]:
    """Find all key points (stops + correction ends), sorted by date."""
    points = _find_trend_stops(daily_bars, atr, config)
    points.extend(_find_correction_ends(daily_bars, atr, config))
    points.sort(key=lambda kp: kp.date)
    return points


# ---------------------------------------------------------------------------
#  Trend determination
# ---------------------------------------------------------------------------


def determine_trend(
    current_price: float,
    key_points: list[KeyPoint],
    config: GerchikConfig,
) -> Trend:
    """Determine trend by the NEAREST key point below/above the price.

    - nearest support (below price) that is a DOWN-stop or down-correction → UP
    - nearest resistance (above price) that is an UP-stop or up-correction → DOWN
    - if both signal → closer wins; if equidistant → NEUTRAL
    """
    if not key_points:
        return "NEUTRAL"

    supports = [kp for kp in key_points if kp.price < current_price]
    resistances = [kp for kp in key_points if kp.price > current_price]

    bullish_support = None
    if supports:
        nearest_sup = max(supports, key=lambda kp: kp.price)
        if nearest_sup.direction == "down":  # stop of down-move OR end of down-correction
            bullish_support = nearest_sup

    bearish_resistance = None
    if resistances:
        nearest_res = min(resistances, key=lambda kp: kp.price)
        if nearest_res.direction == "up":
            bearish_resistance = nearest_res

    if bullish_support is None and bearish_resistance is None:
        return "NEUTRAL"
    if bullish_support is not None and bearish_resistance is None:
        return "UP"
    if bearish_resistance is not None and bullish_support is None:
        return "DOWN"

    # Both signal — closer wins.
    dist_up = current_price - bullish_support.price
    dist_down = bearish_resistance.price - current_price
    if dist_up < dist_down:
        return "UP"
    if dist_down < dist_up:
        return "DOWN"
    return "NEUTRAL"
