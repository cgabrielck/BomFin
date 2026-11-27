"""S4 provider-swappable model adapter (OpenAI-compatible chat completions).

The adapter owns the provider credential and the HTTP call; the research
runtime owns prompts, tool permission, and budgets. Only read-only
application tools are offered to the provider, and the actual permission is
always decided by the guarded dispatch callback supplied by the caller.

Failure handling: every provider fault surfaces as a `ModelProviderError`
whose message is a fixed reason token. URLs, request bodies, response
bodies, and credentials never appear in an error message or a log record.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import urllib.error
import urllib.request

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from gabfin.research.nodes import ModelReply, ModelRequest, ToolDenied


# Fixed reason tokens. These are the only provider error strings a caller
# may observe; they never embed provider data.
REASONS = frozenset({
    'config_invalid',
    'request_failed',
    'http_error',
    'redirect_blocked',
    'invalid_response',
    'usage_missing',
    'usage_invalid',
    'output_not_json',
    'output_not_object',
    'tool_not_allowed',
    'tool_dispatch_failed',
    'tool_loop_exhausted',
    'budget_exhausted',
})


class ModelProviderError(RuntimeError):
    """Stable failure code with no provider payload, endpoint, or credential.

    The message is a fixed reason token plus, for HTTP failures, the numeric
    status code. No provider body, URL, header, or credential is ever included.
    """

    def __init__(self, reason: str, *, status: int = 0):
        if reason not in REASONS:
            reason = 'request_failed'
        message = f'{reason}:{status}' if status else reason
        super().__init__(message)
        self.reason = reason
        self.status = status


# Application-owned tool surface per research role. This mapping is fixed in
# code: a role card can never widen it, and the runtime's dispatch callback
# remains the real permission boundary.
ROLE_TOOLS: Mapping[str, tuple[str, ...]] = {
    'discovery': ('resolve_symbols', 'read_observations', 'read_massive_snapshot'),
    'technical': ('read_bars', 'compute_indicators', 'read_quote_snapshot'),
    'portfolio': ('read_account', 'read_risk_limits'),
}

# The provider may only ask for an empty argument object. Tool inputs are
# bound by the service, not by the model.
TOOL_PARAMETERS: Mapping[str, Any] = {
    'type': 'object',
    'properties': {},
    'additionalProperties': False,
}

MAX_TOOL_ROUNDS = 8


@dataclass(frozen=True)
class ModelHttpRequest:
    """One outbound HTTP request. `headers` carries the credential."""

    url: str = field(repr=False)
    headers: Mapping[str, str] = field(repr=False)
    body: bytes = field(repr=False)
    timeout: float = 0.0


@dataclass(frozen=True)
class ModelHttpResponse:
    """One inbound HTTP response; only `status` and `body` are used."""

    status: int
    body: bytes = field(repr=False)


# A transport is a synchronous callable so a test can inject a fake and the
# production path can use the standard library without an async HTTP client.
Transport = Callable[[ModelHttpRequest], ModelHttpResponse]


class ModelConfig(BaseModel):
    """Explicit provider settings; use load_model_config to read the environment.

    The endpoint and the credential are hidden from repr, dumps, and logs.
    """

    model_config = ConfigDict(hide_input_in_errors=True, frozen=True, extra='forbid')

    base_url: str = Field(repr=False, exclude=True)
    api_key: SecretStr
    model: str
    timeout_seconds: float = Field(default=60.0, gt=0, le=3600)

    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        try:
            parts = urlsplit(value)
            _ = parts.port
        except ValueError:
            raise ValueError('Invalid LLM_BASE_URL') from None
        if (parts.scheme != 'https' or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or '?' in value or '#' in value
                or any(char.isspace() or ord(char) < 32 for char in value)
                or '\\' in value or '..' in parts.path):
            raise ValueError('Invalid LLM_BASE_URL')
        return value.rstrip('/')

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError('Missing LLM_API_KEY')
        return value

    @field_validator('model')
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value.strip() or any(char.isspace() or ord(char) < 32 for char in value):
            raise ValueError('Invalid LLM_MODEL')
        return value

    @property
    def chat_completions_url(self) -> str:
        """Derive the endpoint; the credential never appears in the URL."""
        return f'{self.base_url}/chat/completions'


def load_model_config() -> ModelConfig:
    """Read the process environment only; never load a dotenv file implicitly."""
    fields = {'base_url': 'LLM_BASE_URL', 'api_key': 'LLM_API_KEY', 'model': 'LLM_MODEL'}
    values = {field: os.environ[name] for field, name in fields.items() if name in os.environ}
    missing = [f'LLM_{fields[field]}' for field in ('base_url', 'api_key', 'model')
               if field not in values]
    if missing:
        from pydantic import ValidationError
        raise ValidationError.from_exception_data('ModelConfig', [
            {'type': 'missing', 'loc': (name,), 'input': None} for name in missing
        ], hide_input=True)
    timeout = os.environ.get('LLM_TIMEOUT_SECONDS')
    if timeout is not None:
        values['timeout_seconds'] = timeout
    return ModelConfig.model_validate(values)


def _default_transport(request: ModelHttpRequest) -> ModelHttpResponse:
    """Standard-library HTTPS call that never follows a redirect."""

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    req = urllib.request.Request(request.url, data=request.body, method='POST')
    for name, value in request.headers.items():
        req.add_header(name, value)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req, timeout=request.timeout) as handle:
            return ModelHttpResponse(handle.status, handle.read())
    except urllib.error.HTTPError as error:
        return ModelHttpResponse(error.code, error.read())


class OpenAICompatibleModel:
    """Chat-completions adapter for any OpenAI-compatible endpoint.

    `transport` is injectable so tests run without network access. The
    callable is synchronous and runs inside `asyncio.to_thread`.
    """

    def __init__(self, config: ModelConfig, *, transport: Transport | None = None):
        self._config = config
        self._transport = transport or _default_transport

    @property
    def config(self) -> ModelConfig:
        return self._config

    async def __call__(self, request: ModelRequest,
                       dispatch: Callable[[str, dict], Awaitable[Any]]) -> ModelReply:
        """Run one research turn, including any bounded tool round trips."""
        tool_names = ROLE_TOOLS.get(request.role, ())
        messages: list[dict[str, Any]] = [
            {'role': 'system', 'content': request.system},
            {'role': 'user', 'content': request.user},
        ]
        total_input = 0
        total_output = 0
        remaining = int(request.max_output_tokens)
        if remaining <= 0:
            raise ModelProviderError('budget_exhausted')

        for _ in range(MAX_TOOL_ROUNDS):
            if total_input >= request.max_input_tokens:
                raise ModelProviderError('budget_exhausted')
            payload = self._build_payload(messages, tool_names, remaining)
            response = await self._post(payload)
            choice, usage, version = self._parse_response(response)
            total_input += usage[0]
            total_output += usage[1]
            # The next round may only ask for what the budget still allows.
            remaining -= usage[1]
            tool_calls = choice.get('tool_calls') or []
            if not tool_calls:
                content = choice.get('content')
                output = self._parse_content(content)
                return ModelReply(output, total_input, total_output, version)
            if remaining <= 0:
                raise ModelProviderError('budget_exhausted')
            messages = await self._run_tools(messages, tool_calls, tool_names, dispatch)

        raise ModelProviderError('tool_loop_exhausted')

    # ---------------------------------------------------------------- payload

    def _build_payload(self, messages: list[dict[str, Any]], tool_names: tuple[str, ...],
                       remaining: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            'model': self._config.model,
            'messages': messages,
            'max_tokens': remaining,
            'temperature': 0,
        }
        if tool_names:
            payload['tools'] = [
                {'type': 'function',
                 'function': {'name': name, 'description': f'Application read-only tool {name}.',
                              'parameters': dict(TOOL_PARAMETERS)}}
                for name in tool_names
            ]
        return payload

    # ------------------------------------------------------------------- http

    async def _post(self, payload: Mapping[str, Any]) -> ModelHttpResponse:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = ModelHttpRequest(
            url=self._config.chat_completions_url,
            headers={'Authorization': f'Bearer {self._config.api_key.get_secret_value()}',
                     'Content-Type': 'application/json',
                     'Accept': 'application/json'},
            body=body,
            timeout=self._config.timeout_seconds,
        )
        try:
            response = await asyncio.to_thread(self._transport, request)
        except Exception:
            raise ModelProviderError('request_failed') from None
        if not isinstance(response, ModelHttpResponse):
            raise ModelProviderError('invalid_response')
        if response.status in (301, 302, 303, 307, 308):
            raise ModelProviderError('redirect_blocked', status=response.status)
        if response.status != 200:
            raise ModelProviderError('http_error', status=response.status)
        return response

    # --------------------------------------------------------------- parsing

    def _parse_response(self, response: ModelHttpResponse
                        ) -> tuple[dict[str, Any], tuple[int, int], str]:
        try:
            document = json.loads(response.body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ModelProviderError('invalid_response') from None
        if not isinstance(document, dict):
            raise ModelProviderError('invalid_response')
        choices = document.get('choices')
        if not isinstance(choices, list) or not choices:
            raise ModelProviderError('invalid_response')
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ModelProviderError('invalid_response')
        message = choice.get('message')
        if not isinstance(message, dict):
            raise ModelProviderError('invalid_response')
        usage = document.get('usage')
        if not isinstance(usage, dict):
            raise ModelProviderError('usage_missing')
        prompt_tokens = usage.get('prompt_tokens')
        completion_tokens = usage.get('completion_tokens')
        if (type(prompt_tokens) is not int or type(completion_tokens) is not int
                or prompt_tokens < 0 or completion_tokens < 0):
            raise ModelProviderError('usage_invalid')
        # Track the model the provider actually served, not just the requested one.
        served = document.get('model')
        version = served.strip() if isinstance(served, str) and served.strip() \
            else self._config.model
        return message, (prompt_tokens, completion_tokens), version

    def _parse_content(self, content: Any) -> dict[str, Any]:
        """Accept only a bare JSON object; fences and prose are rejected."""
        if not isinstance(content, str) or not content.strip():
            raise ModelProviderError('output_not_json')
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            raise ModelProviderError('output_not_json') from None
        if not isinstance(parsed, dict):
            raise ModelProviderError('output_not_object')
        return parsed

    # ------------------------------------------------------------------ tools

    async def _run_tools(self, messages: list[dict[str, Any]], tool_calls: list[Any],
                         tool_names: tuple[str, ...],
                         dispatch: Callable[[str, dict], Awaitable[Any]]
                         ) -> list[dict[str, Any]]:
        """Execute each tool call through the caller's guarded callback."""
        if not isinstance(tool_calls, list):
            raise ModelProviderError('invalid_response')
        updated = list(messages)
        updated.append({'role': 'assistant', 'content': None,
                        'tool_calls': [_normalise_tool_call(call) for call in tool_calls]})
        for call in tool_calls:
            normalised = _normalise_tool_call(call)
            name = normalised['function']['name']
            if name not in tool_names:
                raise ModelProviderError('tool_not_allowed')
            arguments = _parse_arguments(normalised['function']['arguments'])
            try:
                result = await dispatch(name, arguments)
            except (ToolDenied, TimeoutError):
                # Permission and deadline decisions belong to the runtime; the
                # adapter must not mask them as a provider fault.
                raise
            except Exception:
                raise ModelProviderError('tool_dispatch_failed') from None
            updated.append({'role': 'tool', 'tool_call_id': normalised['id'],
                            'name': name, 'content': _tool_result_content(result)})
        return updated


def _normalise_tool_call(call: Any) -> dict[str, Any]:
    if not isinstance(call, dict):
        raise ModelProviderError('invalid_response')
    function = call.get('function')
    if not isinstance(function, dict):
        raise ModelProviderError('invalid_response')
    name = function.get('name')
    if not isinstance(name, str) or not name:
        raise ModelProviderError('invalid_response')
    call_id = call.get('id')
    if not isinstance(call_id, str) or not call_id:
        raise ModelProviderError('invalid_response')
    arguments = function.get('arguments')
    if not isinstance(arguments, str):
        raise ModelProviderError('invalid_response')
    return {'id': call_id, 'type': 'function',
            'function': {'name': name, 'arguments': arguments}}


def _parse_arguments(raw: str) -> dict[str, Any]:
    """Tool arguments must be a JSON object; the model may not invent inputs."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise ModelProviderError('invalid_response') from None
    if not isinstance(parsed, dict):
        raise ModelProviderError('invalid_response')
    return parsed


def _tool_result_content(result: Any) -> str:
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return '{}'
