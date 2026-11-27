"""Research-only option snapshots; absent Greeks and IV remain absent."""
import re
from urllib.parse import quote

from gabfin.providers.massive.rest import MassiveRestClient, MassiveRestError


class MassiveOptions:
    def __init__(self, client: MassiveRestClient):
        self._client = client

    def chain(self, underlying: str) -> tuple[dict, ...]:
        if not re.fullmatch(r'(?:I:)?[A-Z0-9.]+', underlying):
            raise ValueError('Invalid Massive underlying')
        path = f'/v3/snapshot/options/{quote(underlying, safe="")}?limit=250'
        rows = []
        for raw in self._client.results(path):
            details = raw.get('details')
            if not isinstance(details, dict) or not isinstance(details.get('ticker'), str):
                raise MassiveRestError('invalid_option_snapshot')
            greeks = raw.get('greeks')
            iv = raw.get('implied_volatility')
            if greeks is not None and not isinstance(greeks, dict):
                raise MassiveRestError('invalid_option_greeks')
            missing = []
            if not greeks:
                missing.append('greeks')
            if iv is None:
                missing.append('iv')
            coverage = 'missing_' + '_'.join(missing) if missing else 'available'
            if greeks and any(greeks.get(name) is None for name in ('delta', 'gamma', 'theta', 'vega')):
                coverage = 'partial_greeks' if not missing else coverage + '_partial_greeks'
            rows.append({**raw, 'source': 'massive', 'greeks': greeks or None,
                         'implied_volatility': iv,
                         'greeks_source': 'massive' if greeks else None,
                         'iv_source': 'massive' if iv is not None else None,
                         'coverage': coverage})
        return tuple(rows)
