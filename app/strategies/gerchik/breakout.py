"""Breakout pattern detector: accumulation + pending Stop order.

The pattern:
1. Energy = ACCUMULATION or COMPRESSION (market is "loading" positions
   before a move).
2. Price is near a level but hasn't broken through yet.
3. Optionally: a strong move preceded the approach (move > 3 ATR over
   the last N bars) — in this case, we require more confirmation bars
   after the breakout (2 instead of 1).

We don't place the order here. We only detect the setup and produce a
"pending Stop order" spec. The actual trigger is checked on M1 bars
(see m1_stop_timing.py).

Why this design:
- Real Stop orders are native to exchanges and execute on touch.
- In backtesting, we simulate them by checking each M1 bar inside the
  M5 where the setup is active.
- `strong_move_before` raises the bar for post-entry confirmation, but
  cannot delay entry (Stop order triggers on touch — that's the point).
"""

import logging
from typing import Literal

import pandas as pd
from pydantic import BaseModel

from app.strategies.gerchik.config import GerchikConfig

logger = logging.getLogger(__name__)

Direction = Literal["LONG", "SHORT"]


class BreakoutSetup(BaseModel):
    """Detected breakout setup with a pending Stop order spec."""

    level: float
    direction: Direction
    stop_order_price: float  # level ± offset
    detected_at_bar: int  # M5-bar index where setup was detected
    expires_at_bar: int  # detected_at_bar + max_wait_bars
    setup_reason: str  # "accumulation" | "compression"
    strong_move_before: bool  # move > strong_move_atr × ATR
    calculated_stop_size: float  # 0.2% of level (methodology)
    max_allowed_stop: float  # = calculated_stop_size


def _normalize_m5(m5_bars: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns; sort by timestamp if present; reset index."""
    df = m5_bars.copy()
    df.columns = [c.lower() for c in df.columns]
    if "timestamp" in df.columns:
        df = df.sort_values("timestamp").reset_index(drop=True)
    return df


def _compute_offset(level: float, config: GerchikConfig) -> float:
    """Stop order offset = max(ticks*tick_size, pct*level)."""
    return max(
        config.breakout_stop_order_offset_ticks * config.tick_size,
        config.breakout_stop_order_offset_pct * level,
    )


def _check_strong_move_before(
    m5_bars: pd.DataFrame,
    level: float,
    direction: Direction,
    atr: float,
    config: GerchikConfig,
) -> bool:
    """Was there a strong move toward the level in the last N bars?

    LONG setup (level below price, breakout upward):
        Look at last N bars. If close rose from (level - move) to level
        by more than strong_move_atr × ATR -> strong.

    SHORT setup (level above price, breakout downward):
        Mirror.
    """
    if atr <= 0:
        return False
    n = min(len(m5_bars), config.breakout_strong_move_lookback)
    if n < 2:
        return False

    tail = m5_bars.tail(n)
    closes = tail["close"].to_numpy(dtype=float)
    move_size = abs(float(closes[-1]) - float(closes[0]))
    return move_size > config.breakout_strong_move_atr * atr


def detect_breakout_setup(
    m5_bars: pd.DataFrame,
    level: float,
    direction: Direction,
    energy: str,
    atr: float,
    config: GerchikConfig,
) -> BreakoutSetup | None:
    """Try to detect a breakout setup on the last M5 bar.

    Returns BreakoutSetup if all conditions pass, else None.

    `m5_bars` must be sorted ascending by timestamp.
    """
    if m5_bars is None or len(m5_bars) == 0:
        return None

    df = _normalize_m5(m5_bars)
    last = df.iloc[-1]
    last_close = float(last["close"])
    last_high = float(last["high"])
    last_low = float(last["low"])

    # --- Step 1: energy gate ---
    energy_lower = energy.lower()
    if energy_lower not in ("accumulation", "compression"):
        return None
    setup_reason = energy_lower

    # --- Step 2: price hasn't broken through level yet ---
    # Also: if price is already FAR from the level (> cancel_distance × stop),
    # setup has no chance — the strategy will cancel it anyway. Not detect.
    calc_stop = level * config.stop_loss_pct
    max_distance = config.breakout_cancel_distance * calc_stop

    if direction == "LONG":
        if last_close >= level:
            return None
        if last_high >= level:  # wick already touched/crossed — too late
            return None
        if (level - last_close) > max_distance:
            return None  # price too far below the level
    else:  # SHORT
        if last_close <= level:
            return None
        if last_low <= level:
            return None
        if (last_close - level) > max_distance:
            return None  # price too far above the level

    # --- Step 3: strong move check ---
    strong_move = _check_strong_move_before(
        df,
        level,
        direction,
        atr,
        config,
    )

    # --- Step 4: stop order price ---
    offset = _compute_offset(level, config)
    if direction == "LONG":
        stop_order_price = level + offset
    else:
        stop_order_price = level - offset

    # --- Step 5: expiry ---
    detected_at_bar = len(df) - 1
    expires_at_bar = detected_at_bar + config.breakout_max_wait_bars

    # --- Step 6: pre-calculated stop size (0.2% of level) ---
    calculated_stop_size = level * config.stop_loss_pct

    return BreakoutSetup(
        level=level,
        direction=direction,
        stop_order_price=stop_order_price,
        detected_at_bar=detected_at_bar,
        expires_at_bar=expires_at_bar,
        setup_reason=setup_reason,
        strong_move_before=strong_move,
        calculated_stop_size=calculated_stop_size,
        max_allowed_stop=calculated_stop_size,
    )
