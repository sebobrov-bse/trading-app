"""Registry of supported indicators.

Each indicator has a name, a params spec (for validation), and a
factory function that creates a Backtrader indicator from bt_data
and a params dict.

The factory is called by the compiler when building a strategy.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import backtrader as bt


@dataclass
class ParamSpec:
    """Validation spec for a single indicator parameter."""

    min: float | int | None = None
    max: float | int | None = None
    default: Any = None
    required: bool = False


@dataclass
class IndicatorSpec:
    """Spec + factory for a supported indicator."""

    name: str
    params: dict[str, ParamSpec] = field(default_factory=dict)
    factory: Callable[[bt.LineSeries, dict[str, Any]], Any] | None = None


# ---- factories (short lambdas / helpers) ----


def _sma(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.SMA(data, period=int(params["period"]))


def _ema(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.EMA(data, period=int(params["period"]))


def _wma(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.WMA(data, period=int(params["period"]))


def _rsi(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.RSI(data, period=int(params["period"]))


def _stochastic(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.Stochastic(
        data,
        period=int(params["period"]),
        period_dfast=int(params.get("period_dfast", 3)),
        period_dslow=int(params.get("period_dslow", 3)),
    )


def _cci(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.CCI(data, period=int(params["period"]))


def _macd(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.MACD(
        data,
        period_me1=int(params.get("fast", 12)),
        period_me2=int(params.get("slow", 26)),
        period_signal=int(params.get("signal", 9)),
    )


def _adx(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.ADX(data, period=int(params["period"]))


def _bollinger(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.BollingerBands(
        data,
        period=int(params.get("period", 20)),
        devfactor=float(params.get("devfactor", 2.0)),
    )


def _atr(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.ATR(data, period=int(params.get("period", 14)))


def _volume_sma(data: bt.LineSeries, params: dict) -> Any:
    return bt.indicators.SMA(data, period=int(params.get("period", 20)))


# ---- registry ----

INDICATOR_REGISTRY: dict[str, IndicatorSpec] = {
    "SMA": IndicatorSpec(
        "SMA",
        {"period": ParamSpec(min=2, max=500, default=20, required=True)},
        _sma,
    ),
    "EMA": IndicatorSpec(
        "EMA",
        {"period": ParamSpec(min=2, max=500, default=20, required=True)},
        _ema,
    ),
    "WMA": IndicatorSpec(
        "WMA",
        {"period": ParamSpec(min=2, max=500, default=20, required=True)},
        _wma,
    ),
    "RSI": IndicatorSpec(
        "RSI",
        {"period": ParamSpec(min=2, max=100, default=14, required=True)},
        _rsi,
    ),
    "Stochastic": IndicatorSpec(
        "Stochastic",
        {
            "period": ParamSpec(min=2, max=200, default=14, required=True),
            "period_dfast": ParamSpec(min=1, max=20, default=3),
            "period_dslow": ParamSpec(min=1, max=20, default=3),
        },
        _stochastic,
    ),
    "CCI": IndicatorSpec(
        "CCI",
        {"period": ParamSpec(min=2, max=200, default=20, required=True)},
        _cci,
    ),
    "MACD": IndicatorSpec(
        "MACD",
        {
            "fast": ParamSpec(min=2, max=100, default=12),
            "slow": ParamSpec(min=3, max=300, default=26),
            "signal": ParamSpec(min=2, max=100, default=9),
        },
        _macd,
    ),
    "ADX": IndicatorSpec(
        "ADX",
        {"period": ParamSpec(min=2, max=100, default=14, required=True)},
        _adx,
    ),
    "BollingerBands": IndicatorSpec(
        "BollingerBands",
        {
            "period": ParamSpec(min=2, max=200, default=20),
            "devfactor": ParamSpec(min=0.5, max=5.0, default=2.0),
        },
        _bollinger,
    ),
    "ATR": IndicatorSpec(
        "ATR",
        {"period": ParamSpec(min=2, max=100, default=14)},
        _atr,
    ),
    "VolumeSMA": IndicatorSpec(
        "VolumeSMA",
        {"period": ParamSpec(min=2, max=200, default=20)},
        _volume_sma,
    ),
}
