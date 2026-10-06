"""Risk management configuration.

All parameters are validated by Pydantic: invalid ranges raise on
construction, not later during a backtest.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RiskConfig(BaseModel):
    """Parameters for risk management in a strategy.

    Set `use_risk_management=False` to disable all risk logic and fall
    back to plain `self.buy()` / `self.sell()` behaviour.
    """

    # ---- master switch ----
    use_risk_management: bool = True

    # ---- stop type ----
    stop_type: Literal["atr", "percent", "n_bars"] = "atr"

    # ATR-based stop
    atr_period: int = Field(14, ge=2, le=200)
    atr_multiplier: float = Field(1.5, gt=0.1, le=10.0)

    # Percent-based stop
    stop_percent: float = Field(0.02, gt=0.001, le=0.5)

    # N-bars stop
    stop_n_bars: int = Field(10, ge=2, le=200)

    # ---- take profit ----
    take_profit_rr: float = Field(3.0, gt=0.5, le=20.0)

    # ---- position sizing ----
    risk_per_trade_pct: float = Field(0.5, gt=0.01, le=10.0)

    # ---- global limits ----
    max_daily_loss_pct: float = Field(1.0, gt=0.0, le=50.0)
    max_weekly_loss_pct: float = Field(5.0, gt=0.0, le=100.0)
    max_monthly_loss_pct: float = Field(10.0, gt=0.0, le=100.0)

    # ---- trailing / breakeven ----
    move_to_breakeven_after_rr: float = Field(1.0, ge=0.0, le=10.0)
    trailing_after_rr: float = Field(3.0, ge=0.0, le=20.0)
    trailing_atr_multiplier: float = Field(1.0, gt=0.0, le=10.0)

    # ---- position count ----
    max_positions: int = Field(3, ge=1, le=100)

    # ---- ATR gate ----
    # Reject trades where the stop is wider than max_stop_to_atr_ratio * ATR.
    # Protects against stops that are too far (risk per trade would shrink
    # the position size to nothing).
    check_atr: bool = True
    max_stop_to_atr_ratio: float = Field(5.0, ge=0.1, le=100.0)

    # ---- direction / session ----
    long_only: bool = False
    short_only: bool = False
    intraday_only: bool = True

    @model_validator(mode="after")
    def check_conflicts(self) -> "RiskConfig":
        if self.long_only and self.short_only:
            raise ValueError("long_only and short_only cannot both be True")
        if self.max_daily_loss_pct > self.max_weekly_loss_pct:
            raise ValueError("max_daily_loss_pct must be <= max_weekly_loss_pct")
        if self.max_weekly_loss_pct > self.max_monthly_loss_pct:
            raise ValueError("max_weekly_loss_pct must be <= max_monthly_loss_pct")
        return self
