"""Load strategies: builtin YAML configs and custom ones from DB.

Builtin YAMLs are compiled once and cached in memory.
Custom strategies are loaded from the DB on demand (users can
create/update/delete them at runtime, so caching is not safe).
"""

import json
import logging
import re
from pathlib import Path

import yaml

from app.db.session import SessionLocal
from app.models.custom_strategy import CustomStrategy
from app.strategies.builder.compiler import compile_strategy
from app.strategies.builder.config import StrategyConfig

logger = logging.getLogger(__name__)

BUILTIN_DIR = Path(__file__).parent / "builtin"

_builtin_cache: dict[str, type] | None = None


def _slugify(name: str) -> str:
    """Turn 'SMA Crossover DSL' into 'sma_crossover_dsl'."""
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def load_builtin() -> dict[str, type]:
    """Load, compile and cache all builtin YAML strategies."""
    global _builtin_cache
    if _builtin_cache is not None:
        return _builtin_cache

    result: dict[str, type] = {}
    if not BUILTIN_DIR.exists():
        _builtin_cache = result
        return result

    for yaml_path in sorted(BUILTIN_DIR.glob("*.yaml")):
        try:
            with yaml_path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            cfg = StrategyConfig.model_validate(raw)
            cls = compile_strategy(cfg)
            key = _slugify(cfg.name)
            result[key] = cls
            logger.info("Builtin loaded: %s -> %s", key, cls.__name__)
        except Exception as exc:
            logger.error("Failed to load builtin %s: %s", yaml_path.name, exc)

    _builtin_cache = result
    return result


def load_custom(strategy_id: int) -> type:
    """Load and compile a custom strategy by its DB id."""
    with SessionLocal() as db:
        row = db.get(CustomStrategy, strategy_id)
        if row is None:
            raise ValueError(f"Custom strategy id={strategy_id} not found")
        raw = json.loads(row.config_json)

    cfg = StrategyConfig.model_validate(raw)
    return compile_strategy(cfg)
