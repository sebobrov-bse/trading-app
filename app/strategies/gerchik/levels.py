"""Level identification and scoring for the Gerchik system.

8 level types from D1 bars, then merge → score → filter.

All calculations are pure functions over a DataFrame — no Backtrader,
no DB. Testable in isolation.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from app.strategies.gerchik.config import GerchikConfig


# ---------------------------------------------------------------------------
#  Data model
# ---------------------------------------------------------------------------


class LevelType(str, Enum):
    TREND_BREAK = "trend_break"
    MIRROR = "mirror"
    LIMIT_PLAYER = "limit_player"
    HISTORICAL = "historical"
    PARANORMAL_BAR = "paranormal_bar"
    CONSOLIDATION = "consolidation"
    AIR = "air"
    GAP = "gap"


@dataclass
class Level:
    """A price level with scoring metadata."""

    price: float
    type: LevelType
    base_score: int = 0
    bonuses: list[tuple[str, int]] = field(default_factory=list)
    penalties: list[tuple[str, int]] = field(default_factory=list)
    total_score: int = 0
    touches: int = 0
    has_false_breakout: bool = False
    is_round_number: bool = False
    is_higher_tf_match: bool = False
    created_date: Optional[date] = None
    last_touch_date: Optional[date] = None


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------


def _ts_to_date(ts) -> Optional[date]:
    if ts is None:
        return None
    if hasattr(ts, "date"):
        return ts.date()
    return None


def _is_round(price: float, step: float, tolerance_pct: float = 0.002) -> bool:
    """True if price is within `tolerance_pct` of a multiple of `step`.

    Tolerance is needed because on real data, pivots never land on
    exactly 250.00 — they land on 249.87 or 250.13, which is still
    'the 250 round level' from a trader's point of view.

    Uses round-half-to-even to find nearest multiple (Python's default).
    """
    if step <= 0 or price <= 0 or tolerance_pct <= 0:
        return False
    nearest = round(price / step) * step
    return abs(price - nearest) / price < tolerance_pct


# ---------------------------------------------------------------------------
#  Detection — 8 types
# ---------------------------------------------------------------------------


def _detect_trend_break(df: pd.DataFrame, config: GerchikConfig) -> list[Level]:
    """2 up bars then 2 down (or reverse) — direction change.

    Level = the high (top) or low (bottom) of the bar that ended
    the preceding move (index i-2 in a 4-bar window).
    """
    out: list[Level] = []
    ups = df["close"].to_numpy() > df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    for i in range(3, len(df)):
        # up, up, down, down -> top
        if ups[i - 3] and ups[i - 2] and not ups[i - 1] and not ups[i]:
            out.append(
                Level(
                    price=float(highs[i - 2]),
                    type=LevelType.TREND_BREAK,
                    base_score=config.score_trend_break,
                    created_date=_ts_to_date(df.index[i - 2]),
                )
            )
        # down, down, up, up -> bottom
        elif not ups[i - 3] and not ups[i - 2] and ups[i - 1] and ups[i]:
            out.append(
                Level(
                    price=float(lows[i - 2]),
                    type=LevelType.TREND_BREAK,
                    base_score=config.score_trend_break,
                    created_date=_ts_to_date(df.index[i - 2]),
                )
            )
    return out


def _find_pivots(
    highs: np.ndarray,
    lows: np.ndarray,
    window: int = 1,
) -> tuple[list[tuple[int, float]], list[tuple[int, float]]]:
    """Simple local pivots: high[i] >= neighbours, low[i] <= neighbours."""
    piv_highs: list[tuple[int, float]] = []
    piv_lows: list[tuple[int, float]] = []
    n = len(highs)
    for i in range(window, n - window):
        if highs[i] >= highs[i - window] and highs[i] >= highs[i + window]:
            piv_highs.append((i, float(highs[i])))
        if lows[i] <= lows[i - window] and lows[i] <= lows[i + window]:
            piv_lows.append((i, float(lows[i])))
    return piv_highs, piv_lows


def _detect_mirror(
    df: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[Level]:
    """Was support (low), now resistance (high), or vice versa."""
    out: list[Level] = []
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    piv_highs, piv_lows = _find_pivots(highs, lows, window=1)
    tol = config.level_merge_pct
    min_gap = 10  # bars between pivots to count as different regions

    for i_low, low_p in piv_lows:
        for i_high, high_p in piv_highs:
            if i_high <= i_low + min_gap:
                continue
            if abs(low_p - high_p) / max(low_p, 1e-9) < tol:
                out.append(
                    Level(
                        price=(low_p + high_p) / 2.0,
                        type=LevelType.MIRROR,
                        base_score=config.score_mirror,
                    )
                )
    return out


def _detect_limit_player(
    df: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[Level]:
    """3+ touches without breaking."""
    out: list[Level] = []
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    piv_highs, piv_lows = _find_pivots(highs, lows, window=1)
    tol = config.level_merge_pct

    seen: set[float] = set()
    candidates = [(p, "high") for _, p in piv_highs] + [(p, "low") for _, p in piv_lows]

    for price, side in candidates:
        key = round(price, 4)
        if key in seen:
            continue
        seen.add(key)

        touches = 0
        for i in range(n):
            if side == "high":
                if abs(highs[i] - price) / max(price, 1e-9) < tol:
                    touches += 1
            else:
                if abs(lows[i] - price) / max(price, 1e-9) < tol:
                    touches += 1

        if touches >= config.touches_for_limit_player:
            out.append(
                Level(
                    price=price,
                    type=LevelType.LIMIT_PLAYER,
                    base_score=config.score_limit_player,
                    touches=touches,
                )
            )
    return out


def _detect_historical(
    df: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[Level]:
    """Exact price repetition on the same side (high-high or low-low)."""
    out: list[Level] = []
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    n = len(df)
    tol = config.level_merge_pct
    min_gap = 20

    # Limit by scanning all pairs — n=250, fine.
    for i in range(n):
        for j in range(i + min_gap, n):
            if abs(highs[i] - highs[j]) / max(highs[i], 1e-9) < tol:
                out.append(
                    Level(
                        price=(highs[i] + highs[j]) / 2.0,
                        type=LevelType.HISTORICAL,
                        base_score=config.score_historical,
                    )
                )
            if abs(lows[i] - lows[j]) / max(lows[i], 1e-9) < tol:
                out.append(
                    Level(
                        price=(lows[i] + lows[j]) / 2.0,
                        type=LevelType.HISTORICAL,
                        base_score=config.score_historical,
                    )
                )
    return out


def _detect_paranormal_bar(
    df: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[Level]:
    """Bar with range > big_k * ATR."""
    out: list[Level] = []
    if atr <= 0:
        return out
    ranges = (df["high"] - df["low"]).to_numpy()
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()
    threshold = config.atr_big_k * atr

    for i in range(len(df)):
        if ranges[i] <= threshold:
            continue
        is_up = closes[i] > opens[i]
        price = float(df["high"].iloc[i]) if is_up else float(df["low"].iloc[i])
        out.append(
            Level(
                price=price,
                type=LevelType.PARANORMAL_BAR,
                base_score=config.score_paranormal_bar,
                created_date=_ts_to_date(df.index[i]),
            )
        )
    return out


def _detect_consolidation(
    df: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[Level]:
    """Tight zone: N consecutive bars all with range < 0.5 * ATR."""
    out: list[Level] = []
    if atr <= 0 or len(df) < 5:
        return out
    ranges = (df["high"] - df["low"]).to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    window = 5

    for i in range(window, len(df)):
        chunk = ranges[i - window : i]
        if all(r < 0.5 * atr for r in chunk):
            mid = (highs[i - window : i].max() + lows[i - window : i].min()) / 2.0
            out.append(
                Level(
                    price=float(mid),
                    type=LevelType.CONSOLIDATION,
                    base_score=config.score_consolidation,
                    created_date=_ts_to_date(df.index[i - 1]),
                )
            )
    return out


def _detect_air(
    df: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[Level]:
    """Two consecutive big opposite-direction bars."""
    out: list[Level] = []
    if atr <= 0:
        return out
    ranges = (df["high"] - df["low"]).to_numpy()
    closes = df["close"].to_numpy()
    opens = df["open"].to_numpy()
    threshold = 1.5 * atr

    for i in range(1, len(df)):
        if ranges[i - 1] < threshold or ranges[i] < threshold:
            continue
        prev_up = closes[i - 1] > opens[i - 1]
        curr_up = closes[i] > opens[i]
        if prev_up == curr_up:
            continue
        # Outer extreme of the first bar
        price = float(df["high"].iloc[i - 1]) if prev_up else float(df["low"].iloc[i - 1])
        out.append(
            Level(
                price=price,
                type=LevelType.AIR,
                base_score=config.score_air,
                created_date=_ts_to_date(df.index[i - 1]),
            )
        )
    return out


def _detect_gap(
    df: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[Level]:
    """Gap between consecutive bars (both boundaries as levels)."""
    out: list[Level] = []
    if atr <= 0:
        return out
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    min_gap = 0.3 * atr

    for i in range(1, len(df)):
        if lows[i] > highs[i - 1] and (lows[i] - highs[i - 1]) >= min_gap:
            out.append(
                Level(
                    price=float(lows[i]),
                    type=LevelType.GAP,
                    base_score=config.score_air,
                )
            )
            out.append(
                Level(
                    price=float(highs[i - 1]),
                    type=LevelType.GAP,
                    base_score=config.score_air,
                )
            )
        elif highs[i] < lows[i - 1] and (lows[i - 1] - highs[i]) >= min_gap:
            out.append(
                Level(
                    price=float(highs[i]),
                    type=LevelType.GAP,
                    base_score=config.score_air,
                )
            )
            out.append(
                Level(
                    price=float(lows[i - 1]),
                    type=LevelType.GAP,
                    base_score=config.score_air,
                )
            )
    return out


def identify_levels(
    daily_bars: pd.DataFrame,
    atr: float,
    config: GerchikConfig,
) -> list[Level]:
    """Run all 8 detectors, return the raw list."""
    levels: list[Level] = []
    levels.extend(_detect_trend_break(daily_bars, config))
    levels.extend(_detect_mirror(daily_bars, atr, config))
    levels.extend(_detect_limit_player(daily_bars, atr, config))
    levels.extend(_detect_historical(daily_bars, atr, config))
    levels.extend(_detect_paranormal_bar(daily_bars, atr, config))
    levels.extend(_detect_consolidation(daily_bars, atr, config))
    levels.extend(_detect_air(daily_bars, atr, config))
    levels.extend(_detect_gap(daily_bars, atr, config))
    return levels


# ---------------------------------------------------------------------------
#  Merge
# ---------------------------------------------------------------------------


def merge_similar_levels(
    levels: list[Level],
    config: GerchikConfig,
) -> list[Level]:
    """Collapse levels within level_merge_pct. Higher base_score wins.

    Bonuses and penalties from both levels are combined, touches summed.
    """
    if not levels:
        return []

    sorted_levels = sorted(levels, key=lambda lv: lv.price)
    merged: list[Level] = [sorted_levels[0]]
    tol = config.level_merge_pct

    for lv in sorted_levels[1:]:
        last = merged[-1]
        if abs(lv.price - last.price) / max(last.price, 1e-9) < tol:
            # Same zone — keep higher base, combine details.
            winner = lv if lv.base_score > last.base_score else last
            loser = last if winner is lv else lv
            winner.bonuses.extend(loser.bonuses)
            winner.penalties.extend(loser.penalties)
            winner.touches = max(winner.touches, loser.touches)
            winner.has_false_breakout = winner.has_false_breakout or loser.has_false_breakout
            merged[-1] = winner
        else:
            merged.append(lv)
    return merged


# ---------------------------------------------------------------------------
#  Scoring
# ---------------------------------------------------------------------------


def score_levels(
    levels: list[Level],
    daily_bars: pd.DataFrame,
    config: GerchikConfig,
) -> list[Level]:
    """For each level: base + bonuses − penalties → total_score."""
    highs = daily_bars["high"].to_numpy()
    lows = daily_bars["low"].to_numpy()
    closes = daily_bars["close"].to_numpy()
    opens = daily_bars["open"].to_numpy()
    n = len(daily_bars)
    tol = config.level_merge_pct

    for lv in levels:
        price = lv.price

        # ---- touches + false breakout ----
        touches = 0
        false_breakout = False
        for i in range(n):
            near_high = abs(highs[i] - price) / max(price, 1e-9) < tol
            near_low = abs(lows[i] - price) / max(price, 1e-9) < tol
            if near_high or near_low:
                touches += 1
            # False breakout: wick above/below, close back inside
            if lows[i] < price < highs[i]:
                if closes[i] < price and opens[i] < price:
                    if highs[i] > price * (1 + tol):
                        false_breakout = True
                elif closes[i] > price and opens[i] > price:
                    if lows[i] < price * (1 - tol):
                        false_breakout = True

        lv.touches = max(lv.touches, touches)

        # ---- bonuses ----
        if false_breakout and config.bonus_false_breakout > 0:
            lv.has_false_breakout = True
            lv.bonuses.append(("false_breakout", config.bonus_false_breakout))

        if config.bonus_round_number > 0 and _is_round(
            price,
            config.round_number_step,
            config.round_number_tolerance_pct,
        ):
            lv.is_round_number = True
            lv.bonuses.append(("round_number", config.bonus_round_number))

        if lv.touches > config.touches_for_limit_player and config.bonus_extra_touches > 0:
            extra = min(
                lv.touches - config.touches_for_limit_player,
                config.bonus_extra_touches_max,
            )
            lv.bonuses.append(("extra_touches", extra * config.bonus_extra_touches))

        # ---- penalties ----
        crossings = 0
        for i in range(1, n):
            prev_above = closes[i - 1] > price
            curr_above = closes[i] > price
            if prev_above != curr_above:
                crossings += 1
        if crossings >= 5 and config.penalty_chop < 0:
            lv.penalties.append(("chop", config.penalty_chop))

        # Body-only penalty for paranormal bars: bar whose body is > 80% of range
        if lv.type == LevelType.PARANORMAL_BAR and config.penalty_body_only < 0:
            for i in range(n):
                rng = highs[i] - lows[i]
                if rng <= 0:
                    continue
                body = abs(closes[i] - opens[i])
                if body > 0.8 * rng and (
                    abs(highs[i] - price) / max(price, 1e-9) < tol
                    or abs(lows[i] - price) / max(price, 1e-9) < tol
                ):
                    lv.penalties.append(("body_only", config.penalty_body_only))
                    break

        # ---- total ----
        lv.total_score = (
            lv.base_score + sum(v for _, v in lv.bonuses) + sum(v for _, v in lv.penalties)
        )

    return levels


# ---------------------------------------------------------------------------
#  Filter
# ---------------------------------------------------------------------------


def filter_strong_levels(
    levels: list[Level],
    config: GerchikConfig,
) -> list[Level]:
    """Keep only total_score >= min_level_score."""
    return [lv for lv in levels if lv.total_score >= config.min_level_score]
