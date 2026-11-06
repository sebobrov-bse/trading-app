"""Orchestrator: precompute all Gerchik components per day.

For each trading day D in [start, end] (look-ahead free):

- ATR from bars[D-atr_period : D] (only past).
- Levels from bars[0 : D]  (only past).
- Key points from bars[0 : D].
- Trend from key points + close[D] (current observation).
- Energy per strong level, from bars[0 : D].
- path_ratio = (close[D] - close[D-1]) / atr.

Returns a list of PrecomputedDay. One PrecomputedDay has per-day
attributes (atr, prev_close, close, trend, path_ratio, key_points,
strong_levels) and a list of PrecomputedLevelRow — one DB row
candidate per (day, strong level).

`save_to_db` writes the rows to the gerchik_levels table.
"""

import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.strategies.gerchik.config import GerchikConfig
from app.strategies.gerchik.atr import calculate_clean_atr
from app.strategies.gerchik.levels import (
    identify_levels,
    merge_similar_levels,
    score_levels,
    filter_strong_levels,
    Level,
    LevelType,
)
from app.strategies.gerchik.key_points import (
    find_key_points,
    determine_trend,
    KeyPoint,
)
from app.strategies.gerchik.energy import evaluate_energy, EnergyContext

logger = logging.getLogger(__name__)


@dataclass
class PrecomputedLevelRow:
    """One DB row candidate: a strong level with its full context."""

    symbol: str
    date: date
    level_price: float
    level_type: LevelType
    total_score: int
    trend: str  # "UP" / "DOWN" / "NEUTRAL"
    energy: EnergyContext
    path_ratio: float
    atr: float
    prev_close: float


@dataclass
class PrecomputedDay:
    """One day's snapshot; rows contain the per-level data."""

    symbol: str
    date: date
    atr: float
    prev_close: float
    close: float
    path_ratio: float
    trend: str
    key_points: list[KeyPoint] = field(default_factory=list)
    strong_levels: list[Level] = field(default_factory=list)
    rows: list[PrecomputedLevelRow] = field(default_factory=list)


def _load_d1(session: Session, symbol: str, start: date, end: date):
    """Load D1 candles; handles both get_dataframe signatures."""
    from app.services.candle_repository import CandleRepository

    repo = CandleRepository()
    try:
        return repo.get_dataframe(symbol=symbol, timeframe=24, start=start, end=end)
    except TypeError:
        return repo.get_dataframe(
            session,
            symbol=symbol,
            timeframe=24,
            start=start,
            end=end,
        )


def precompute_gerchik(
    session: Session,
    symbol: str,
    start: date,
    end: date,
    config: GerchikConfig | None = None,
) -> list[PrecomputedDay]:
    """Run the full pipeline for `symbol` over `[start, end]`."""
    if config is None:
        config = GerchikConfig()

    load_start = start - timedelta(days=config.atr_period + 10)
    df = _load_d1(session, symbol, load_start, end)
    if df is None or df.empty:
        logger.warning("No D1 for %s in %s..%s", symbol, load_start, end)
        return []

    df = df.sort_index()
    idx_dates = [ts.date() if hasattr(ts, "date") else ts for ts in df.index]

    min_history = config.atr_period + 1
    results: list[PrecomputedDay] = []

    for i in range(len(df)):
        day = idx_dates[i]
        if day < start or day > end:
            continue
        if i < min_history:
            continue

        # Limit history for level/key_point detection: trend_break
        # detection is O(N) in history size, so without this cap the
        # number of levels grows linearly with years of data. 120 bars
        # (≈6 months) is enough for limit_player (3 touches) and
        # mirror (pivot-to-pivot within 10+ bars).
        lookback = config.history_lookback_bars
        bars_prev = df.iloc[max(0, i - lookback) : i]
        prev_close = float(df["close"].iloc[i - 1])
        current_close = float(df["close"].iloc[i])

        atr_res = calculate_clean_atr(bars_prev, config)
        atr = atr_res.value
        if not math.isfinite(atr) or atr <= 0:
            continue

        raw = identify_levels(bars_prev, atr, config)
        merged = merge_similar_levels(raw, config)
        scored = score_levels(merged, bars_prev, config)
        strong = filter_strong_levels(scored, config)

        kps = find_key_points(bars_prev, atr, config)
        trend = determine_trend(current_close, kps, config)

        # path_ratio: signed, relative to prev_close.
        path_ratio = (current_close - prev_close) / atr

        rows: list[PrecomputedLevelRow] = []
        for lv in strong:
            energy_res = evaluate_energy(bars_prev, lv.price, atr, config)
            rows.append(
                PrecomputedLevelRow(
                    symbol=symbol,
                    date=day,
                    level_price=lv.price,
                    level_type=lv.type,
                    total_score=lv.total_score,
                    trend=trend,
                    energy=energy_res.context,
                    path_ratio=path_ratio,
                    atr=atr,
                    prev_close=prev_close,
                )
            )

        results.append(
            PrecomputedDay(
                symbol=symbol,
                date=day,
                atr=atr,
                prev_close=prev_close,
                close=current_close,
                path_ratio=path_ratio,
                trend=trend,
                key_points=kps,
                strong_levels=strong,
                rows=rows,
            )
        )

    logger.info("Precomputed %d days for %s", len(results), symbol)
    return results


def save_to_db(session: Session, days: list[PrecomputedDay]) -> int:
    """Insert all level rows into gerchik_levels.

    Clears existing rows for the same (symbol, dates) first, then inserts.
    Returns total inserted row count.
    """
    from app.models.gerchik_level import GerchikLevel

    if not days:
        return 0

    symbols = {d.symbol for d in days}
    dates = {d.date for d in days}
    session.execute(
        delete(GerchikLevel).where(
            GerchikLevel.symbol.in_(symbols),
            GerchikLevel.date.in_(dates),
        )
    )

    inserted = 0
    for day in days:
        for r in day.rows:
            session.add(
                GerchikLevel(
                    symbol=r.symbol,
                    date=r.date,
                    level_price=r.level_price,
                    level_type=r.level_type.value,
                    total_score=r.total_score,
                    trend=r.trend,
                    energy=r.energy.value,
                    path_ratio=r.path_ratio,
                    atr=r.atr,
                    prev_close=r.prev_close,
                )
            )
            inserted += 1

    session.commit()
    return inserted
