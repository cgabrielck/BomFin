"""Finite canonical instrument snapshots; no metadata guessing or provider I/O."""
from decimal import Decimal
import re
from uuid import UUID

from gabfin.contracts.market import AssetClass, Instrument

TICKER = r'[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*'


def valid_us_symbol(symbol: str) -> bool:
    return re.fullmatch(r'US\.' + TICKER, symbol) is not None


class InstrumentCatalog:
    def __init__(self, instruments):
        self._instruments = {}
        self._symbols = {}
        economic_options = set()
        for value in instruments:
            instrument = Instrument.model_validate(value.model_dump(mode='python'))
            identifier = instrument.instrument_id
            if identifier in self._instruments:
                raise ValueError('Duplicate canonical instrument')
            for source, symbol in instrument.vendor_symbols.items():
                if (source == 'futu' and instrument.asset_class == AssetClass.EQUITY
                        and re.fullmatch(r'(?:US|HK)\.' + TICKER + r'[0-9]{6}[CP][0-9]+', symbol)):
                    raise ValueError('Equity cannot claim a Futu option symbol')
                if (source, symbol) in self._symbols:
                    raise ValueError('Ambiguous source symbol')
                self._symbols[source, symbol] = identifier
            self._instruments[identifier] = instrument
        for instrument in self._instruments.values():
            terms = instrument.option
            if terms is None:
                continue
            underlying = self._instruments.get(terms.underlying_id)
            if underlying is None or underlying.asset_class != AssetClass.EQUITY:
                raise ValueError('Option requires a registered equity underlying')
            identity = (terms.underlying_id, terms.expiry, terms.right, terms.strike,
                        terms.multiplier, instrument.currency)
            if identity in economic_options:
                raise ValueError('Duplicate canonical option terms')
            economic_options.add(identity)
            symbol = instrument.vendor_symbols.get('futu')
            if symbol is not None and symbol.startswith('US.'):
                root = underlying.vendor_symbols.get('futu', '')
                prefix = root + terms.expiry.strftime('%y%m%d') + ('C' if terms.right == 'call' else 'P')
                suffix = symbol[len(prefix):] if symbol.startswith(prefix) else ''
                if (not valid_us_symbol(root) or not re.fullmatch(r'[0-9]{1,12}', suffix)
                        or Decimal(suffix + 'e-3') != terms.strike):
                    raise ValueError('Futu US option symbol conflicts with canonical terms')

    def get(self, identifier: UUID) -> Instrument | None:
        value = self._instruments.get(identifier)
        return value.model_copy(deep=True) if value is not None else None

    def resolve(self, source: str, symbol: str) -> Instrument:
        return self.get(self._symbols[source, symbol])
