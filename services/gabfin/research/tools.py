"""Read-only tools bound to one frozen research snapshot."""
from copy import deepcopy


class SnapshotTools:
    """No model arguments can select another account, path, symbol or snapshot."""

    FIELDS = {
        'resolve_symbols': 'symbols', 'read_observations': 'observations',
        'read_massive_snapshot': 'massive_snapshot', 'read_bars': 'bars',
        'compute_indicators': 'indicators', 'read_quote_snapshot': 'quote',
        'read_account': 'account', 'read_risk_limits': 'limits',
    }

    def __init__(self, context: dict):
        self._context = deepcopy(context)

    def mapping(self):
        def bind(field):
            async def read(arguments):
                if not isinstance(arguments, dict) or arguments:
                    raise ValueError('Snapshot tools accept only an empty argument object')
                if field not in self._context:
                    raise ValueError('Snapshot data unavailable')
                return deepcopy(self._context[field])
            return read
        return {name: bind(field) for name, field in self.FIELDS.items()}
