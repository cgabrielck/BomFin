"""Quote-only gateway. Imports ``futu`` lazily and never opens a trade context."""
from __future__ import annotations

import logging
from typing import Any, Sequence

from backend.observe.errors import ObserveFailure, classify_gateway_message

logger = logging.getLogger(__name__)


def _rows(frame: Any) -> list[dict]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [row for row in frame if isinstance(row, dict)]
    to_dict = getattr(frame, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict(orient="records")
        except TypeError:
            records = to_dict()
        if isinstance(records, list):
            return [row for row in records if isinstance(row, dict)]
    return []


class FutuQuoteGateway:
    """Thin ``OpenQuoteContext`` wrapper. Connection happens on first use."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = int(port)
        self._ctx: Any = None

    def _client(self) -> Any:
        if self._ctx is not None:
            return self._ctx
        try:
            from futu import OpenQuoteContext
        except ImportError as exc:
            raise ObserveFailure("opend_unreachable", "quote client unavailable") from exc
        try:
            self._ctx = OpenQuoteContext(host=self.host, port=self.port)
        except Exception as exc:
            logger.info("futu observe degrade: opend_unreachable")
            raise ObserveFailure("opend_unreachable", "OpenD connection failed") from exc
        return self._ctx

    def _fail(self, ret: Any, data: Any) -> Any:
        if ret == 0:
            return data
        message = data if isinstance(data, str) else ""
        code = classify_gateway_message(message)
        logger.info("futu observe degrade: %s", code)
        raise ObserveFailure(code)

    def _kl(self, name: str) -> Any:
        try:
            from futu import KLType
        except ImportError as exc:
            raise ObserveFailure("opend_unreachable", "quote client unavailable") from exc
        value = getattr(KLType, name, None)
        if value is None:
            raise ObserveFailure("opend_unreachable", "native kl type is not on this client")
        return value

    def _subtypes(self, names: Sequence[str]) -> list[Any]:
        try:
            from futu import SubType
        except ImportError as exc:
            raise ObserveFailure("opend_unreachable", "quote client unavailable") from exc
        found: list[Any] = []
        for name in names:
            value = getattr(SubType, name, None)
            if value is None:
                raise ObserveFailure("opend_unreachable", "subscribe kind is not on this client")
            found.append(value)
        return found

    def _autype(self) -> Any:
        try:
            from futu import AuType
        except ImportError as exc:
            raise ObserveFailure("opend_unreachable", "quote client unavailable") from exc
        return AuType.QFQ

    def subscribe(self, codes: Sequence[str], subtypes: Sequence[str]) -> None:
        if not codes or not subtypes:
            return
        ctx = self._client()
        kinds = self._subtypes(subtypes)
        try:
            try:
                ret, data = ctx.subscribe(list(codes), kinds, is_first_push=False, subscribe_push=False)
            except TypeError:
                ret, data = ctx.subscribe(list(codes), kinds)
        except ObserveFailure:
            raise
        except Exception as exc:
            logger.info("futu observe degrade: opend_unreachable")
            raise ObserveFailure("opend_unreachable", "OpenD subscribe failed") from exc
        self._fail(ret, data)

    def unsubscribe(self, codes: Sequence[str], subtypes: Sequence[str]) -> None:
        if not codes or not subtypes or self._ctx is None:
            return
        kinds = self._subtypes(subtypes)
        try:
            ret, data = self._ctx.unsubscribe(list(codes), kinds)
        except Exception as exc:
            logger.info("futu observe degrade: opend_unreachable")
            raise ObserveFailure("opend_unreachable", "OpenD unsubscribe failed") from exc
        self._fail(ret, data)

    def snapshot(self, codes: Sequence[str]) -> list[dict]:
        if not codes:
            return []
        ctx = self._client()
        try:
            ret, data = ctx.get_market_snapshot(list(codes))
        except Exception as exc:
            logger.info("futu observe degrade: opend_unreachable")
            raise ObserveFailure("opend_unreachable", "OpenD snapshot failed") from exc
        return _rows(self._fail(ret, data))

    def history_kline(self, code: str, kl_type: str, max_count: int = 1000) -> list[dict]:
        ctx = self._client()
        try:
            result = ctx.request_history_kline(
                code,
                ktype=self._kl(kl_type),
                autype=self._autype(),
                max_count=int(max_count),
            )
        except ObserveFailure:
            raise
        except Exception as exc:
            logger.info("futu observe degrade: opend_unreachable")
            raise ObserveFailure("opend_unreachable", "OpenD history failed") from exc
        if not isinstance(result, tuple) or len(result) < 2:
            raise ObserveFailure("opend_unreachable", "OpenD history failed")
        ret, data = result[0], result[1]
        return _rows(self._fail(ret, data))

    def cur_kline(self, code: str, kl_type: str, num: int) -> list[dict]:
        ctx = self._client()
        try:
            ret, data = ctx.get_cur_kline(code, int(num), ktype=self._kl(kl_type), autype=self._autype())
        except ObserveFailure:
            raise
        except Exception as exc:
            logger.info("futu observe degrade: opend_unreachable")
            raise ObserveFailure("opend_unreachable", "OpenD kline failed") from exc
        return _rows(self._fail(ret, data))

    def close(self) -> None:
        ctx = self._ctx
        self._ctx = None
        if ctx is None:
            return
        closer = getattr(ctx, "close", None)
        if not callable(closer):
            return
        try:
            closer()
        except Exception:
            logger.info("futu observe degrade: opend_unreachable")
