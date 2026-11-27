"""Resolve a bounded user list using only an authoritative injected lookup."""
import re
from collections.abc import Callable, Mapping

_SYMBOL = re.compile(r'[A-Z]{1,6}(?:[.-][A-Z]{1,2})?\Z')


def resolve_batch(text: str, lookup: Callable[[str], Mapping | None]) -> list[dict]:
    if not isinstance(text, str) or len(text) > 8192:
        raise ValueError('Invalid symbol list')
    symbols = list(dict.fromkeys(part.upper() for part in re.split(r'[\s,;，；]+', text.strip()) if part))
    if not symbols or len(symbols) > 50:
        raise ValueError('Provide between 1 and 50 unique symbols')
    results = []
    for symbol in symbols:
        if not _SYMBOL.fullmatch(symbol):
            results.append({'symbol': symbol, 'status': 'invalid', 'instrument_id': None})
            continue
        from gabfin.providers.massive.rest import MassiveRestError
        try:
            value = lookup(symbol)
        except MassiveRestError as error:
            results.append({'symbol': symbol, 'status': 'unavailable', 'instrument_id': None,
                            'reason': 'rate_limited' if error.status == 429 else 'provider_unavailable'})
            continue
        if value is None:
            results.append({'symbol': symbol, 'status': 'unknown', 'instrument_id': None})
        else:
            row = {'symbol': symbol, 'status': 'resolved', 'instrument_id': str(value['instrument_id'])}
            if isinstance(value.get('name'), str):
                row['name'] = value['name']
            results.append(row)
    return results
