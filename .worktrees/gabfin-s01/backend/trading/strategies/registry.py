"""
Strategy registry — maps strategy_id strings to strategy instances.

Canonical desk modes: adaptive | trend | breakout | research_list | defensive_gld
Legacy aliases: hybrid→adaptive, aggressive→breakout, stable→reversion (same class)
defensive_gld is operator-chosen only — never the default.
"""
from __future__ import annotations

from typing import Dict

from backend.trading.strategies.adaptive import AdaptiveStrategy
from backend.trading.strategies.aggressive import AggressiveStrategy
from backend.trading.strategies.base import StrategyBase
from backend.trading.strategies.defensive_gld import DefensiveGldStrategy
from backend.trading.strategies.research_list import ResearchListStrategy
from backend.trading.strategies.stable import StableStrategy
from backend.trading.strategies.trend import TrendStrategy

KNOWN_STRATEGIES = (
    "adaptive",
    "trend",
    "breakout",
    "research_list",
    "defensive_gld",
    # legacy aliases
    "hybrid",
    "aggressive",
    "stable",
    "reversion",
)


class HybridStrategy(AdaptiveStrategy):
    """Legacy name for AdaptiveStrategy (kept for ai_mode.json / old workers)."""

    strategy_id = "hybrid"
    display_name = "混合型 Hybrid → Adaptive"


# Registry of all available strategies
_INSTANCES: Dict[str, StrategyBase] = {
    "adaptive": AdaptiveStrategy(),
    "trend": TrendStrategy(),
    "breakout": AggressiveStrategy(),
    "aggressive": AggressiveStrategy(),  # alias
    "research_list": ResearchListStrategy(),
    "defensive_gld": DefensiveGldStrategy(),
    "stable": StableStrategy(),  # Connors reversion
    "reversion": StableStrategy(),
    "hybrid": HybridStrategy(),
}

STRATEGY_REGISTRY: Dict[str, StrategyBase] = _INSTANCES

_CLS_MAP = {
    "adaptive": AdaptiveStrategy,
    "trend": TrendStrategy,
    "breakout": AggressiveStrategy,
    "aggressive": AggressiveStrategy,
    "research_list": ResearchListStrategy,
    "defensive_gld": DefensiveGldStrategy,
    "stable": StableStrategy,
    "reversion": StableStrategy,
    "hybrid": HybridStrategy,
}


# Cached experimental instances. Not part of STRATEGY_REGISTRY / KNOWN_STRATEGIES.
# The product default stays adaptive/breakout whether or not the flag is on.
_EXPERIMENTAL: Dict[str, StrategyBase] = {}


def strategy_choices() -> tuple:
    """Ids the worker CLI may select.

    ``leader_campaign`` is included only while the experimental flag is on.
    It is never added to ``KNOWN_STRATEGIES`` or the AI Mode button list.
    """
    from backend.trading.strategies.experimental import experimental_strategies_enabled

    if experimental_strategies_enabled():
        return KNOWN_STRATEGIES + ("leader_campaign",)
    return KNOWN_STRATEGIES


def _leader_campaign_strategy() -> StrategyBase:
    """Flag on: the playbook. Flag off: a no-buy stand-in with the same id.

    Unknown ids still fall through to adaptive. This id must not, or a saved
    ``leader_campaign`` setting would silently trade another strategy.
    """
    from backend.trading.strategies.experimental import experimental_strategies_enabled
    from backend.trading.strategies.experimental.leader_campaign import (
        DisabledLeaderCampaign,
        LeaderCampaignStrategy,
    )

    if experimental_strategies_enabled():
        inst = _EXPERIMENTAL.get("leader_campaign")
        if not isinstance(inst, LeaderCampaignStrategy):
            inst = LeaderCampaignStrategy()
            _EXPERIMENTAL["leader_campaign"] = inst
        return inst
    inst = _EXPERIMENTAL.get("leader_campaign_off")
    if not isinstance(inst, DisabledLeaderCampaign):
        inst = DisabledLeaderCampaign()
        _EXPERIMENTAL["leader_campaign_off"] = inst
    return inst


def get_strategy(strategy_id: str, **overrides) -> StrategyBase:
    """Return a strategy instance by ID. Defaults to 'adaptive' if unknown."""
    sid = (strategy_id or "adaptive").lower()
    if sid == "leader_campaign":
        # Overrides would be a hot-path edit of experimental constants. Ignore them.
        del overrides
        return _leader_campaign_strategy()
    if overrides:
        cls = _CLS_MAP.get(sid, AdaptiveStrategy)
        return cls(**overrides)
    return _INSTANCES.get(sid, _INSTANCES["adaptive"])
