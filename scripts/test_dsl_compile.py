"""Test: compile a YAML strategy and run a backtest on SBER."""

from datetime import date

import backtrader as bt
import yaml

from app.backtest.feed import df_to_bt_feed
from app.services.candle_repository import CandleRepository
from app.strategies.builder.compiler import compile_strategy
from app.strategies.builder.config import StrategyConfig


YAML_CONFIG = """
name: "RSI Mean Reversion"
description: "Buy on RSI oversold, sell on RSI overbought"
version: 1
entry:
  logic: AND
  conditions:
    - left: { indicator: RSI, params: { period: 14 } }
      operator: "<"
      right: { constant: 35 }
    - left: { price: close }
      operator: ">"
      right: { indicator: SMA, params: { period: 100 } }
exit:
  logic: OR
  conditions:
    - left: { indicator: RSI, params: { period: 14 } }
      operator: ">"
      right: { constant: 65 }
filters: []
risk:
  stop_type: atr
  atr_period: 14
  atr_multiplier: 1.5
  take_profit_rr: 2.0
  risk_per_trade_pct: 0.5
direction:
  long: true
  short: false
intraday_only: true
"""


def main() -> None:
    cfg = StrategyConfig.model_validate(yaml.safe_load(YAML_CONFIG))
    print(f"Config: {cfg.name}")

    CompiledStrategy = compile_strategy(cfg)
    print(f"Compiled class: {CompiledStrategy.__name__}")
    print(f"MRO: {[c.__name__ for c in CompiledStrategy.__mro__]}")

    # Load SBER daily.
    repo = CandleRepository()
    df = repo.get_dataframe(
        symbol="SBER",
        timeframe=24,
        start=date(2024, 1, 1),
        end=date(2026, 9, 28),
    )
    if df.empty:
        print("No data. Load SBER first.")
        return
    print(f"Loaded {len(df)} candles.")

    cerebro = bt.Cerebro(runonce=False)
    cerebro.adddata(df_to_bt_feed(df))
    cerebro.addstrategy(CompiledStrategy)
    cerebro.broker.setcash(100_000.0)
    cerebro.broker.setcommission(commission=0.001)

    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="dd")

    print(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")
    results = cerebro.run()
    final = cerebro.broker.getvalue()
    strat = results[0]

    ta = strat.analyzers.trades.get_analysis()
    dd = strat.analyzers.dd.get_analysis()

    total = int(ta.get("total", {}).get("closed", 0) or 0)
    won = int(ta.get("won", {}).get("total", 0) or 0)
    max_dd = float(dd.get("max", {}).get("drawdown", 0.0) or 0.0)

    print(f"Final Portfolio Value:   {final:.2f}")
    print(f"PnL:                     {final - 100_000:.2f}")
    print(f"Trades:                  {total} (won {won})")
    print(f"Win rate:                {(won / total * 100) if total else 0:.1f}%")
    print(f"Max drawdown:            {max_dd:.2f}%")

    if strat.risk is not None:
        rs = strat.risk.get_stats()
        print(f"Stops hit:               {rs.get('stops_hit', 0)}")
        print(f"Take-profits hit:        {rs.get('take_profits_hit', 0)}")
        print(f"Skipped by ATR:          {rs.get('skipped_by_atr', 0)}")
        print(f"Avg risk / trade:        {rs.get('avg_risk_per_trade', 0.0):.3f}%")


if __name__ == "__main__":
    main()
