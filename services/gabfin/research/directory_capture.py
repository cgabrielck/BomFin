"""Freeze verified list instruments using local tape and bounded daily history."""
from datetime import timedelta
import threading

from gabfin.analysis.sources import TapeBarSource
from gabfin.contracts.market import Timeframe, TimeUnit
from gabfin.research.capture import SnapshotCapture, _require_utc


class DirectoryCapture:
    def __init__(self, directory, store, tape_root, *, history=None):
        self.directory = directory
        self.store = store
        self.tape_root = tape_root
        self.history = history
        self._lock = threading.Lock()

    def __call__(self, instrument_id, *, as_of):
        as_of = _require_utc(as_of)
        metadata = self.directory.by_id(instrument_id)
        symbol = metadata['symbol']
        timeframe = Timeframe(count=1, unit=TimeUnit.TRADING_DAY)
        # Serialize import/read so two jobs never observe a half-written manifest.
        with self._lock:
            source = TapeBarSource(self.tape_root, symbol=symbol, source='massive')
            try:
                bars = tuple(source.bars(instrument_id, timeframe))
            except (KeyError, FileNotFoundError):
                bars = ()
            if not bars and self.history is not None:
                self.history.store(self.tape_root, symbol, timeframe=timeframe,
                    start=(as_of - timedelta(days=370)).date(), end=(as_of - timedelta(days=1)).date(), now=as_of)
                source = TapeBarSource(self.tape_root, symbol=symbol, source='massive')
            result = SnapshotCapture(self.store, bars=source).capture(
                instrument_id=instrument_id, symbol=symbol, timeframe=timeframe, as_of=as_of)
            return result['snapshot_id']
