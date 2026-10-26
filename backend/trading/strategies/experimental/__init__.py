"""Experimental strategies. Not a product default.

Importing this package does not register a strategy, does not change
``RiskLimits``, and does not place orders. ``leader_campaign`` is loaded
by ``get_strategy`` only when ``BOOMBOOM_EXPERIMENTAL_STRATEGIES`` is on.
The default is off. The flag does not authorize this package to submit.
"""
from __future__ import annotations

import os


def experimental_strategies_enabled() -> bool:
    """True only when the operator explicitly opts into experimental code."""
    raw = os.environ.get("BOOMBOOM_EXPERIMENTAL_STRATEGIES", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}
