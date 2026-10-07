"""Unified strategy registry.

Collects metadata from three sources and returns a single list of
StrategyMetadata objects, so the API and UI do not care where a
strategy came from.

Sources:
- Python classes in STRATEGY_REGISTRY (read ClassVar attributes).
- Builtin YAML configs compiled in loader.load_builtin().
- Custom strategies from the DB (parse config_json).
"""

import json
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.custom_strategy import CustomStrategy
from app.schemas.strategy import (
    DirectionSpec,
    RiskConfigPreview,
    StrategyMetadata,
    StrategyParamSpec,
)
from app.services.backtest_service import STRATEGY_REGISTRY
from app.strategies.loader import load_builtin

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Converters
# ---------------------------------------------------------------------------


def _python_to_metadata(name: str, cls: type) -> StrategyMetadata:
    """Convert a Python strategy class to StrategyMetadata.

    Reads ClassVar attributes: name, display_name, description,
    params_meta, default_risk_config, direction, tags, intraday_only.
    """
    raw_params = getattr(cls, "params_meta", []) or []
    params = [StrategyParamSpec(**p) for p in raw_params]

    raw_risk = getattr(cls, "default_risk_config", {}) or {}
    risk = RiskConfigPreview(
        use_risk_management=raw_risk.get("use_risk_management", True),
        stop_type=raw_risk.get("stop_type", "atr"),
        atr_multiplier=float(raw_risk.get("atr_multiplier", 1.5)),
        take_profit_rr=float(raw_risk.get("take_profit_rr", 3.0)),
        risk_per_trade_pct=float(raw_risk.get("risk_per_trade_pct", 0.5)),
    )

    raw_dir = getattr(cls, "direction", {"long": True, "short": False})
    direction = DirectionSpec(
        long=bool(raw_dir.get("long", True)),
        short=bool(raw_dir.get("short", False)),
    )

    return StrategyMetadata(
        name=getattr(cls, "name", name),
        display_name=getattr(cls, "display_name", name),
        description=getattr(cls, "description", ""),
        source="python",
        is_custom=False,
        custom_id=None,
        params=params,
        default_risk_config=risk,
        direction=direction,
        tags=list(getattr(cls, "tags", []) or []),
        intraday_only=bool(getattr(cls, "intraday_only", False)),
    )


def _builtin_to_metadata(slug: str, cls: type) -> StrategyMetadata:
    """Convert a compiled builtin YAML strategy to StrategyMetadata.

    Builtin strategies are compiled classes without ClassVar metadata,
    so we read what we can: name = slug, tags = ["builtin"].
    """
    return StrategyMetadata(
        name=slug,
        display_name=slug.replace("_", " ").title(),
        description="Builtin YAML strategy",
        source="builtin",
        is_custom=False,
        custom_id=None,
        params=[],
        default_risk_config=RiskConfigPreview(),
        direction=DirectionSpec(long=True, short=False),
        tags=["builtin"],
        intraday_only=False,
    )


def _custom_to_metadata(row: CustomStrategy) -> StrategyMetadata:
    """Convert a CustomStrategy DB row to StrategyMetadata.

    Parses config_json. Params are extracted from the `risk` section
    defaults (no min/max yet — those come later with templates).
    """
    try:
        config = json.loads(row.config_json)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Custom strategy id=%s has invalid config_json", row.id)
        config = {}

    raw_risk = config.get("risk", {}) or {}
    risk = RiskConfigPreview(
        use_risk_management=raw_risk.get("use_risk_management", True),
        stop_type=raw_risk.get("stop_type", "atr"),
        atr_multiplier=float(raw_risk.get("atr_multiplier", 1.5)),
        take_profit_rr=float(raw_risk.get("take_profit_rr", 3.0)),
        risk_per_trade_pct=float(raw_risk.get("risk_per_trade_pct", 0.5)),
    )

    raw_dir = config.get("direction", {"long": True, "short": False})
    direction = DirectionSpec(
        long=bool(raw_dir.get("long", True)),
        short=bool(raw_dir.get("short", False)),
    )

    return StrategyMetadata(
        name=f"custom_{row.id}",
        display_name=row.name,
        description=row.description or "",
        source="custom",
        is_custom=True,
        custom_id=row.id,
        params=[],
        default_risk_config=risk,
        direction=direction,
        tags=["custom"],
        intraday_only=bool(config.get("intraday_only", False)),
    )


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------


def get_all_strategies(session: Session) -> list[StrategyMetadata]:
    """Collect all strategies from all sources, sorted.

    Order: builtin first, then custom, then python.
    Within each group — by display_name.
    """
    items: list[StrategyMetadata] = []

    # 1. Builtin YAML.
    try:
        builtin = load_builtin()
    except Exception as exc:
        logger.error("Failed to load builtin strategies: %s", exc)
        builtin = {}

    for slug, cls in builtin.items():
        items.append(_builtin_to_metadata(slug, cls))

    # 2. Custom from DB.
    try:
        rows = (
            session.execute(select(CustomStrategy).order_by(CustomStrategy.id.asc()))
            .scalars()
            .all()
        )
    except Exception as exc:
        logger.error("Failed to load custom strategies: %s", exc)
        rows = []

    for row in rows:
        items.append(_custom_to_metadata(row))

    # 3. Python classes.
    for name, cls in STRATEGY_REGISTRY.items():
        items.append(_python_to_metadata(name, cls))

    # Sort: source order then display_name.
    source_order = {"builtin": 0, "custom": 1, "python": 2}
    items.sort(key=lambda m: (source_order.get(m.source, 99), m.display_name.lower()))

    return items


def get_strategy_by_name(session: Session, name: str) -> StrategyMetadata | None:
    """Find one strategy by name.

    Accepts:
    - Python class name (e.g. "sma_crossover")
    - Builtin slug (e.g. "rsi_mean_reversion")
    - Custom by id (e.g. "custom_1")
    - Custom by display name (e.g. "RSI Simple")
    """
    # Python.
    if name in STRATEGY_REGISTRY:
        return _python_to_metadata(name, STRATEGY_REGISTRY[name])

    # Builtin.
    try:
        builtin = load_builtin()
    except Exception:
        builtin = {}
    if name in builtin:
        return _builtin_to_metadata(name, builtin[name])

    # Custom by id.
    if name.startswith("custom_"):
        try:
            sid = int(name.split("_", 1)[1])
        except (ValueError, IndexError):
            return None
        row = session.get(CustomStrategy, sid)
        if row is not None:
            return _custom_to_metadata(row)
        return None

    # Custom by display name.
    row = session.execute(
        select(CustomStrategy).where(CustomStrategy.name == name)
    ).scalar_one_or_none()
    if row is not None:
        return _custom_to_metadata(row)

    return None
