"""Build continuous futures series with rolling by volume.

A continuous series concatenates candles from different futures contracts
on the same underlying asset, so that a long, uninterrupted price history
is available for backtesting.

Two concatenation methods:
- "concat": raw concat, no price adjustment. Gaps at roll dates remain.
- "ratio": historical prices are multiplied by a ratio computed at each
  roll, removing gaps (back-adjusted series).

Rolling rule:
- On each trading day, pick the contract with the highest daily volume.
- If the currently active contract is within `roll_offset_days` of its
  expiration date, switch to the next-most-liquid contract.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.candle import Candle
from app.models.instrument_spec import InstrumentSpec

logger = logging.getLogger(__name__)


@dataclass
class RollEvent:
    """One roll from old to new contract."""

    date: date
    old_secid: str
    new_secid: str
    old_close: float
    new_open: float
    ratio: float  # new_open / old_close


class ContinuousSeriesBuilder:
    """Build a continuous futures series for a given base asset."""

    def __init__(
        self,
        base_asset: str,
        roll_offset_days: int = 5,
    ) -> None:
        self.base_asset = base_asset.upper()
        self.roll_offset_days = roll_offset_days
        self._specs: dict[str, InstrumentSpec] = {}
        self._rolls: list[RollEvent] = []

    # ---------- public API ----------

    def build(
        self,
        timeframe: int,
        start: date,
        end: date,
        method: Literal["concat", "ratio"] = "ratio",
    ) -> pd.DataFrame:
        """Build the continuous series and return a DataFrame.

        Columns: timestamp, secid, open, high, low, close, volume.
        """
        specs = self._load_specs()
        if not specs:
            raise ValueError(
                f"No instrument specs found for base asset {self.base_asset}. "
                f"Run scripts/load_futures.py --load-specs first."
            )

        self._specs = {s.symbol: s for s in specs}
        secids = list(self._specs.keys())

        raw = self._load_candles(secids, timeframe, start, end)
        if raw.empty:
            raise ValueError(
                f"No futures candles found for base asset {self.base_asset} "
                f"in {start}..{end}, timeframe={timeframe}."
            )

        active_per_day = self._pick_active_contracts(raw)
        series = self._assemble(raw, active_per_day)

        if method == "ratio":
            series = self._apply_ratio(series)

        return series

    def roll_events(self) -> list[RollEvent]:
        """Return the list of roll events after build() has been called."""
        return self._rolls

    # ---------- internals ----------

    def _load_specs(self) -> list[InstrumentSpec]:
        with SessionLocal() as db:
            stmt = select(InstrumentSpec).where(
                InstrumentSpec.asset_type == "future",
                InstrumentSpec.base_asset == self.base_asset,
            )
            return list(db.execute(stmt).scalars().all())

    def _load_candles(
        self,
        secids: list[str],
        timeframe: int,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        with SessionLocal() as db:
            stmt = (
                select(Candle)
                .where(
                    Candle.symbol.in_(secids),
                    Candle.asset_type == "future",
                    Candle.timeframe == timeframe,
                    Candle.timestamp >= datetime.combine(start, datetime.min.time()),
                    Candle.timestamp <= datetime.combine(end, datetime.max.time()),
                )
                .order_by(Candle.timestamp.asc())
            )
            rows = db.execute(stmt).scalars().all()

        if not rows:
            return pd.DataFrame(
                columns=[
                    "secid",
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            )

        return pd.DataFrame(
            {
                "secid": [r.symbol for r in rows],
                "timestamp": [r.timestamp for r in rows],
                "open": [float(r.open) for r in rows],
                "high": [float(r.high) for r in rows],
                "low": [float(r.low) for r in rows],
                "close": [float(r.close) for r in rows],
                "volume": [int(r.volume) for r in rows],
            }
        )

    def _pick_active_contracts(self, raw: pd.DataFrame) -> dict[date, str]:
        """Return {date: secid} — the active contract on each trading day."""
        raw = raw.copy()
        raw["date"] = pd.to_datetime(raw["timestamp"]).dt.date

        volumes = raw.groupby(["date", "secid"])["volume"].sum().reset_index()
        dates = sorted(volumes["date"].unique())

        active_per_day: dict[date, str] = {}
        active: str | None = None

        for d in dates:
            day_vol = volumes[volumes["date"] == d]

            if active is None:
                active = day_vol.sort_values("volume", ascending=False).iloc[0]["secid"]

            spec = self._specs[active]
            exp_date = spec.expiration_date.date() if spec.expiration_date is not None else None

            if exp_date is not None:
                days_to_exp = (exp_date - d).days
                if days_to_exp <= self.roll_offset_days:
                    candidates = day_vol[day_vol["secid"] != active].copy()
                    candidates["exp"] = candidates["secid"].map(
                        lambda s: (
                            self._specs[s].expiration_date.date()
                            if self._specs[s].expiration_date is not None
                            else None
                        )
                    )
                    candidates = candidates[candidates["exp"].apply(lambda e: e is None or e > d)]
                    if not candidates.empty:
                        next_active = candidates.sort_values("volume", ascending=False).iloc[0][
                            "secid"
                        ]
                        old_candle = raw[(raw["date"] == d) & (raw["secid"] == active)]
                        new_candle = raw[(raw["date"] == d) & (raw["secid"] == next_active)]
                        if not old_candle.empty and not new_candle.empty:
                            old_close = float(old_candle["close"].iloc[0])
                            new_open = float(new_candle["open"].iloc[0])
                            ratio = new_open / old_close if old_close else 1.0
                            self._rolls.append(
                                RollEvent(
                                    date=d,
                                    old_secid=active,
                                    new_secid=next_active,
                                    old_close=old_close,
                                    new_open=new_open,
                                    ratio=ratio,
                                )
                            )
                        active = next_active

            active_per_day[d] = active

        return active_per_day

    def _assemble(
        self,
        raw: pd.DataFrame,
        active_per_day: dict[date, str],
    ) -> pd.DataFrame:
        """Take the active contract's candle for each trading day."""
        raw = raw.copy()
        raw["date"] = pd.to_datetime(raw["timestamp"]).dt.date
        raw["_active"] = raw["date"].map(active_per_day)
        selected = raw[raw["secid"] == raw["_active"]].copy()
        selected = selected.drop(columns=["_active", "date"])
        selected = selected.sort_values("timestamp").reset_index(drop=True)
        return selected

    def _apply_ratio(self, series: pd.DataFrame) -> pd.DataFrame:
        """Back-adjust prices so the series has no gaps at roll dates."""
        if not self._rolls:
            return series.copy()

        series = series.copy()
        series["_date"] = pd.to_datetime(series["timestamp"]).dt.date

        rolls_sorted = sorted(self._rolls, key=lambda r: r.date)
        cumulative = [1.0] * len(rolls_sorted)
        acc = 1.0
        for i in range(len(rolls_sorted) - 1, -1, -1):
            cumulative[i] = acc
            acc *= rolls_sorted[i].ratio

        for i, roll in enumerate(rolls_sorted):
            mask = series["_date"] < roll.date
            factor = cumulative[i]
            for col in ("open", "high", "low", "close"):
                series.loc[mask, col] = series.loc[mask, col] * factor

        series = series.drop(columns=["_date"])
        return series
