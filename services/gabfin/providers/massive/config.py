"""Environment-only Massive settings; diagnostics never serialize credentials."""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


def redact_key(value: str | SecretStr) -> str:
    """Mask the entire value, including short credentials."""
    return '****'


class MassiveConfig(BaseModel):
    """Explicit settings; use load_config to read the process environment.

    Endpoints are deliberately omitted from repr and dumps. Only the transport
    should read base_url, ws_url and api_key.get_secret_value().
    """

    model_config = ConfigDict(hide_input_in_errors=True, frozen=True, extra='forbid')

    base_url: str = Field(repr=False, exclude=True)
    api_key: SecretStr
    ws_path: str = '/ws'
    max_subscriptions: int = Field(default=100, ge=1, le=100)
    rest_qpm: int = Field(default=1000, ge=1, le=1000)

    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            _ = parts.port  # Validate the port without echoing an invalid URL.
        except ValueError:
            raise ValueError('Invalid MASSIVE_BASE_URL') from None
        if (parts.scheme != 'https' or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or '?' in value or '#' in value
                or any(char.isspace() or ord(char) < 32 for char in value)
                or '\\' in value):
            raise ValueError('Invalid MASSIVE_BASE_URL')
        return value.rstrip('/')

    @field_validator('api_key')
    @classmethod
    def validate_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError('Missing MASSIVE_API_KEY')
        return value

    @field_validator('ws_path')
    @classmethod
    def validate_ws_path(cls, value: str) -> str:
        if (not value.startswith('/') or value.startswith('//')
                or any(char in value for char in ('?', '#', '\\'))
                or any(char.isspace() or ord(char) < 32 for char in value)):
            raise ValueError('Invalid MASSIVE_WS_PATH')
        return value

    @property
    def ws_url(self) -> str:
        """Derive the credential-free WebSocket endpoint."""
        parts = urlsplit(self.base_url)
        scheme = 'wss' if parts.scheme == 'https' else 'ws'
        return urlunsplit((scheme, parts.netloc, parts.path + self.ws_path, '', ''))


def load_config() -> MassiveConfig:
    """Read process variables only; never load or write a dotenv file implicitly."""
    fields = {'base_url': 'BASE_URL', 'api_key': 'API_KEY', 'ws_path': 'WS_PATH',
              'max_subscriptions': 'MAX_SUBSCRIPTIONS', 'rest_qpm': 'REST_QPM'}
    values = {field: os.environ[f'MASSIVE_{name}'] for field, name in fields.items()
              if f'MASSIVE_{name}' in os.environ}
    missing = [f'MASSIVE_{fields[field]}' for field in ('base_url', 'api_key')
               if field not in values]
    if missing:
        # An empty model raises a ValidationError without including other values.
        from pydantic import ValidationError
        raise ValidationError.from_exception_data('MassiveConfig', [
            {'type': 'missing', 'loc': (name,), 'input': None} for name in missing
        ], hide_input=True)
    return MassiveConfig.model_validate(values)
