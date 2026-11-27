"""Read exact ticker metadata; a provider outage is not an unknown symbol."""
import re
from urllib.parse import quote

from gabfin.providers.massive.rest import MassiveRestError


class MassiveReference:
    def __init__(self, client):
        self.client = client

    def lookup(self, symbol):
        if not re.fullmatch(r'[A-Z]{1,6}(?:[.-][A-Z]{1,2})?', symbol):
            return None
        try:
            body = self.client.get('/v3/reference/tickers/' + quote(symbol, safe=''))
        except MassiveRestError as error:
            if error.status == 404:
                return None
            raise
        result = body.get('results')
        if not isinstance(result, dict):
            raise MassiveRestError('invalid_reference')
        return result
