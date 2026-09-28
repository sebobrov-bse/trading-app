"""Base Backtrader strategy with shared logging and order tracking."""

import backtrader as bt


class BaseStrategy(bt.Strategy):
    """Base class for all strategies.

    Provides self.order, self.trade_log, self.log(),
    and default notify_order / notify_trade handlers.
    """

    def __init__(self) -> None:
        self.order = None
        self.trade_log: list[dict] = []
        self.bars_in_market: int = 0  # for exposure

    def log(self, txt: str) -> None:
        """Log a message with the current bar's date."""
        dt = self.datas[0].datetime.date(0)
        print(f"{dt.isoformat()}, {txt}")

    def notify_order(self, order) -> None:
        """Handle order lifecycle."""
        if order.status in (order.Submitted, order.Accepted):
            return

        if order.status == order.Completed:
            side = "BUY" if order.isbuy() else "SELL"
            self.log(
                f"{side} EXECUTED, price={order.executed.price:.2f}, "
                f"size={order.executed.size:.0f}, "
                f"commission={order.executed.comm:.2f}"
            )
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

        # In some edge cases trade.history may be empty. Fall back to
        # direct attributes, which Backtrader always populates.
        if trade.history:
            entry_dt = trade.history[0].event.dt
            exit_dt = trade.history[-1].event.dt
            entry_price = float(trade.history[0].event.price)
            exit_price = float(trade.history[-1].event.price)
            closed_size = abs(float(trade.history[-1].event.size))
        else:
            entry_dt = trade.dtopen
            exit_dt = trade.dtclose
            entry_price = float(trade.price)
            exit_price = float(trade.price)
            closed_size = abs(float(trade.size)) or 0.0

        position_value = entry_price * closed_size
        pnl_pct = (trade.pnlcomm / position_value * 100) if position_value else 0.0

        self.trade_log.append(
            {
                "entry_time": bt.num2date(entry_dt).isoformat(),
                "exit_time": bt.num2date(exit_dt).isoformat(),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "size": closed_size,
                "bars_held": int(trade.barlen),
                "pnl": float(trade.pnl),
                "pnl_net": float(trade.pnlcomm),
                "pnl_percent": float(pnl_pct),
            }
        )
