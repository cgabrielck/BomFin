"""Durable research snapshots and harness audit records.

A snapshot is the only thing a research conclusion may cite. It is
created once and never rewritten, and it declares the evidence it holds
before anything may cite it: the evidence ids a caller registers are the
only ids the snapshot's context may mention, so a conclusion cannot
reach past the snapshot it was given.

The stored document is hashed, so a reader can tell that what it reads
is what was written. The evidence set is verified against that same
hash, so a tampered row is refused rather than believed.

The store owns its own two tables and never touches the global schema
version table, so a research database can be opened beside a market one
without either pretending to be the other.
"""
import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from gabfin.research.harness import CheckResult, ExecutionResult

#: The evidence ids of one snapshot, as a canonical JSON array.
_EVIDENCE_KEY = "evidence_ids"
#: The hash of the canonical snapshot content, as stored in the row.
_HASH_KEY = "content_hash"
#: The context keys that carry a moment in time. A moment after the
#: snapshot cutoff is look-ahead, and look-ahead is refused.
_TIME_KEYS = ("event_at", "available_at", "published_at", "first_seen_at", "as_of",
              "received_at", "computed_at", "checked_at")
#: The context keys that carry a calendar date. A date after the cutoff
#: day is look-ahead; a date on the cutoff day is not.
_DATE_KEYS = ("release_date",)


class ResearchStoreError(ValueError):
    """The request is not valid research state. The message never carries the payload."""


def _canonical(value: Any) -> str:
    """One canonical JSON form for one value.

    The same content always produces the same text, so the same content
    always produces the same hash, whichever order the keys arrived in.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      default=_reject_unserialisable)


def _reject_unserialisable(value: Any) -> Any:
    raise ResearchStoreError("Snapshot content must be JSON serialisable")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _collect_evidence_ids(node: Any) -> set[str]:
    """Every `evidence_id` value anywhere in a context tree.

    Each id is canonicalised the same way a registered id is, so the
    same UUID written in a different but equivalent form still refers
    to the same evidence.
    """
    found: set[str] = set()
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key == "evidence_id":
                if isinstance(value, str) and not isinstance(value, bool):
                    try:
                        found.add(str(UUID(value)))
                    except (TypeError, ValueError, AttributeError) as exc:
                        raise ResearchStoreError(
                            "Context evidence ids must be UUIDs") from exc
            else:
                found |= _collect_evidence_ids(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            found |= _collect_evidence_ids(item)
    return found


def _require_snapshot_id(snapshot_id: Any) -> UUID:
    try:
        return snapshot_id if isinstance(snapshot_id, UUID) else UUID(str(snapshot_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ResearchStoreError("snapshot_id must be a UUID") from exc


def _require_as_of(as_of: Any) -> datetime:
    """An aware moment expressed in UTC.

    A naive timestamp is refused because it means different things in
    different places, and a timestamp with a non-zero offset is refused
    because it is not the UTC instant it claims to be. A zero offset is
    an unambiguous UTC instant and is normalised to UTC.
    """
    if not isinstance(as_of, datetime):
        raise ResearchStoreError("as_of must be a datetime")
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ResearchStoreError("as_of must be an aware UTC datetime")
    if as_of.utcoffset() != timedelta(0):
        raise ResearchStoreError("as_of must be expressed in UTC")
    return as_of.astimezone(timezone.utc)


def _require_json_mapping(value: Any, label: str) -> dict:
    if not isinstance(value, Mapping):
        raise ResearchStoreError(f"{label} must be a mapping")
    plain = deepcopy(dict(value))
    try:
        _canonical(plain)
    except ResearchStoreError:
        raise
    except (TypeError, ValueError) as exc:
        raise ResearchStoreError(f"{label} must be JSON serialisable") from exc
    return plain


def _require_json_sequence(value: Any, label: str) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ResearchStoreError(f"{label} must be a sequence")
    plain = deepcopy(list(value))
    try:
        _canonical(plain)
    except ResearchStoreError:
        raise
    except (TypeError, ValueError) as exc:
        raise ResearchStoreError(f"{label} must be JSON serialisable") from exc
    return plain


def _count_items(node: Any) -> int:
    """How many items a JSON document holds, counting containers themselves."""
    if isinstance(node, Mapping):
        return 1 + sum(_count_items(value) for value in node.values())
    if isinstance(node, (list, tuple)):
        return 1 + sum(_count_items(item) for item in node)
    return 1


def _require_bounded(document: Any, label: str, max_bytes: int, max_items: int) -> None:
    """Refuse a document too large to be one snapshot.

    The bound is on the stored form, so the size the caller pays for and
    the size the store keeps are the same size. The message names the
    limit and never the document, so a rejected payload cannot leak a
    provider url or a token through the error.
    """
    text = _canonical(document)
    if len(text.encode("utf-8")) > max_bytes:
        raise ResearchStoreError(f"{label} is too large; the limit is {max_bytes} bytes")
    if _count_items(document) > max_items:
        raise ResearchStoreError(f"{label} is too large; the limit is {max_items} items")


def _require_evidence_ids(value: Any) -> frozenset[str]:
    """A registered evidence set, normalised to a frozenset of UUID strings.

    Every id must be a UUID. A registered id that is not one is refused
    rather than stored, because an id nobody can resolve is not a
    reference to anything.
    """
    if value is None:
        return frozenset()
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ResearchStoreError("evidence_ids must be a set of evidence ids")
    ids: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ResearchStoreError("evidence_ids must be a set of evidence ids")
        try:
            ids.add(str(UUID(item)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ResearchStoreError("evidence_ids must be UUIDs") from exc
    return frozenset(ids)


def _parse_moment(value: Any) -> datetime | date | None:
    """The moment a text names, or None when the text names no moment.

    Text that cannot be parsed is left alone rather than guessed at: an
    unparsable timestamp is not evidence of look-ahead, and treating it
    as such would refuse honest data.

    Date-only text yields a date, so a day is never mistaken for the
    midnight that starts it.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _find_look_ahead(node: Any, cutoff: datetime) -> bool:
    """Whether any moment in the tree falls after the cutoff.

    A date-only value is compared on its date, so a release dated the
    cutoff day is not look-ahead.
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in _TIME_KEYS:
                moment = _parse_moment(value)
                if moment is None:
                    continue
                if isinstance(moment, datetime):
                    if moment.tzinfo is None:
                        moment = moment.replace(tzinfo=timezone.utc)
                    if moment.astimezone(timezone.utc) > cutoff:
                        return True
                elif moment > cutoff.date():
                    return True
            elif key in _DATE_KEYS:
                day = _parse_moment(value)
                if day is None:
                    continue
                if isinstance(day, datetime):
                    if day.tzinfo is None:
                        day = day.replace(tzinfo=timezone.utc)
                    day = day.astimezone(timezone.utc).date()
                if day > cutoff.date():
                    return True
            elif _find_look_ahead(value, cutoff):
                return True
    elif isinstance(node, (list, tuple)):
        for item in node:
            if _find_look_ahead(item, cutoff):
                return True
    return False


class ResearchStore:
    """Immutable research snapshots plus their harness audit trail.

    The store is the audit authority for research: it holds what a
    conclusion was allowed to see, and what the harness concluded about
    the run that cited it. Both are written once and read back exactly.
    """

    #: The largest context document that may be stored, in bytes. A
    #: snapshot is a frozen view of a research question; a document big
    #: enough to be a data dump is not one, and refusing it keeps the
    #: store a store rather than a warehouse.
    MAX_CONTEXT_BYTES = 1_048_576
    #: The largest number of items one context document may hold. The
    #: byte bound alone does not stop a document made of a million tiny
    #: items, which costs more to walk than it is worth to keep.
    MAX_CONTEXT_ITEMS = 10_000
    #: The largest data-quality document that may be stored, in bytes.
    MAX_QUALITY_BYTES = 65_536

    _SCHEMA = (
        """CREATE TABLE IF NOT EXISTS research_snapshots(
             snapshot_id TEXT PRIMARY KEY,
             as_of TEXT NOT NULL,
             context TEXT NOT NULL,
             data_quality TEXT NOT NULL,
             evidence_ids TEXT NOT NULL,
             content_hash TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS research_checks(
             check_id INTEGER PRIMARY KEY AUTOINCREMENT,
             snapshot_id TEXT NOT NULL REFERENCES research_snapshots(snapshot_id),
             role TEXT NOT NULL,
             prompt_version INTEGER NOT NULL,
             model_version TEXT NOT NULL,
             input_hash TEXT NOT NULL,
             output_hash TEXT NOT NULL,
             execution_result TEXT NOT NULL,
             reasons TEXT NOT NULL,
             checked_at TEXT NOT NULL)""",
    )

    def __init__(self, path: Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    @property
    def path(self) -> Path:
        """The database this store owns.

        Another component that keeps its own tables beside the
        snapshots may need the same file, and a store that hides its
        path would force a second copy of the path to be kept in step.
        """
        return self._path

    # --- plumbing ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5)
        connection.execute("pragma foreign_keys=ON")
        connection.execute("pragma journal_mode=WAL")
        connection.execute("pragma busy_timeout=5000")
        return connection

    def _ensure_schema(self) -> None:
        connection = self._connect()
        try:
            with connection:
                for statement in self._SCHEMA:
                    connection.execute(statement)
        finally:
            connection.close()

    # --- snapshots --------------------------------------------------------

    def create_snapshot(self, *, as_of: datetime, context: Mapping[str, Any],
                        data_quality: Sequence[str],
                        evidence_ids: Iterable[str],
                        snapshot_id: UUID | None = None) -> UUID:
        """Create one immutable snapshot and return its id.

        The evidence ids registered here are the only ids the context
        may mention: a context that cites an unregistered id is refused,
        so the snapshot can never be cited for evidence it does not
        hold. Registering the same content twice is accepted and changes
        nothing; registering different content under an id that already
        exists is refused.
        """
        identifier = _require_snapshot_id(snapshot_id) if snapshot_id is not None else uuid4()
        moment = _require_as_of(as_of)
        plain_context = _require_json_mapping(context, "context")
        plain_quality = _require_json_sequence(data_quality, "data_quality")
        _require_bounded(plain_context, "context",
                         self.MAX_CONTEXT_BYTES, self.MAX_CONTEXT_ITEMS)
        _require_bounded(plain_quality, "data_quality",
                         self.MAX_QUALITY_BYTES, self.MAX_CONTEXT_ITEMS)
        registered = _require_evidence_ids(evidence_ids)

        cited = _collect_evidence_ids(plain_context)
        unregistered = sorted(cited - registered)
        if unregistered:
            raise ResearchStoreError(
                "Context cites evidence ids that are not registered for this snapshot")
        if _find_look_ahead(plain_context, moment):
            raise ResearchStoreError("Context contains look-ahead data after as_of")

        content_hash = _digest(_canonical({
            "as_of": moment.isoformat(),
            "context": plain_context,
            "data_quality": plain_quality,
            _EVIDENCE_KEY: sorted(registered),
        }))

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT content_hash FROM research_snapshots WHERE snapshot_id=?",
                (str(identifier),)).fetchone()
            if row is not None:
                if row[0] != content_hash:
                    raise ResearchStoreError("Snapshot content conflict")
                connection.rollback()
                return identifier
            connection.execute(
                "INSERT INTO research_snapshots"
                "(snapshot_id, as_of, context, data_quality, evidence_ids, content_hash)"
                " VALUES(?,?,?,?,?,?)",
                (str(identifier), moment.isoformat(), _canonical(plain_context),
                 _canonical(plain_quality), _canonical(sorted(registered)), content_hash))
            connection.commit()
            return identifier
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def snapshot_ids(self) -> tuple[UUID, ...]:
        """Every stored snapshot id, oldest first."""
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT snapshot_id FROM research_snapshots ORDER BY rowid").fetchall()
        finally:
            connection.close()
        return tuple(UUID(row[0]) for row in rows)

    def _load_row(self, snapshot_id: UUID) -> tuple[str, dict, list, list] | None:
        """The stored row of one snapshot, verified, or None if there is none.

        The hash is checked before the row is handed back, so no caller
        ever sees a document that has been changed since it was written.
        """
        identifier = _require_snapshot_id(snapshot_id)
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT as_of, context, data_quality, evidence_ids, content_hash"
                " FROM research_snapshots WHERE snapshot_id=?",
                (str(identifier),)).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        as_of_text, context_text, quality_text, evidence_text, content_hash = row
        context = json.loads(context_text)
        quality = json.loads(quality_text)
        evidence = json.loads(evidence_text)
        self._verify_hash(content_hash, {
            "as_of": as_of_text,
            "context": context,
            "data_quality": quality,
            _EVIDENCE_KEY: evidence,
        })
        return as_of_text, context, quality, evidence

    def get_snapshot(self, snapshot_id: UUID) -> dict:
        """The research input payload of one snapshot.

        The returned dictionary is a deep copy; changing it changes
        nothing that is stored. A snapshot that was never registered is
        an error, because a caller that asks for a snapshot must not be
        handed an empty one that looks like a snapshot with no data.
        """
        loaded = self._load_row(snapshot_id)
        if loaded is None:
            raise KeyError(_require_snapshot_id(snapshot_id))
        as_of_text, context, quality, _evidence = loaded
        return {
            "snapshot_id": str(_require_snapshot_id(snapshot_id)),
            "as_of": datetime.fromisoformat(as_of_text),
            "context": deepcopy(context),
            "data_quality": deepcopy(quality),
        }

    def evidence_ids(self, snapshot_id: UUID) -> frozenset[str]:
        """The evidence ids one snapshot holds.

        The stored set is only trusted after the content hash confirms
        it still matches the stored context, so a tampered row is refused
        rather than believed.
        """
        loaded = self._load_row(snapshot_id)
        if loaded is None:
            raise KeyError(_require_snapshot_id(snapshot_id))
        return frozenset(str(item) for item in loaded[3])

    @staticmethod
    def _verify_hash(stored_hash: str, content: dict) -> None:
        if not isinstance(stored_hash, str) or stored_hash != _digest(_canonical(content)):
            raise ResearchStoreError("Snapshot content hash mismatch")

    # --- checks -----------------------------------------------------------

    def append_check(self, check: CheckResult) -> None:
        """Record one harness verdict against a snapshot that exists.

        A check for a snapshot the store does not hold is refused: an
        audit trail that can point at a snapshot nobody can read is not
        an audit trail.
        """
        if not isinstance(check, CheckResult):
            raise ResearchStoreError("check must be a CheckResult")
        identifier = _require_snapshot_id(check.snapshot_id)
        result = check.execution_result
        if not isinstance(result, ExecutionResult):
            raise ResearchStoreError("execution_result must be an ExecutionResult")
        checked_at = _require_as_of(check.checked_at)
        try:
            reasons_text = _canonical(list(check.reasons))
        except ResearchStoreError:
            raise
        except (TypeError, ValueError) as exc:
            raise ResearchStoreError("reasons must be JSON serialisable") from exc

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute(
                "SELECT 1 FROM research_snapshots WHERE snapshot_id=?",
                (str(identifier),)).fetchone()
            if exists is None:
                raise ResearchStoreError("check references an unknown snapshot")
            connection.execute(
                "INSERT INTO research_checks"
                "(snapshot_id, role, prompt_version, model_version, input_hash,"
                " output_hash, execution_result, reasons, checked_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (str(identifier), check.role, int(check.prompt_version),
                 check.model_version, check.input_hash, check.output_hash,
                 result.value, reasons_text, checked_at.isoformat()))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def checks(self, snapshot_id: UUID) -> tuple[CheckResult, ...]:
        """Every recorded verdict for one snapshot, oldest first."""
        identifier = _require_snapshot_id(snapshot_id)
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT role, prompt_version, model_version, input_hash, output_hash,"
                " execution_result, reasons, checked_at"
                " FROM research_checks WHERE snapshot_id=? ORDER BY check_id",
                (str(identifier),)).fetchall()
        finally:
            connection.close()
        records: list[CheckResult] = []
        for row in rows:
            role, prompt_version, model_version, input_hash, output_hash, result, reasons, checked_at = row
            records.append(CheckResult(
                role=role,
                prompt_version=int(prompt_version),
                model_version=model_version,
                snapshot_id=identifier,
                input_hash=input_hash,
                output_hash=output_hash,
                execution_result=ExecutionResult(result),
                reasons=tuple(json.loads(reasons)),
                checked_at=datetime.fromisoformat(checked_at),
            ))
        return tuple(records)
