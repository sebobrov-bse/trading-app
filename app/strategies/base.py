"""Base Backtrader strategy with shared logging and order tracking."""

import backtrader as bt


class BaseStrategy(bt.Strategy):
    """Base class for all strategies.

    Tracks closed trades with reliable entry/exit info by remembering
    the executed orders in notify_order, because in some Backtrader
    configurations trade.history is not populated.
    """

    def __init__(self) -> None:
        self.order = None
        self.trade_log: list[dict] = []
        self.bars_in_market: int = 0
        self._last_entry: dict | None = None
        self._last_exit: dict | None = None

    def log(self, txt: str) -> None:
        """Log a message with the current bar's date."""
        dt = self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()}, {txt}")

    def notify_order(self, order) -> None:
        """Handle order lifecycle and remember entry/exit prices."""
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            dt = self.datas[0].datetime.datetime(0)
            side = "BUY" if order.isbuy() else "SELL"
            self.log(
                f"{side} EXECUTED, price={order.executed.price:.2f}, "
                f"size={order.executed.size:.0f}, "
                f"commission={order.executed.comm:.2f}"
            )
            info = {
                "time": dt,
                "price": float(order.executed.price),
                "size": abs(float(order.executed.size)),
            }
            if order.isbuy():
                self._last_entry = info
            else:
                self._last_exit = info
        elif order.status == order.Canceled:
            self.log("ORDER CANCELED")
        elif order.status == order.Margin:
            self.log("ORDER REJECTED: MARGIN")
        elif order.status == order.Rejected:
            self.log("ORDER REJECTED")

        if order.status in (
            order.Completed,
            order.Canceled,
            order.Margin,
            order.Rejected,
        ):
            self.order = None

    def notify_trade(self, trade) -> None:
        """Append a rich record to trade_log when a trade closes."""
        if not trade.isclosed:
            return

        # Use the orders captured in notify_order; fall back to trade
        # attributes if a signal went missing (should not happen).
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
        pnl_pct = (
            (trade.pnlcomm / position_value * 100) if position_value else 0.0
        )

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

        self._last_entry = None
        self._last_exit = None