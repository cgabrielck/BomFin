"""Provider sequences are opaque unless a feed explicitly declares otherwise."""
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(frozen=True)
class PreparedSequence:
    key: tuple
    frontier: int
    pending: frozenset[int]
    number: int
    facts: dict


def numeric_sequence(value):
    if isinstance(value, str) and len(value) <= 128 and value.isascii() and value.isdecimal():
        return int(value)
    return None


class SequenceTracker:
    """Bounded two-phase frontier: rejected events cannot fill a known hole."""
    def __init__(self, capacity):
        self._capacity = capacity
        self._state = {}
        self._facts = OrderedDict()

    @property
    def has_gaps(self):
        return any(pending for _, pending in self._state.values())

    def prepare(self, key, value, facts):
        number = numeric_sequence(value)
        if number is None:
            raise ValueError('invalid_contiguous_sequence')
        current = self._state.get(key)
        if current is None:
            return PreparedSequence(key, number, frozenset(), number, facts)
        frontier, retained = current
        pending = set(retained)
        if number <= frontier or number in pending:
            known = self._facts.get((key, number))
            if known is None:
                raise ValueError('sequence_reset_or_outside_retention')
            if known != facts:
                raise ValueError('sequence_identity_conflict')
        if number == frontier + 1:
            frontier = number
            while frontier + 1 in pending:
                pending.remove(frontier + 1)
                frontier += 1
        elif number > frontier + 1:
            pending.add(number)
        if len(pending) > self._capacity:
            raise ValueError('sequence_retention_capacity')
        return PreparedSequence(key, frontier, frozenset(pending), number, facts)

    def commit(self, prepared):
        self._state[prepared.key] = (prepared.frontier, prepared.pending)
        self._facts[(prepared.key, prepared.number)] = prepared.facts
        if len(self._facts) > self._capacity:
            self._facts.popitem(last=False)
