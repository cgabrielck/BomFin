"""Harness and role-card contracts: whitelist, references, budget, schema, prompts."""
from pathlib import Path
from uuid import UUID

import pytest

from gabfin.research.harness import ExecutionResult, Harness
from gabfin.research.roles import (
    PROMPT_ROOT,
    PromptRenderError,
    RoleCardError,
    load_all_role_cards,
    load_role_card,
    render_prompt,
)

ROLES_DIR = Path(__file__).resolve().parents[2] / "config" / "agents"
SNAP = UUID("22222222-2222-4222-8222-222222222222")
EV_OK = "33333333-3333-4333-8333-333333333333"
EV_OTHER = "44444444-4444-4444-8444-444444444444"


@pytest.fixture
def technical():
    return load_role_card("technical", ROLES_DIR)


@pytest.fixture
def harness():
    return Harness({SNAP: frozenset({EV_OK})})


def _run(harness, card, **overrides):
    kwargs = dict(
        snapshot_id=SNAP,
        tools_called=("read_bars",),
        output={"conclusions": [{"text": "x", "evidence_id": EV_OK}]},
        input_payload={"snapshot": str(SNAP)},
        input_tokens=100,
        output_tokens=50,
        elapsed_seconds=1.0,
        attempts=1,
        model_version="test-model",
    )
    kwargs.update(overrides)
    return harness.validate(card, **kwargs)


# --- role cards -----------------------------------------------------------

def test_all_three_role_cards_load():
    cards = load_all_role_cards(ROLES_DIR)
    assert set(cards) == {"discovery", "portfolio", "technical"}


def test_role_card_rejects_execution_capable_tool(tmp_path):
    (tmp_path / "bad.yaml").write_text(
        "version: 1\nrole: bad\npurpose: p\ninputs: i\noutputs: o\n"
        "tools: [submit_order]\nforbidden: []\n"
        "budget: {max_input_tokens: 1, max_output_tokens: 1, max_attempts_per_node: 1, deadline_seconds: 1}\n"
        "prompt: {system: a, user: b, version: 1}\n",
        encoding="utf-8",
    )
    with pytest.raises(RoleCardError, match="Execution-capable"):
        load_role_card("bad", tmp_path)


def test_role_card_name_must_match_file(tmp_path):
    src = (ROLES_DIR / "technical.yaml").read_text(encoding="utf-8")
    (tmp_path / "other.yaml").write_text(src, encoding="utf-8")
    with pytest.raises(RoleCardError, match="does not match"):
        load_role_card("other", tmp_path)


def test_role_card_rejects_unknown_field(tmp_path):
    src = (ROLES_DIR / "technical.yaml").read_text(encoding="utf-8")
    (tmp_path / "technical.yaml").write_text(src + "\nextra_key: 1\n", encoding="utf-8")
    with pytest.raises(RoleCardError, match="Schema violation"):
        load_role_card("technical", tmp_path)


def test_role_card_missing_file_is_reported(tmp_path):
    with pytest.raises(RoleCardError, match="not found"):
        load_role_card("nope", tmp_path)


# --- prompts --------------------------------------------------------------

def test_prompt_renders_with_context(technical):
    system = render_prompt(technical, "system", {"tools": technical.tools, "output_schema": "{}"}, PROMPT_ROOT)
    assert "read_bars" in system
    assert "不得輸出 StrategyIntent" in system


def test_prompt_missing_variable_is_an_error(technical):
    with pytest.raises(PromptRenderError):
        render_prompt(technical, "system", {"tools": technical.tools}, PROMPT_ROOT)


# --- harness: whitelist ---------------------------------------------------

def test_unlisted_tool_is_rejected(harness, technical):
    result = _run(harness, technical, tools_called=("read_bars", "submit_order"))
    assert result.execution_result is ExecutionResult.tool_forbidden
    assert any("submit_order" in r for r in result.reasons)


def test_listed_tools_pass(harness, technical):
    result = _run(harness, technical, tools_called=("read_bars", "compute_indicators"))
    assert result.execution_result is ExecutionResult.success


# --- harness: evidence references -----------------------------------------

def test_missing_evidence_reference_is_flagged(harness, technical):
    output = {"conclusions": [{"text": "x", "evidence_id": EV_OTHER}]}
    result = _run(harness, technical, output=output)
    assert result.execution_result is ExecutionResult.snapshot_reference_broken
    assert EV_OTHER in result.reasons[0]


def test_unknown_snapshot_fails_closed(technical):
    harness = Harness()  # no snapshots registered
    result = _run(harness, technical)
    assert result.execution_result is ExecutionResult.snapshot_unknown


# --- harness: budget ------------------------------------------------------

@pytest.mark.parametrize(
    "overrides",
    [
        {"input_tokens": 20001},
        {"output_tokens": 4001},
        {"attempts": 3},
        {"elapsed_seconds": 121.0},
    ],
)
def test_budget_overrun_is_flagged(harness, technical, overrides):
    result = _run(harness, technical, **overrides)
    assert result.execution_result is ExecutionResult.budget_exceeded


# --- harness: schema ------------------------------------------------------

def test_schema_failure_is_flagged(harness, technical):
    def validator(output):
        return None if "conclusions" in output else "missing conclusions"

    result = _run(harness, technical, output={"oops": 1}, output_validator=validator)
    assert result.execution_result is ExecutionResult.output_schema_invalid


# --- harness: precedence and audit ----------------------------------------

def test_first_failure_wins_but_all_reasons_recorded(harness, technical):
    result = _run(
        harness,
        technical,
        tools_called=("submit_order",),
        input_tokens=99999,
    )
    assert result.execution_result is ExecutionResult.tool_forbidden
    assert len(result.reasons) == 2


def test_audit_log_records_hashes_and_versions(harness, technical):
    result = _run(harness, technical)
    assert len(harness.audit_log) == 1
    assert len(result.input_hash) == 64 and len(result.output_hash) == 64
    assert result.prompt_version == technical.prompt.version
    assert result.model_version == "test-model"


def test_same_input_gives_same_input_hash(harness, technical):
    a = _run(harness, technical, input_payload={"k": 1, "j": 2})
    b = _run(harness, technical, input_payload={"j": 2, "k": 1})
    assert a.input_hash == b.input_hash
