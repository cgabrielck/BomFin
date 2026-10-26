"""Product M7 judge slot (Phase 1).

Interface plus a no-op default. This package must not import OrderManager,
a broker, or lab advisory_debate. Phase 1 does not call a model when
``AI_JUDGE=0``.
"""

from backend.trading.advisory.judge import (
    JUDGE_TIMEOUT_S,
    KNOWN_VETO_CODES,
    JudgeDecision,
    ai_judge_enabled,
    evaluate_entry,
    parse_judge_payload,
)

__all__ = [
    "JUDGE_TIMEOUT_S",
    "KNOWN_VETO_CODES",
    "JudgeDecision",
    "ai_judge_enabled",
    "evaluate_entry",
    "parse_judge_payload",
]
