"""Research snapshots and harness checks persist immutably in local SQLite.

A snapshot is the only thing a research conclusion may cite. It is created
once, never rewritten, and the evidence it exposes is read out of its own
context rather than handed over separately: a caller cannot widen the
evidence a snapshot has by asserting a wider set.

The store owns its own tables in the same file as the rest of the domain
storage. It never touches the global schema version table, so a research
database can be opened beside a market one without a migration.
"""
import json
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from gabfin.research.harness import CheckResult, ExecutionResult

SNAPSHOT_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_SNAPSHOT_ID = UUID("22222222-2222-4222-8222-222222222222")
EV_ONE = "33333333-3333-4333-8333-333333333333"
EV_TWO = "44444444-4444-4444-8444-444444444444"
EV_ABSENT = "55555555-5555-4555-8555-555555555555"
AS_OF = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def _default_context():
    """A context in the common research input shape."""
    return {
        "observations": [
            {"evidence_id": EV_ONE, "text": "AAPL earnings beat", "symbol": "AAPL"},
        ],
        "bars": [
            {"evidence_id": EV_TWO, "symbol": "AAPL", "close": "211.50"},
        ],
        "indicators": [],
        "account": {"equity": "100000.00", "evidence_id": EV_ONE,
                    "position_count": 2, "max_weight": "0.25"},
        "limits": {"per_trade_risk": "0.01", "daily_loss": "0.02"},
    }


def check(snapshot_id=SNAPSHOT_ID):
    return CheckResult(
        role="technical",
        prompt_version=1,
        model_version="test-model",
        snapshot_id=snapshot_id,
        input_hash="a" * 64,
        output_hash="b" * 64,
        execution_result=ExecutionResult.success,
        reasons=(),
        checked_at=datetime(2026, 11, 27, 12, 5, tzinfo=timezone.utc),
    )


@pytest.fixture
def store(tmp_path):
    from gabfin.research.store import ResearchStore
    return ResearchStore(tmp_path / "research.sqlite")


def _create(store, *, as_of=AS_OF, context=None, quality=("clean",), evidence=None):
    payload = _default_context() if context is None else context
    return store.create_snapshot(
        as_of=as_of,
        context=payload,
        data_quality=list(quality),
        evidence_ids=frozenset({EV_ONE, EV_TWO}) if evidence is None else evidence,
    )


# --- creation -------------------------------------------------------------

def test_create_snapshot_returns_a_uuid(store):
    snapshot_id = _create(store)
    assert isinstance(snapshot_id, UUID)
    assert snapshot_id != uuid4()


def test_create_snapshot_returns_the_common_input_shape(store):
    _create(store)
    snapshot = store.get_snapshot(store.snapshot_ids()[0])
    assert set(snapshot) == {"snapshot_id", "as_of", "context", "data_quality"}
    assert snapshot["as_of"] == AS_OF
    assert snapshot["data_quality"] == ["clean"]
    assert snapshot["context"]["bars"][0]["close"] == "211.50"


def test_created_snapshot_validates_against_the_common_input_schema(store):
    """The stored document is exactly what schemas/research/common.json accepts."""
    from jsonschema import Draft202012Validator
    from pathlib import Path
    schema_path = (Path(__file__).resolve().parents[2] / "schemas" / "research" / "common.json")
    document = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(document["$defs"]["input"])
    snapshot_id = _create(store)
    snapshot = store.get_snapshot(snapshot_id)
    errors = list(validator.iter_errors({
        "snapshot_id": str(snapshot["snapshot_id"]),
        "as_of": snapshot["as_of"].isoformat(),
        "data_quality": snapshot["data_quality"],
        "context": snapshot["context"],
    }))
    assert errors == []


def test_get_snapshot_of_unknown_id_raises_key_error(store):
    with pytest.raises(KeyError):
        store.get_snapshot(uuid4())


def test_get_snapshot_returns_a_deep_copy(store):
    _create(store)
    snapshot = store.get_snapshot(store.snapshot_ids()[0])
    snapshot["context"]["bars"][0]["close"] = "999.99"
    snapshot["context"]["bars"].append({"evidence_id": EV_TWO})
    snapshot["data_quality"].append("mutated")
    fresh = store.get_snapshot(store.snapshot_ids()[0])
    assert fresh["context"]["bars"][0]["close"] == "211.50"
    assert len(fresh["context"]["bars"]) == 1
    assert fresh["data_quality"] == ["clean"]


def test_snapshot_survives_reopen(tmp_path):
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    _create(ResearchStore(path))
    reopened = ResearchStore(path)
    snapshot_id = reopened.snapshot_ids()[0]
    assert reopened.get_snapshot(snapshot_id)["as_of"] == AS_OF
    assert reopened.evidence_ids(snapshot_id) == frozenset({EV_ONE, EV_TWO})


# --- immutability ---------------------------------------------------------

def test_snapshot_content_cannot_be_rewritten(tmp_path):
    """Re-registering the same id with different content is refused."""
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    store = ResearchStore(path)
    snapshot_id = _create(store)
    changed = _default_context()
    changed["bars"][0]["close"] = "1.00"
    with pytest.raises(ValueError, match="conflict"):
        store.create_snapshot(as_of=AS_OF, context=changed, data_quality=["clean"],
                              evidence_ids=frozenset({EV_ONE, EV_TWO}), snapshot_id=snapshot_id)
    assert store.get_snapshot(snapshot_id)["context"]["bars"][0]["close"] == "211.50"


def test_snapshot_rows_have_no_update_path(tmp_path):
    """The store exposes no way to mutate a stored snapshot."""
    from gabfin.research.store import ResearchStore
    import inspect
    public = [name for name in dir(ResearchStore) if not name.startswith("_")]
    assert not [name for name in public
                if any(word in name.lower() for word in ("update", "rewrite", "mutate",
                                                        "delete", "drop", "replace"))]


def test_context_key_order_does_not_make_a_conflict(store):
    snapshot_id = _create(store)
    reordered = dict(reversed(list(_default_context().items())))
    store.create_snapshot(as_of=AS_OF, context=reordered, data_quality=["clean"],
                          evidence_ids=frozenset({EV_ONE, EV_TWO}), snapshot_id=snapshot_id)
    assert store.get_snapshot(snapshot_id)["context"]["bars"][0]["close"] == "211.50"


# --- evidence -------------------------------------------------------------

def test_evidence_ids_come_from_the_registered_set(store):
    snapshot_id = _create(store)
    assert store.evidence_ids(snapshot_id) == frozenset({EV_ONE, EV_TWO})


def test_evidence_ids_is_a_frozenset(store):
    snapshot_id = _create(store)
    evidence = store.evidence_ids(snapshot_id)
    assert isinstance(evidence, frozenset)
    with pytest.raises(AttributeError):
        evidence.add(EV_ABSENT)


def test_evidence_ids_of_unknown_snapshot_raises_key_error(store):
    with pytest.raises(KeyError):
        store.evidence_ids(uuid4())


def test_context_evidence_id_outside_the_registered_set_is_refused(store):
    """A context may not cite evidence the snapshot does not register."""
    with pytest.raises(ValueError, match="evidence"):
        _create(store, context={"observations": [{"evidence_id": EV_ABSENT}]})


def test_context_evidence_id_must_be_a_uuid(store):
    with pytest.raises(ValueError, match="evidence"):
        _create(store, context={"observations": [{"evidence_id": "not-a-uuid"}]})


def test_registered_evidence_id_must_be_a_uuid(store):
    with pytest.raises(ValueError, match="evidence"):
        _create(store, evidence=frozenset({"not-a-uuid"}))


def test_snapshot_with_no_evidence_has_empty_evidence(store):
    snapshot_id = _create(store, context={"observations": [], "bars": []}, evidence=frozenset())
    assert store.evidence_ids(snapshot_id) == frozenset()


def test_evidence_id_in_another_uuid_form_is_the_same_evidence(store):
    """The same UUID written differently still refers to the same evidence."""
    context = {"observations": [{"evidence_id": EV_ONE.upper()}]}
    snapshot_id = _create(store, context=context)
    assert store.evidence_ids(snapshot_id) == frozenset({EV_ONE, EV_TWO})


# --- as_of and look-ahead -------------------------------------------------

def test_naive_as_of_is_refused(store):
    with pytest.raises(ValueError, match="as_of"):
        _create(store, as_of=datetime(2026, 11, 27, 12, 0))


def test_non_utc_as_of_is_refused(store):
    local = datetime(2026, 11, 27, 12, 0, tzinfo=timezone(timedelta(hours=8)))
    with pytest.raises(ValueError, match="as_of"):
        _create(store, as_of=local)


def test_zero_offset_as_of_is_accepted_as_utc(store):
    zero = datetime(2026, 11, 27, 12, 0, tzinfo=timezone(timedelta(0)))
    snapshot_id = _create(store, as_of=zero)
    assert store.get_snapshot(snapshot_id)["as_of"] == AS_OF


def test_context_event_at_after_as_of_is_refused(store):
    context = {"observations": [{"evidence_id": EV_ONE,
                                 "event_at": "2026-11-27T12:00:01+00:00"}]}
    with pytest.raises(ValueError, match="look-ahead"):
        _create(store, context=context)


def test_context_available_at_after_as_of_is_refused(store):
    context = {"observations": [{"evidence_id": EV_ONE,
                                 "available_at": "2026-11-27T12:00:01+00:00"}]}
    with pytest.raises(ValueError, match="look-ahead"):
        _create(store, context=context)


def test_context_release_date_after_as_of_is_refused(store):
    context = {"observations": [{"evidence_id": EV_ONE, "release_date": "2026-11-28"}]}
    with pytest.raises(ValueError, match="look-ahead"):
        _create(store, context=context)


def test_context_release_date_on_as_of_is_accepted(store):
    context = {"observations": [{"evidence_id": EV_ONE, "release_date": "2026-11-27"}]}
    snapshot_id = _create(store, context=context)
    assert store.get_snapshot(snapshot_id)["as_of"] == AS_OF


def test_unparsable_timestamp_text_is_not_treated_as_look_ahead(store):
    """Unknown text is left alone rather than guessed at."""
    context = {"observations": [{"evidence_id": EV_ONE, "event_at": "not-a-timestamp"}]}
    snapshot_id = _create(store, context=context)
    assert store.get_snapshot(snapshot_id)["context"]["observations"][0]["event_at"] \
        == "not-a-timestamp"


def test_look_ahead_inside_nested_context_is_refused(store):
    context = {"account": {"positions": [{"evidence_id": EV_ONE,
                                          "available_at": "2026-11-27T13:00:00+00:00"}]}}
    with pytest.raises(ValueError, match="look-ahead"):
        _create(store, context=context)


# --- input shape ----------------------------------------------------------

def test_non_json_context_is_refused(store):
    with pytest.raises(ValueError):
        _create(store, context={"bars": [object()]})


def test_non_json_data_quality_is_refused(store):
    with pytest.raises(ValueError):
        _create(store, quality=("clean", object()))


def test_non_mapping_context_is_refused(store):
    with pytest.raises(ValueError):
        _create(store, context=["not", "a", "mapping"])


def test_errors_do_not_leak_the_payload(store):
    with pytest.raises(ValueError) as caught:
        _create(store, context={"secret": "s3cr3t-value", "raw": object()})
    assert "s3cr3t-value" not in str(caught.value)
    assert "s3cr3t-value" not in repr(caught.value)


# --- harness checks -------------------------------------------------------

def test_append_and_read_checks_roundtrip(store):
    snapshot_id = _create(store)
    record = check(snapshot_id)
    store.append_check(record)
    records = store.checks(snapshot_id)
    assert len(records) == 1
    assert records[0] == record
    assert records[0].execution_result is ExecutionResult.success
    assert records[0].reasons == ()


def test_checks_are_returned_in_insertion_order(store):
    snapshot_id = _create(store)
    first = check(snapshot_id).model_copy(update={"model_version": "first"})
    second = check(snapshot_id).model_copy(update={"model_version": "second"})
    third = check(snapshot_id).model_copy(update={"model_version": "third"})
    store.append_check(first)
    store.append_check(second)
    store.append_check(third)
    assert [r.model_version for r in store.checks(snapshot_id)] == ["first", "second", "third"]


def test_checks_survive_reopen(tmp_path):
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    store = ResearchStore(path)
    snapshot_id = _create(store)
    store.append_check(check(snapshot_id))
    assert ResearchStore(path).checks(snapshot_id) == (check(snapshot_id),)


def test_check_for_unknown_snapshot_is_refused(store):
    with pytest.raises(ValueError, match="snapshot"):
        store.append_check(check(uuid4()))
    assert store.checks(SNAPSHOT_ID) == ()


def test_failed_check_reasons_are_preserved(store):
    snapshot_id = _create(store)
    failed = check(snapshot_id).model_copy(update={
        "execution_result": ExecutionResult.snapshot_reference_broken,
        "reasons": ("evidence ids not in snapshot: " + EV_ABSENT,),
    })
    store.append_check(failed)
    records = store.checks(snapshot_id)
    assert records[0].execution_result is ExecutionResult.snapshot_reference_broken
    assert records[0].reasons == ("evidence ids not in snapshot: " + EV_ABSENT,)


def test_checks_of_unknown_snapshot_is_empty(store):
    assert store.checks(uuid4()) == ()


def test_checks_are_kept_per_snapshot(store):
    first = _create(store)
    second = _create(store)
    store.append_check(check(first))
    assert len(store.checks(first)) == 1
    assert store.checks(second) == ()


def test_a_failed_check_is_still_recorded(store):
    """A failing execution is audit evidence, not a reason to lose the record."""
    snapshot_id = _create(store)
    failed = check(snapshot_id).model_copy(update={
        "execution_result": ExecutionResult.tool_forbidden,
        "reasons": ("tool 'submit_order' not in whitelist for technical",),
    })
    store.append_check(failed)
    assert store.checks(snapshot_id)[0].execution_result is ExecutionResult.tool_forbidden


# --- tamper detection -----------------------------------------------------

def test_tampered_context_is_detected_on_read(tmp_path):
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    written = ResearchStore(path)
    snapshot_id = _create(written)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE research_snapshots SET context=? WHERE snapshot_id=?",
                       (json.dumps({"observations": [], "bars": []}),
                        str(snapshot_id)))
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="hash"):
        ResearchStore(path).get_snapshot(snapshot_id)


def test_tampered_as_of_is_detected_on_read(tmp_path):
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    written = ResearchStore(path)
    snapshot_id = _create(written)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE research_snapshots SET as_of=? WHERE snapshot_id=?",
                       ("2026-11-28T12:00:00+00:00", str(snapshot_id)))
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="hash"):
        ResearchStore(path).get_snapshot(snapshot_id)


def test_tampered_evidence_cannot_be_injected(tmp_path):
    """The stored evidence set is verified against the stored context."""
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    written = ResearchStore(path)
    snapshot_id = _create(written)
    connection = sqlite3.connect(path)
    connection.execute("UPDATE research_snapshots SET evidence_ids=? WHERE snapshot_id=?",
                       (json.dumps([EV_ABSENT]), str(snapshot_id)))
    connection.commit()
    connection.close()
    with pytest.raises(ValueError, match="hash"):
        ResearchStore(path).evidence_ids(snapshot_id)


# --- audit foreign key protection ----------------------------------------

def test_check_row_cannot_reference_an_absent_snapshot(tmp_path):
    """The audit table refuses an orphan row."""
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    store = ResearchStore(path)
    _create(store)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO research_checks(snapshot_id, role, prompt_version, model_version,"
            " input_hash, output_hash, execution_result, reasons, checked_at)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (str(uuid4()), "technical", 1, "m", "a" * 64, "b" * 64, "success", "[]",
             "2026-11-27T12:05:00+00:00"))
    connection.rollback()
    connection.close()
    assert store.checks(uuid4()) == ()


def test_deleting_a_snapshot_does_not_orphan_its_checks(tmp_path):
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    store = ResearchStore(path)
    snapshot_id = _create(store)
    store.append_check(check(snapshot_id))
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM research_snapshots WHERE snapshot_id=?", (str(snapshot_id),))
    connection.rollback()
    connection.close()
    assert len(store.checks(snapshot_id)) == 1


def test_store_creates_its_own_tables_without_touching_global_migrations(tmp_path):
    from gabfin.research.store import ResearchStore
    path = tmp_path / "research.sqlite"
    ResearchStore(path)
    connection = sqlite3.connect(path)
    tables = {row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert {"research_snapshots", "research_checks"} <= tables
    assert "schema_migrations" not in tables


# --- concurrency ----------------------------------------------------------

def test_concurrent_appends_all_land(store):
    """Two writers on the same file do not lose records."""
    snapshot_id = _create(store)
    errors = []

    def writer(tag):
        try:
            for index in range(10):
                store.append_check(check(snapshot_id).model_copy(update={
                    "model_version": f"{tag}-{index}"}))
        except Exception as exc:  # pragma: no cover - surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(tag,)) for tag in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(store.checks(snapshot_id)) == 20


# --- bounded context ------------------------------------------------------

def test_oversized_context_is_refused(store):
    """A context is bounded; an unbounded one is not a snapshot."""
    with pytest.raises(ValueError, match="too large"):
        _create(store, context={"bars": [{"evidence_id": EV_ONE, "close": "1" * 2_000_000}]})


def test_context_at_the_size_limit_is_accepted(store):
    from gabfin.research.store import ResearchStore
    limit = ResearchStore.MAX_CONTEXT_BYTES
    payload = {"bars": [{"evidence_id": EV_ONE, "close": "1" * (limit - 200)}]}
    snapshot_id = _create(store, context=payload)
    assert store.get_snapshot(snapshot_id)["context"]["bars"][0]["evidence_id"] == EV_ONE


def test_oversized_data_quality_is_refused(store):
    with pytest.raises(ValueError, match="too large"):
        _create(store, quality=("q" * 100_000,))


def test_many_context_items_are_refused(store):
    """Item count is bounded too, not only byte count."""
    payload = {"bars": [{"evidence_id": EV_ONE, "i": index} for index in range(50_000)]}
    with pytest.raises(ValueError, match="too large"):
        _create(store, context=payload)


# --- no secret leakage ----------------------------------------------------

def test_provider_url_is_not_echoed_in_an_error(store):
    """An error names the problem, never the payload it came from."""
    url = "https://private.example.test/v1/quotes?apikey=abc123"
    with pytest.raises(ValueError) as caught:
        _create(store, context={"bars": [{"evidence_id": EV_ONE, "url": url, "raw": object()}]})
    assert url not in str(caught.value)
    assert "abc123" not in str(caught.value)
    assert "private.example.test" not in str(caught.value)


def test_provider_token_is_not_echoed_in_an_error(store):
    token = "sk-live-0000000000000000"
    with pytest.raises(ValueError) as caught:
        _create(store, context={"token": token, "raw": object()})
    assert token not in str(caught.value)


def test_rejection_does_not_leave_a_partial_snapshot(store):
    """A refused snapshot leaves nothing behind."""
    with pytest.raises(ValueError):
        _create(store, context={"bars": [{"evidence_id": EV_ONE, "raw": object()}]})
    assert store.snapshot_ids() == ()

