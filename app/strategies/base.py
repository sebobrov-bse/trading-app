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
        """Log trade open/close and append closed trades to trade_log."""
        if not trade.isclosed:
            return

        # trade.size is 0 after close. Recover the size from history.
        closed_size = 0.0
        if trade.history:
            closed_size = trade.history[-1].event.size

        self.trade_log.append(
            {
                "date": self.datas[0].datetime.date(0).isoformat(),
                "size": closed_size,
                "price": trade.price,
                "pnl": trade.pnl,
                "pnl_net": trade.pnlcomm,
            }
        )
        self.log(
            f"TRADE CLOSED, size={closed_size:.0f}, "
            f"price={trade.price:.2f}, "
            f"pnl={trade.pnl:.2f}, "
            f"pnl_net={trade.pnlcomm:.2f}"
        )