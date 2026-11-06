"""Gerchik system configuration.

All numeric parameters for the Gerchik precomputation live here.
Modules receive a GerchikConfig instance and read from it — no
hardcoded magic numbers anywhere else in the codebase.

Defaults follow Larry Levin / Gerchik methodology as described in
S.2a spec. Override at runtime for grid optimization (S.2e).
"""

from pydantic import BaseModel, Field


class GerchikConfig(BaseModel):
    """All parameters for the Gerchik precomputation pipeline."""

    # ---- ATR ----
    atr_period: int = Field(default=5, ge=2, le=30)
    atr_small_k: float = Field(default=0.333, gt=0, lt=1)
    atr_big_k: float = Field(default=2.0, gt=1, lt=10)
    atr_fallback_min_bars: int = Field(default=3, ge=1, le=30)

    # ---- Impulse bar / strong move ----
    n_strong: int = Field(default=3, ge=2, le=10)
    k_impulse: float = Field(default=1.5, gt=1, lt=10)
    k_strong_path: float = Field(default=2.0, gt=1, lt=10)

    # ---- Stop detection ----
    m_cons: int = Field(default=2, ge=1, le=5)
    long_tail_threshold: float = Field(default=0.5, gt=0, lt=1)

    # ---- Correction ----
    fib_min: float = Field(default=0.236, gt=0, lt=1)
    fib_max: float = Field(default=0.618, gt=0, lt=1)
    k_resume: int = Field(default=2, ge=1, le=5)

    # ---- Levels: identification ----
    level_merge_pct: float = Field(default=0.001, gt=0, lt=0.05)
    min_level_score: int = Field(default=5, ge=1, le=20)

    # ---- Levels: base scores ----
    score_trend_break: int = Field(default=4, ge=1, le=10)
    score_mirror: int = Field(default=3, ge=1, le=10)
    score_limit_player: int = Field(default=3, ge=1, le=10)
    score_historical: int = Field(default=3, ge=1, le=10)
    score_paranormal_bar: int = Field(default=2, ge=1, le=10)
    score_consolidation: int = Field(default=2, ge=1, le=10)
    score_air: int = Field(default=1, ge=1, le=10)

    # ---- Levels: bonuses ----
    bonus_false_breakout: int = Field(default=1, ge=0, le=5)
    bonus_round_number: int = Field(default=1, ge=0, le=5)
    bonus_extra_touches: int = Field(default=1, ge=0, le=5)
    bonus_extra_touches_max: int = Field(default=2, ge=0, le=5)
    bonus_higher_tf_match: int = Field(default=1, ge=0, le=5)
    bonus_first_hour: int = Field(default=1, ge=0, le=5)

    # ---- Levels: penalties ----
    penalty_chop: int = Field(default=-2, ge=-5, le=0)
    penalty_body_only: int = Field(default=-1, ge=-5, le=0)
    penalty_infected_zone: int = Field(default=-1, ge=-5, le=0)

    # ---- Levels: detection thresholds ----
    touches_for_limit_player: int = Field(default=3, ge=2, le=10)
    round_number_step: float = Field(default=25.0, gt=0)
    round_number_tolerance_pct: float = Field(default=0.002, gt=0, lt=0.05)
    chop_lookback: int = Field(default=20, ge=5, le=100)

    # ---- Energy ----
    energy_window_min: int = Field(default=3, ge=2, le=10)
    energy_window_max: int = Field(default=10, ge=3, le=30)
    energy_small_k: float = Field(default=0.5, gt=0, lt=1)
    energy_big_k: float = Field(default=2.0, gt=1, lt=10)
    energy_accumulation_pct: float = Field(default=0.6, gt=0, lt=1)
    energy_distribution_pct: float = Field(default=0.4, gt=0, lt=1)
    energy_exhaustion_atr: float = Field(default=0.1, gt=0, lt=1)

    # ---- path_ratio ----
    atr_filter_threshold: float = Field(default=0.75, gt=0, lt=5)
    allow_ath_override: bool = True

    # ---- Lookback ----
    key_points_lookback_days: int = Field(default=365, ge=30, le=2000)
