"""Harness: tool whitelist, output schema, evidence references, budget, audit.

This is the only permission boundary for research roles. Prompt text is never
trusted to enforce anything; LangGraph only orders nodes and does not judge.
"""
import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from gabfin.research.roles import RoleCard

logger = logging.getLogger(__name__)

# Returns None when the output is valid, otherwise a human-readable reason.
OutputValidator = Callable[[Mapping[str, Any]], str | None]


class ExecutionResult(str, Enum):
    success = "success"
    tool_forbidden = "tool_forbidden"
    output_schema_invalid = "output_schema_invalid"
    snapshot_unknown = "snapshot_unknown"
    snapshot_reference_broken = "snapshot_reference_broken"
    budget_exceeded = "budget_exceeded"


class CheckResult(BaseModel):
    """Immutable audit record for one harnessed execution."""

    model_config = ConfigDict(frozen=True)

    role: str
    prompt_version: int
    model_version: str
    snapshot_id: UUID
    input_hash: str
    output_hash: str
    execution_result: ExecutionResult
    reasons: tuple[str, ...]
    checked_at: datetime


def _sha256(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _collect_evidence_ids(node: Any) -> set[str]:
    """Every `evidence_id` value anywhere in the output tree."""
    found: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "evidence_id":
                found.add(str(value))
            else:
                found |= _collect_evidence_ids(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            found |= _collect_evidence_ids(item)
    return found


class Harness:
    """Checks one research execution and records an audit entry.

    `snapshot_evidence` maps a snapshot_id to the set of evidence ids that
    snapshot actually contains. An unknown snapshot is a failure.
    """

    def __init__(self, snapshot_evidence: Mapping[UUID, frozenset[str]] | None = None):
        self._snapshots: dict[UUID, frozenset[str]] = dict(snapshot_evidence or {})
        self.audit_log: list[CheckResult] = []

    def register_snapshot(self, snapshot_id: UUID, evidence_ids: frozenset[str]) -> None:
        self._snapshots[snapshot_id] = frozenset(evidence_ids)

    def validate(
        self,
        card: RoleCard,
        *,
        snapshot_id: UUID,
        tools_called: tuple[str, ...],
        output: Mapping[str, Any],
        input_payload: Mapping[str, Any],
        input_tokens: int | None,
        output_tokens: int | None,
        elapsed_seconds: float,
        attempts: int,
        model_version: str,
        output_validator: OutputValidator | None = None,
    ) -> CheckResult:
        """Run all checks in priority order; the first failure decides the result."""
        reasons: list[str] = []
        result = ExecutionResult.success

        def fail(kind: ExecutionResult, reason: str) -> None:
            nonlocal result
            reasons.append(reason)
            if result is ExecutionResult.success:
                result = kind

        # 1. Tool whitelist: every tool actually called must be on the role card.
        allowed = set(card.tools)
        for tool in tools_called:
            if tool not in allowed:
                fail(ExecutionResult.tool_forbidden, f"tool '{tool}' not in whitelist for {card.role}")

        # 2. Output schema (delegated validator; None means valid).
        if output_validator is not None:
            schema_error = output_validator(output)
            if schema_error:
                fail(ExecutionResult.output_schema_invalid, schema_error)

        # 3. Snapshot must exist, and every cited evidence_id must belong to it.
        if snapshot_id not in self._snapshots:
            fail(ExecutionResult.snapshot_unknown, f"snapshot {snapshot_id} is not registered")
        else:
            available = self._snapshots[snapshot_id]
            broken = sorted(_collect_evidence_ids(output) - available)
            if broken:
                fail(
                    ExecutionResult.snapshot_reference_broken,
                    f"evidence ids not in snapshot: {', '.join(broken)}",
                )

        # 4. Budget: tokens, attempts, and wall-clock deadline.
        budget = card.budget
        if input_tokens is not None and input_tokens > budget.max_input_tokens:
            fail(ExecutionResult.budget_exceeded, f"input tokens {input_tokens} > {budget.max_input_tokens}")
        if output_tokens is not None and output_tokens > budget.max_output_tokens:
            fail(ExecutionResult.budget_exceeded, f"output tokens {output_tokens} > {budget.max_output_tokens}")
        if attempts > budget.max_attempts_per_node:
            fail(ExecutionResult.budget_exceeded, f"attempts {attempts} > {budget.max_attempts_per_node}")
        if elapsed_seconds > budget.deadline_seconds:
            fail(ExecutionResult.budget_exceeded, f"elapsed {elapsed_seconds}s > {budget.deadline_seconds}s")

        record = CheckResult(
            role=card.role,
            prompt_version=card.prompt.version,
            model_version=model_version,
            snapshot_id=snapshot_id,
            input_hash=_sha256(input_payload),
            output_hash=_sha256(output),
            execution_result=result,
            reasons=tuple(reasons),
            checked_at=datetime.now(timezone.utc),
        )
        self.audit_log.append(record)
        logger.info("harness.check role=%s result=%s", card.role, result.value)
        return record
