"""Base Backtrader strategy with risk management, logging, and order tracking."""

import logging
from datetime import date
from typing import Literal

import backtrader as bt

from app.risk.config import RiskConfig
from app.risk.manager import RiskManager

logger = logging.getLogger(__name__)

Direction = Literal["long", "short"]


class BaseStrategy(bt.Strategy):
    """Base class for all strategies.

    Provides:
    - self.order: reference to a plain market order (None if idle).
    - self.trade_log: list of closed trades for post-run analysis.
    - self.risk: RiskManager or None (if use_risk_management=False).
    - safe_buy / safe_close: risk-aware entry and exit.
    - set_stop_loss / set_take_profit: bracket orders.
    - move_stop_to_breakeven / update_trailing_stop: dynamic stops.

    Subclasses must define `params` and, optionally, override `next()`.
    """

    params = (
        ("risk_config", None),  # RiskConfig instance or None
    )

    def __init__(self) -> None:
        # ---- order tracking ----
        self.order: bt.Order | None = None
        self.trade_log: list[dict] = []
        self.bars_in_market: int = 0
        self._last_entry: dict | None = None
        self._last_exit: dict | None = None

        # ---- risk management ----
        cfg = self.p.risk_config
        if cfg is None:
            cfg = RiskConfig()
        self.risk_config: RiskConfig = cfg
        self.risk: RiskManager | None = RiskManager(self, cfg) if cfg.use_risk_management else None

        # ---- bracket order state ----
        self._entry_price: float | None = None
        self._stop_price: float | None = None
        self._tp_price: float | None = None
        self._stop_order: bt.Order | None = None
        self._tp_order: bt.Order | None = None
        self._direction: Direction | None = None
        self._breakeven_done: bool = False
        self._trailing_on: bool = False

    # ------------------------------------------------------------------
    #  Logging
    # ------------------------------------------------------------------

    def log(self, txt: str) -> None:
        """Log a message with the current bar's date."""
        dt = self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()}, {txt}")

    # ------------------------------------------------------------------
    #  Risk-aware order placement
    # ------------------------------------------------------------------

    def safe_buy(
        self,
        direction: Direction = "long",
        size: int | None = None,
    ) -> None:
        """Open a position with risk-based sizing, stop, and take-profit.

        If risk management is disabled, this falls back to plain buy/sell.
        """
        if self.order or self.position:
            return  # already in flight or in market

        entry_price = float(self.data.close[0])

        # No risk manager: plain entry.
        if self.risk is None:
            if direction == "long":
                self.order = self.buy()
            else:
                self.order = self.sell()
            return

        # Risk gate.
        allowed, reason = self.risk.can_open_position(direction)
        if not allowed:
            self.log(f"SKIP {direction}: {reason}")
            return

        # Size.
        stop_price = self.risk.calculate_stop_price(entry_price, direction)
        if size is None:
            size = self.risk.calculate_position_size(entry_price, stop_price)
        if size <= 0:
            self.log(f"SKIP {direction}: size=0")
            return

        tp_price = self.risk.calculate_take_profit_price(entry_price, stop_price, direction)

        # Entry.
        if direction == "long":
            self.order = self.buy(size=size)
        else:
            self.order = self.sell(size=size)

        # Remember bracket levels. Real stop/tp orders are placed in
        # notify_order after the entry is Completed, so Backtrader knows
        # the actual executed price.
        self._direction = direction
        self._stop_price = stop_price
        self._tp_price = tp_price
        self._pending_size = size
        self._breakeven_done = False
        self._trailing_on = False

    def safe_close(self) -> None:
        """Cancel all outstanding orders and close the current position."""
        for o in (self._stop_order, self._tp_order):
            if o is not None and o.alive():
                self.cancel(o)
        self._stop_order = None
        self._tp_order = None

        if self.position:
            self.order = self.close()

    # ------------------------------------------------------------------
    #  Bracket orders
    # ------------------------------------------------------------------

    def set_stop_loss(self, price: float, size: int) -> None:
        """Place a stop-loss order for a long or short position."""
        if size <= 0:
            return
        if self._direction == "long" or (self._direction is None and self.position.size > 0):
            self._stop_order = self.sell(size=size, exectype=bt.Order.Stop, price=price)
        else:
            self._stop_order = self.buy(size=size, exectype=bt.Order.Stop, price=price)
        self._stop_price = price

    def set_take_profit(self, price: float, size: int) -> None:
        """Place a take-profit limit order."""
        if size <= 0:
            return
        if self._direction == "long" or (self._direction is None and self.position.size > 0):
            self._tp_order = self.sell(size=size, exectype=bt.Order.Limit, price=price)
        else:
            self._tp_order = self.buy(size=size, exectype=bt.Order.Limit, price=price)
        self._tp_price = price

    # ------------------------------------------------------------------
    #  Dynamic stops
    # ------------------------------------------------------------------

    def move_stop_to_breakeven(self) -> None:
        """Cancel the stop and place a new one at the entry price."""
        if self._breakeven_done or self._entry_price is None:
            return
        if self._stop_order is None or not self._stop_order.alive():
            return

        size = abs(int(self.position.size))
        if size <= 0:
            return

        self.cancel(self._stop_order)
        self._stop_order = None
        self.set_stop_loss(self._entry_price, size)
        self._breakeven_done = True
        self.log(f"STOP -> breakeven @ {self._entry_price:.2f}")

    def update_trailing_stop(self) -> None:
        """Trail the stop behind the price once trailing is enabled."""
        if not self._trailing_on or self.risk is None:
            return
        if self._stop_order is None or not self._stop_order.alive():
            return

        size = abs(int(self.position.size))
        if size <= 0:
            return

        atr = self.risk._get_atr()
        if atr <= 0:
            return

        mult = self.risk_config.trailing_atr_multiplier
        current = float(self.data.close[0])
        new_stop: float

        if self._direction == "long":
            new_stop = current - mult * atr
            if self._stop_price is None or new_stop <= self._stop_price:
                return  # only move up
        else:
            new_stop = current + mult * atr
            if self._stop_price is None or new_stop >= self._stop_price:
                return  # only move down

        self.cancel(self._stop_order)
        self._stop_order = None
        self.set_stop_loss(new_stop, size)
        self.log(f"TRAIL stop -> {new_stop:.2f}")

    def _update_dynamic_levels(self) -> None:
        """Check R:R and enable breakeven / trailing if thresholds met."""
        if self.risk is None or self._entry_price is None:
            return
        if self._stop_price is None:
            return
        if not self.position:
            return

        risk = abs(self._entry_price - self._stop_price)
        if risk <= 0:
            return

        current = float(self.data.close[0])
        if self._direction == "long":
            rr = (current - self._entry_price) / risk
        else:
            rr = (self._entry_price - current) / risk

        if rr >= self.risk_config.move_to_breakeven_after_rr and not self._breakeven_done:
            self.move_stop_to_breakeven()

        if rr >= self.risk_config.trailing_after_rr and not self._trailing_on:
            self._trailing_on = True
            self.log(f"TRAILING enabled at RR={rr:.2f}")

    # ------------------------------------------------------------------
    #  Lifecycle hooks
    # ------------------------------------------------------------------

    def prenext(self) -> None:
        """Called by Backtrader while indicators are warming up."""
        # Allow on_new_bar to run even before indicators are ready.
        self._on_bar_start()

    def next(self) -> None:
        """Default strategy logic: do nothing. Subclasses override."""
        # Base next() also calls _on_bar_start in case the subclass
        # forgets to call super().next().
        self._on_bar_start()

    def _on_bar_start(self) -> None:
        """Update risk state and dynamic levels at the start of each bar."""
        if self.position:
            self.bars_in_market += 1

        if self.risk is not None:
            bar_date = self.datas[0].datetime.date(0)
            self.risk.on_new_bar(bar_date)

        # Dynamic levels check only when in position.
        if self.position:
            self._update_dynamic_levels()

    # ------------------------------------------------------------------
    #  Order callbacks
    # ------------------------------------------------------------------

    def notify_order(self, order) -> None:
        """Handle order lifecycle and place bracket orders after entry."""
        if order.status in (order.Submitted, order.Accepted):
            return

        # Entry completed: place stop and take-profit.
        if order.status == order.Completed and order == self.order:
            dt = self.datas[0].datetime.datetime(0)
            side = "BUY" if order.isbuy() else "SELL"
            exec_size = abs(float(order.executed.size))
            exec_price = float(order.executed.price)

            info = {"time": dt, "price": exec_price, "size": exec_size}
            if order.isbuy():
                self._last_entry = info
            else:
                self._last_exit = info

            self._entry_price = exec_price
            size = abs(int(order.executed.size))
            self.log(
                f"{side} EXECUTED, "
                f"price={order.executed.price:.2f}, size={size}, "
                f"comm={order.executed.comm:.2f}"
            )
            self.order = None

            if self._stop_price is not None and self._tp_price is not None:
                self.set_stop_loss(self._stop_price, size)
                self.set_take_profit(self._tp_price, size)

        # Bracket orders: cancel the sibling when one fires.
        elif order.status == order.Completed:
            dt = self.datas[0].datetime.datetime(0)
            exec_size = abs(float(order.executed.size))
            exec_price = float(order.executed.price)
            info = {"time": dt, "price": exec_price, "size": exec_size}

            if order.isbuy():
                self._last_entry = info
            else:
                self._last_exit = info

            if order == self._stop_order:
                self.log("STOP HIT")
                if self.risk is not None:
                    self.risk.stops_hit += 1
                if self._tp_order is not None and self._tp_order.alive():
                    self.cancel(self._tp_order)
                self._tp_order = None
                self._stop_order = None
            elif order == self._tp_order:
                self.log("TAKE-PROFIT HIT")
                if self.risk is not None:
                    self.risk.take_profits_hit += 1
                if self._stop_order is not None and self._stop_order.alive():
                    self.cancel(self._stop_order)
                self._stop_order = None
                self._tp_order = None

        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            if order == self.order:
                self.order = None
            if order == self._stop_order:
                self._stop_order = None
            if order == self._tp_order:
                self._tp_order = None

    def notify_trade(self, trade) -> None:
        """Log closed trades and update risk state."""
        if not trade.isclosed:
            return

        # Use the orders captured earlier; fall back to trade attributes.
        if self._last_entry and self._last_exit:
            entry_time = self._last_entry["time"]
            entry_price = self._last_entry["price"]
            size = self._last_entry["size"]
            exit_time = self._last_exit["time"]
            exit_price = self._last_exit["price"]
        else:
            entry_time = bt.num2date(trade.dtopen)
            exit_time = bt.num2date(trade.dtclose)
            entry_price = float(trade.price) if trade.price else 0.0
            exit_price = entry_price
            size = 0.0

        position_value = entry_price * size
        pnl_pct = (trade.pnlcomm / position_value * 100) if position_value else 0.0

        self.trade_log.append(
            {
                "entry_time": entry_time.isoformat(),
                "exit_time": exit_time.isoformat(),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "size": size,
                "bars_held": int(trade.barlen),
                "pnl": float(trade.pnl),
                "pnl_net": float(trade.pnlcomm),
                "pnl_percent": float(pnl_pct),
            }
        )

        # Update RiskManager.
        if self.risk is not None:
            risk_per_unit = (
                abs(self._entry_price - self._stop_price)
                if self._entry_price is not None and self._stop_price is not None
                else 0.0
            )
            rr_realized: float | None = None
            if risk_per_unit > 0 and size > 0:
                rr_realized = float(trade.pnlcomm) / (risk_per_unit * size)

            capital = float(self.broker.getvalue())
            risk_pct: float | None = None
            size_pct: float | None = None
            if capital > 0 and size > 0 and self._entry_price is not None:
                size_pct = (self._entry_price * size) / capital * 100.0
                if risk_per_unit > 0:
                    risk_pct = (risk_per_unit * size) / capital * 100.0

            self.risk.on_trade_closed(
                pnl=float(trade.pnlcomm),
                realized_rr=rr_realized,
                risk_pct=risk_pct,
                size_pct=size_pct,
            )

        self._last_entry = None
        self._last_exit = None
        self._entry_price = None
        self._stop_price = None
        self._tp_price = None
        self._direction = None
