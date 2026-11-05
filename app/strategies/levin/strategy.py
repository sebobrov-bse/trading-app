"""Larry Levin trading system.

Logic:
1. Pre-computed daily levels (Pivot, VA, POC) from 1m data.
2. One-Time Framing on 30m bars to confirm trend direction.
3. Entry on "return to Value Area" (previous bar outside, current inside).
4. Take-profit at opposite VA edge (or R1/R2/S1/S2).
5. Stop-loss as a fraction of the TP distance.
6. R:R filter — skip trades with R:R < min_rr.
7. Three stop variants: fixed, trailing_r, dynamic_minmax.
8. Time-based exit: max_hold_days, intraday_only.

Levels are passed via `params.levels_cache` (a dict {date: DailyLevels}),
precomputed by backtest_service using precompute_levels().
"""

import logging
from datetime import date

from app.strategies.base import BaseStrategy
from app.strategies.levin.levels import DailyLevels
from app.strategies.levin.one_time_framing import is_otf_up, is_otf_down
from app.strategies.levin.stop_manager import StopManager

logger = logging.getLogger(__name__)


class LevinSystem(BaseStrategy):
    """Larry Levin's Market Profile + OTF + Return to VA system."""

    # ---- Metadata (для UI и /api/v1/strategies) ----
    name = "levin"
    display_name = "Система Ларри Левина"
    description = "Market Profile + One-Time Framing + возврат в Value Area"
    tags = ["market_profile", "trend", "intraday_swing"]
    intraday_only = False
    direction = {"long": True, "short": True}

    params = (
        # Уровни
        ("levels_cache", None),  # dict[date, DailyLevels] — передаётся сервисом
        # OTF (резерв, сейчас используется строгий OTF на 4 барах)
        ("otf_bars", 2),
        # Стоп и тейк
        ("stop_variant", "fixed"),  # fixed | trailing_r | dynamic_minmax
        ("stop_fraction", 1.0 / 3.0),
        ("take_profit_mode", "opposite_va"),  # opposite_va | r1 | r2
        ("min_rr", 3.0),
        # Управление позицией
        ("max_hold_days", 3),
        ("intraday_only", False),
        ("direction_mode", "both"),  # long | short | both
    )

    params_meta = [
        {
            "name": "stop_variant",
            "type": "str",
            "default": "fixed",
            "description": "Вариант стопа: fixed | trailing_r | dynamic_minmax",
        },
        {
            "name": "stop_fraction",
            "type": "float",
            "default": 0.3333,
            "min": 0.1,
            "max": 1.0,
            "description": "Доля TP для SL (1/3 по умолчанию)",
        },
        {
            "name": "take_profit_mode",
            "type": "str",
            "default": "opposite_va",
            "description": "TP: opposite_va | r1 | r2",
        },
        {
            "name": "min_rr",
            "type": "float",
            "default": 3.0,
            "min": 1.0,
            "max": 10.0,
            "description": "Минимальный Risk/Reward",
        },
        {
            "name": "max_hold_days",
            "type": "int",
            "default": 3,
            "min": 1,
            "max": 30,
            "description": "Максимум дней в позиции",
        },
        {
            "name": "intraday_only",
            "type": "bool",
            "default": False,
            "description": "Закрывать в конце дня",
        },
        {
            "name": "direction_mode",
            "type": "str",
            "default": "both",
            "description": "long | short | both",
        },
    ]

    default_risk_config = {
        "use_risk_management": True,
        "stop_type": "atr",  # не используется: стратегия считает SL сама
        "atr_period": 14,
        "atr_multiplier": 1.5,
        "take_profit_rr": 3.0,
        "risk_per_trade_pct": 0.5,
        "max_positions": 3,
        "move_to_breakeven_after_rr": 0.0,  # отключено: stop_manager рулит
        "trailing_after_rr": 0.0,  # отключено: stop_manager рулит
        "check_atr": False,  # отключено: R:R проверяется в стратегии
        "long_only": False,
        "short_only": False,
        "intraday_only": False,
    }

    def __init__(self) -> None:
        super().__init__()
        self.levels_cache: dict[date, DailyLevels] = self.p.levels_cache or {}
        self._current_date: date | None = None
        self._current_levels: DailyLevels | None = None
        self._entry_date: date | None = None
        self._stop_manager: StopManager | None = None
        self._entry_direction: str | None = None

    # ------------------------------------------------------------------
    #  Day switch
    # ------------------------------------------------------------------

    def _on_new_day(self, current_date: date) -> None:
        self._current_date = current_date
        self._current_levels = self.levels_cache.get(current_date)
        if self._current_levels is None:
            logger.debug("%s: no levels for %s", self.__class__.__name__, current_date)

    # ------------------------------------------------------------------
    #  Signal checks
    # ------------------------------------------------------------------

    def _check_return_to_va_long(self) -> bool:
        if self._current_levels is None or len(self.data) < 2:
            return False
        prev_close = float(self.data.close[-1])
        curr_close = float(self.data.close[0])
        was_below = prev_close < self._current_levels.val
        now_inside = self._current_levels.val <= curr_close <= self._current_levels.vah
        return was_below and now_inside

    def _check_return_to_va_short(self) -> bool:
        if self._current_levels is None or len(self.data) < 2:
            return False
        prev_close = float(self.data.close[-1])
        curr_close = float(self.data.close[0])
        was_above = prev_close > self._current_levels.vah
        now_inside = self._current_levels.val <= curr_close <= self._current_levels.vah
        return was_above and now_inside

    # ------------------------------------------------------------------
    #  TP/SL calculation
    # ------------------------------------------------------------------

    def _compute_tp_long(self, entry: float) -> float | None:
        lv = self._current_levels
        if lv is None:
            return None
        mode = self.p.take_profit_mode
        if mode == "opposite_va":
            return lv.vah
        if mode == "r1":
            return lv.r1 if lv.r1 > entry else lv.r2
        if mode == "r2":
            return lv.r2
        return None

    def _compute_tp_short(self, entry: float) -> float | None:
        lv = self._current_levels
        if lv is None:
            return None
        mode = self.p.take_profit_mode
        if mode == "opposite_va":
            return lv.val
        if mode == "r1":
            return lv.s1 if lv.s1 < entry else lv.s2
        if mode == "r2":
            return lv.s2
        return None

    # ------------------------------------------------------------------
    #  Entry
    # ------------------------------------------------------------------

    def _try_enter_long(self) -> None:
        if not self._check_return_to_va_long():
            return
        if not is_otf_up(self.data, len(self)):
            return

        entry = float(self.data.close[0])
        tp = self._compute_tp_long(entry)
        if tp is None or tp <= entry:
            return

        sl = entry - (tp - entry) * self.p.stop_fraction
        risk = entry - sl
        if risk <= 0:
            return
        rr = (tp - entry) / risk
        if rr < self.p.min_rr - 1e-6:
            self.log(f"SKIP long: RR {rr:.2f} < {self.p.min_rr}")
            return

        self._entry_direction = "long"
        self.safe_buy(direction="long", custom_stop=sl, custom_tp=tp)

    def _try_enter_short(self) -> None:
        if not self._check_return_to_va_short():
            return
        if not is_otf_down(self.data, len(self)):
            return

        entry = float(self.data.close[0])
        tp = self._compute_tp_short(entry)
        if tp is None or tp >= entry:
            return

        sl = entry + (entry - tp) * self.p.stop_fraction
        risk = sl - entry
        if risk <= 0:
            return
        rr = (entry - tp) / risk
        if rr < self.p.min_rr - 1e-6:
            self.log(f"SKIP short: RR {rr:.2f} < {self.p.min_rr}")
            return

        self._entry_direction = "short"
        self.safe_buy(direction="short", custom_stop=sl, custom_tp=tp)

    # ------------------------------------------------------------------
    #  Position management
    # ------------------------------------------------------------------

    def _update_stop(self) -> None:
        if self._stop_manager is None or not self.position:
            return
        new_stop = self._stop_manager.update(
            current_price=float(self.data.close[0]),
            current_low=float(self.data.low[0]),
            current_high=float(self.data.high[0]),
        )
        if new_stop is None:
            return
        size = abs(int(self.position.size))
        if size <= 0:
            return
        if self._stop_order is not None and self._stop_order.alive():
            self.cancel(self._stop_order)
        self.set_stop_loss(new_stop, size)

    def _check_time_exit(self) -> None:
        if not self.position or self._entry_date is None or self._current_date is None:
            return
        if self.p.intraday_only and self._current_date != self._entry_date:
            self.safe_close()
            return
        if (self._current_date - self._entry_date).days >= self.p.max_hold_days:
            self.safe_close()

    # ------------------------------------------------------------------
    #  Main loop
    # ------------------------------------------------------------------

    def next(self) -> None:
        super().next()  # bars_in_market, risk.on_new_bar, dynamic levels

        bar_date = self.data.datetime.date(0)
        if bar_date != self._current_date:
            self._on_new_day(bar_date)

        if self.position:
            self._update_stop()
            self._check_time_exit()
            return

        if self.order:
            return
        if self._current_levels is None:
            return

        mode = self.p.direction_mode
        if mode in ("long", "both"):
            self._try_enter_long()
        if mode in ("short", "both") and not self.position:
            self._try_enter_short()

    # ------------------------------------------------------------------
    #  Lifecycle
    # ------------------------------------------------------------------

    def notify_order(self, order) -> None:
        super().notify_order(order)

        # After entry Completed: create StopManager.
        if (
            order.status == order.Completed
            and self._entry_direction is not None
            and self._entry_price is not None
            and self._stop_manager is None
        ):
            self._entry_date = self._current_date
            direction = self._entry_direction or "long"
            self._stop_manager = StopManager(
                variant=self.p.stop_variant,
                direction=direction,
                entry_price=self._entry_price,
                initial_stop=self._stop_price or self._entry_price,
                take_profit=self._tp_price or self._entry_price,
                current_stop=self._stop_price or self._entry_price,
            )

    def notify_trade(self, trade) -> None:
        super().notify_trade(trade)
        if trade.isclosed:
            self._stop_manager = None
            self._entry_date = None
            self._entry_direction = None
