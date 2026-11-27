"""Narrow single-page adapter for the pinned SDK's quote-only protocol hooks."""
from datetime import date

INVALID_PAGE = (0, '', (None, None))


class SinglePageHistoryContext:
    def __init__(self, context, *, pack_request, us_market):
        self.context = context
        self.pack_request = pack_request
        self.us_market = us_market

    def get_market_state(self, codes):
        return self.context.get_market_state(codes)

    def get_history_kl_quota(self, *, get_detail):
        return self.context.get_history_kl_quota(get_detail=get_detail)

    def close(self):
        return self.context.close()

    def _unpack(self, response):
        if not response.HasField('retType'):
            return INVALID_PAGE
        if response.retType != 0:
            return -1, 'history_failed', None
        if not response.HasField('s2c') or not response.s2c.HasField('security'):
            return INVALID_PAGE
        page = response.s2c
        if page.security.market != self.us_market or page.security.code != 'AAPL' or len(page.klList) > 2:
            return INVALID_PAGE
        records = []
        for item in page.klList:
            if not item.HasField('time') or not item.HasField('isBlank'):
                return INVALID_PAGE
            # A new dict for every protobuf record; missing prices stay missing.
            records.append({'code': 'US.AAPL', 'time_key': item.time, **{
                field: getattr(item, wire_field) if not item.isBlank and item.HasField(wire_field) else None
                for field, wire_field in [('open', 'openPrice'), ('high', 'highPrice'),
                                          ('low', 'lowPrice'), ('close', 'closePrice')]
            }})
        token = bytes(page.nextReqKey) if page.HasField('nextReqKey') else None
        return 0, '', (records, token)

    def request_history_kline(self, code, **kwargs):
        if code != 'US.AAPL' or kwargs['max_count'] != 2 or kwargs['page_req_key'] is not None:
            raise ValueError('history_request_scope')
        day = date.fromisoformat(kwargs['start']).isoformat()
        if kwargs['start'] != day or kwargs['end'] != day:
            raise ValueError('history_date_scope')
        # _query_sync sends once and does not wait/retry for a ready connection.
        ret, _, data = self.context._query_sync(
            self.pack_request, self._unpack, code=code,
            start_date=day + ' 00:00:00', end_date=day + ' 23:59:59', ktype=kwargs['ktype'],
            autype=kwargs['autype'], fields=kwargs['fields'], max_num=2,
            conn_id=self.context.get_sync_conn_id(), next_req_key=None,
            extended_time=kwargs['extended_time'], session=kwargs['session'],
            security_firm=self.context.get_security_firm())
        return (ret, data[0], data[1]) if ret == 0 else (ret, None, None)
