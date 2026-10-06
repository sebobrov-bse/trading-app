"""Test: build the same RSI strategy via fluent Builder."""

from datetime import date

import backtrader as bt

from app.backtest.feed import df_to_bt_feed
from app.services.candle_repository import CandleRepository
from app.strategies.builder import (
    Price,
    RSI,
    SMA,
    StrategyBuilder,
)
from app.strategies.builder.compiler import compile_strategy


def main() -> None:
    config = (
        StrategyBuilder()
        .name("RSI Mean Reversion (Builder)")
        .description("Same as YAML, but built programmatically")
        .entry_and()
        .condition(RSI(14), "<", 35)
        .condition(Price.close(), ">", SMA(100))
        .end()
        .exit_or()
        .condition(RSI(14), ">", 65)
        .end()
        .risk(
            stop_type="atr",
            atr_period=14,
            atr_multiplier=1.5,
            take_profit_rr=2.0,
            risk_per_trade_pct=0.5,
        )
        .direction(long=True, short=False)
        .build()
    )

    print(f"Config: {config.name}")
    print(f"Entry: {config.entry.logic}, {len(config.entry.conditions)} conditions")
    print(f"Exit:  {config.exit.logic}, {len(config.exit.conditions)} conditions")
    print(f"Risk:  stop={config.risk.stop_type}, mult={config.risk.atr_multiplier}")

    CompiledStrategy = compile_strategy(config)
    print(f"Compiled: {CompiledStrategy.__name__}")

    repo = CandleRepository()
    df = repo.get_dataframe(
        symbol="SBER",
        timeframe=24,
        start=date(2024, 1, 1),
        end=date(2026, 9, 28),
    )
    if df.empty:
        print("No data.")
        return

    cerebro = bt.Cerebro(runonce=False)
    cerebro.adddata(df_to_bt_feed(df))
    cerebro.addstrategy(CompiledStrategy)
    cerebro.broker.setcash(100_000.0)
    cerebro.broker.setcommission(commission=0.001)
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")

    results = cerebro.run()
    final = cerebro.broker.getvalue()
    strat = results[0]

    ta = strat.analyzers.trades.get_analysis()
    dd = strat.analyzers.dd.get_analysis()
    total = int(ta.get("total", {}).get("closed", 0) or 0)
    won = int(ta.get("won", {}).get("total", 0) or 0)
    max_dd = float(dd.get("max", {}).get("drawdown", 0.0) or 0.0)

    print(f"Final: {final:.2f} | PnL: {final - 100_000:.2f}")
    print(f"Trades: {total} (won {won}) | Max DD: {max_dd:.2f}%")
    if strat.risk is not None:
        rs = strat.risk.get_stats()
        print(f"Avg risk / trade: {rs.get('avg_risk_per_trade', 0.0):.3f}%")


if __name__ == "__main__":
    main()
