"""Phase 1 judge slot: closed schema, default off, no broker."""

from __future__ import annotations

import ast
import json
import socket
from pathlib import Path

import pytest

from backend.trading.advisory.judge import (
    KNOWN_VETO_CODES,
    ai_judge_enabled,
    evaluate_entry,
    parse_judge_payload,
)
from backend.trading.intents.models import IntentValidationError, parse_intent

ROOT = Path(__file__).resolve().parents[3]
ADVISORY = ROOT / "backend" / "trading" / "advisory"

_SOURCE = {
    "type": "filing",
    "ref": "https://example.test/aapl-10q",
    "asof": "2026-10-26T00:00:00Z",
}


def _valid(**overrides):
    payload = {
        "veto_codes": [],
        "conviction_tier": "med",
        "sources": [_SOURCE],
        "notes": "no veto",
    }
    payload.update(overrides)
    return payload


def test_known_veto_list_matches_method():
    assert KNOWN_VETO_CODES == frozenset(
        {
            "CALENDAR_BLACKOUT",
            "STALE_DATA",
            "CORR_CAP",
            "KILL_ACTIVE",
            "EVENT_FREEZE",
        }
    )


def test_default_off_and_explicit_zero(monkeypatch):
    monkeypatch.delenv("AI_JUDGE", raising=False)
    assert ai_judge_enabled() is False
    monkeypatch.setenv("AI_JUDGE", "0")
    assert ai_judge_enabled() is False


def test_off_does_not_call_client_or_open_a_socket(monkeypatch):
    monkeypatch.setenv("AI_JUDGE", "0")
    called = []

    def _client(setup):
        called.append(setup)
        raise AssertionError("client must not run when AI_JUDGE=0")

    def _refuse_network(*_a, **_k):
        raise AssertionError("network while AI_JUDGE=0")

    monkeypatch.setattr(socket, "create_connection", _refuse_network)
    decision = evaluate_entry({"symbol": "AAPL", "side": "buy"}, client=_client)
    assert decision.allow is True
    assert decision.noop is True
    assert called == []
    assert not hasattr(decision, "quantity")


def test_unconfigured_on_is_silence_without_client(monkeypatch):
    monkeypatch.setenv("AI_JUDGE", "1")
    decision = evaluate_entry({"symbol": "AAPL"}, client=None)
    assert decision.allow is False
    assert decision.failure == "judge_unconfigured"


def test_bad_json_is_silence(monkeypatch):
    monkeypatch.setenv("AI_JUDGE", "1")
    decision = evaluate_entry({"symbol": "AAPL"}, client=lambda _s: "this is not json")
    assert decision.allow is False
    assert decision.failure == "bad_json"


def test_timeout_error_and_join_timeout_are_silence(monkeypatch):
    monkeypatch.setenv("AI_JUDGE", "1")
    raised = evaluate_entry(
        {"symbol": "AAPL"},
        client=lambda _s: (_ for _ in ()).throw(TimeoutError("stub")),
    )
    assert raised.allow is False
    assert raised.failure == "timeout"

    def _sleep(_setup):
        import time

        time.sleep(1.0)
        return _valid()

    joined = evaluate_entry({"symbol": "AAPL"}, client=_sleep, timeout_s=0.05)
    assert joined.allow is False
    assert joined.failure == "timeout"


def test_unknown_veto_does_not_block():
    decision = parse_judge_payload(_valid(veto_codes=["NOT_A_REAL_CODE"]))
    assert decision.allow is True
    assert decision.veto_codes == ()
    assert decision.ignored_codes == ("NOT_A_REAL_CODE",)


def test_known_veto_blocks_and_empty_sources_are_silence():
    blocked = parse_judge_payload(_valid(veto_codes=["STALE_DATA"]))
    assert blocked.allow is False
    assert blocked.veto_codes == ("STALE_DATA",)
    assert blocked.failure is None

    silent = parse_judge_payload(_valid(sources=[]))
    assert silent.allow is False
    assert silent.failure == "empty_sources"


def test_quantity_and_notional_are_rejected_and_not_an_intent():
    for field in ("quantity", "notional"):
        decision = parse_judge_payload(_valid(**{field: 10}))
        assert decision.allow is False
        assert decision.failure == "forbidden_fields"

    base = {
        "symbol": "AAPL",
        "side": "buy",
        "stop": {"type": "pct", "value": 0.1},
        "conviction_tier": "low",
        "expiry": "2026-10-27T00:00:00Z",
        "as_of": "2026-10-26T00:00:00Z",
    }
    for field in ("quantity", "notional"):
        with pytest.raises(IntentValidationError):
            parse_intent({**base, field: 5})


def test_advisory_package_does_not_import_the_executor():
    banned_modules = {
        "backend.trading.engine.order_manager",
        "backend.trading.engine.desk_orders",
        "backend.trading.alpaca_broker",
        "backend.trading.engine.signal_processor",
        "backend.trading.engine.worker",
        "backend.lab.advisory_debate",
        "openai",
        "anthropic",
        "httpx",
        "requests",
        "urllib",
        "urllib.request",
    }
    files = list(ADVISORY.rglob("*.py"))
    assert files, "advisory package missing"
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mods.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module)
        assert mods.isdisjoint(banned_modules), f"{path.name} imports {mods & banned_modules}"
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name):
                    called.add(func.id)
                elif isinstance(func, ast.Attribute):
                    called.add(func.attr)
        assert "OrderManager" not in called
        assert "upsert_active_intent" not in called
        assert "place_desk_order" not in called


def test_decision_json_has_no_size_field():
    decision = parse_judge_payload(_valid(conviction_tier="low"))
    blob = json.dumps(
        {
            "allow": decision.allow,
            "conviction_tier": decision.conviction_tier,
            "veto_codes": list(decision.veto_codes),
        }
    )
    assert "quantity" not in blob
    assert "notional" not in blob
