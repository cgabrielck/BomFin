"""LangGraph orchestration with application-owned tools and validation.

The model adapter receives only rendered prompts and a guarded tool callback.
It must honour max_output_tokens; provider credentials stay in the adapter.
"""
import asyncio
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from time import monotonic
from typing import Any, TypedDict
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from langgraph.graph import END, START, StateGraph
from referencing import Registry, Resource

from gabfin.research.harness import ExecutionResult, Harness
from gabfin.research.roles import load_all_role_cards, render_prompt


@dataclass(frozen=True)
class ModelRequest:
    role: str
    system: str
    user: str
    max_output_tokens: int
    max_input_tokens: int = 20000


@dataclass(frozen=True)
class ModelReply:
    output: dict
    input_tokens: int
    output_tokens: int
    model_version: str


class ToolDenied(PermissionError):
    pass


class GraphState(TypedDict, total=False):
    payload: dict
    reports: dict
    audit: list
    status: str


class ResearchRuntime:
    def __init__(self, roles_dir: Path, schema_dir: Path, *, model: Callable,
                 tools: Mapping[str, Callable[[dict], Awaitable[Any]]],
                 snapshot_evidence: Mapping[UUID, frozenset[str]],
                 audit_sink: Callable | None = None):
        self.cards = load_all_role_cards(roles_dir)
        self.model = model
        self.tools = dict(tools)
        self.harness = Harness(snapshot_evidence)
        self.audit_sink = audit_sink
        self.snapshots = dict(snapshot_evidence)
        documents = {p.name: json.loads(p.read_text(encoding='utf-8'))
                     for p in schema_dir.glob('*.json')}
        registry = Registry().with_resources(
            (name, Resource.from_contents(doc)) for name, doc in documents.items())
        self.validators = {}
        self.output_schemas = {}
        for name, card in self.cards.items():
            for kind, ref in [('input', card.inputs), ('output', card.outputs)]:
                doc = documents[Path(ref).name]
                Draft202012Validator.check_schema(doc)
                self.validators[name, kind] = Draft202012Validator(
                    doc, registry=registry, format_checker=FormatChecker())
            # Inline the shared definition so the model sees the full schema.
            schema = deepcopy(documents['common.json']['$defs']['output'])
            schema['properties']['role'] = {'const': name}
            self.output_schemas[name] = schema

    async def run(self, role: str, payload: dict) -> dict:
        card = self.cards[role]
        payload = deepcopy(payload)
        try:
            self.validators[role, 'input'].validate(payload)
        except ValidationError as exc:
            raise ValueError(f'Invalid research input: {exc.message}') from exc
        snapshot = UUID(payload['snapshot_id'])
        if snapshot not in self.snapshots:
            raise ValueError('Snapshot is not registered')
        # Separate role-local context: never pass another model's messages.
        keys = {'discovery': ('observations',), 'technical': ('bars', 'indicators'),
                'portfolio': ('account', 'limits')}[role]
        context = {key: payload['context'][key] for key in keys}
        prompt_context = {**context, 'snapshot_id': str(snapshot), 'as_of': payload['as_of'],
                          'data_quality': payload['data_quality']}
        system = render_prompt(card, 'system', {
            'tools': card.tools, 'output_schema': json.dumps(self.output_schemas[role])})
        user = render_prompt(card, 'user', prompt_context)
        cache_key = hashlib.sha256(json.dumps({
            'role': role, 'card': card.model_dump(mode='json'), 'system': system, 'user': user,
            'evidence': sorted(self.snapshots[snapshot])},
            sort_keys=True).encode()).hexdigest()
        records = []
        total_input = total_output = 0
        started = monotonic()
        for attempt in range(1, card.budget.max_attempts_per_node + 1):
            called = []
            denied = False
            tool_count = 0

            async def dispatch(name: str, arguments: dict):
                nonlocal denied, tool_count
                called.append(name)
                # Check before looking up or invoking the actual function.
                if name not in card.tools or name not in self.tools:
                    denied = True
                    raise ToolDenied(f'Tool unavailable for {role}: {name}')
                tool_count += 1
                if tool_count > 100:
                    denied = True
                    raise ToolDenied('Tool-call limit exceeded')
                remaining = card.budget.deadline_seconds - (monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('Research deadline exceeded')
                return await asyncio.wait_for(self.tools[name](deepcopy(arguments)), remaining)

            error = None
            try:
                remaining = card.budget.deadline_seconds - (monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('Research deadline exceeded')
                reply = await asyncio.wait_for(self.model(
                    ModelRequest(role, system, user, card.budget.max_output_tokens - total_output,
                                 card.budget.max_input_tokens - total_input),
                    dispatch), remaining)
                if (type(reply.input_tokens) is not int or type(reply.output_tokens) is not int
                        or reply.input_tokens < 0 or reply.output_tokens < 0):
                    raise ValueError('Model adapter must report nonnegative token counts')
                total_input += reply.input_tokens
                total_output += reply.output_tokens
            except ToolDenied as exc:
                error = str(exc)
                reply = ModelReply({}, 0, 0, 'unavailable')
            except TimeoutError:
                error = 'Research deadline exceeded'
                reply = ModelReply({}, 0, 0, 'unavailable')
            except Exception as exc:
                # Persist only the type, never a provider error containing secrets.
                error = f'Model/tool failure: {type(exc).__name__}'
                reply = ModelReply({}, 0, 0, 'unavailable')

            def validate_output(data):
                if error:
                    return error
                errors = sorted(self.validators[role, 'output'].iter_errors(data), key=lambda e: str(e.path))
                if errors:
                    return errors[0].message
                if data['snapshot_id'] != str(snapshot):
                    return 'Output snapshot differs from input snapshot'
                if denied:
                    return 'Forbidden tool attempt'
                return None

            record = self.harness.validate(
                card, snapshot_id=snapshot, tools_called=tuple(called), output=reply.output,
                input_payload=payload, input_tokens=total_input, output_tokens=total_output,
                elapsed_seconds=monotonic() - started, attempts=attempt,
                model_version=reply.model_version, output_validator=validate_output)
            if self.audit_sink is not None:
                # Durable evidence must exist before any successful report escapes.
                await asyncio.to_thread(self.audit_sink, record)
            records.append(record)
            if record.execution_result is ExecutionResult.success:
                return {'status': 'success', 'report': deepcopy(reply.output),
                        'audit': records, 'cache_key': cache_key}
            if error is not None:
                # A failed provider/tool turn may have spent unreported tokens.
                # Retrying it as zero usage could exceed the configured budget.
                break
            if denied or record.execution_result in {ExecutionResult.tool_forbidden, ExecutionResult.budget_exceeded}:
                break
            if total_input >= card.budget.max_input_tokens or total_output >= card.budget.max_output_tokens:
                break
        return {'status': 'invalid', 'report': None, 'audit': records, 'cache_key': cache_key}


def build_research_graph(runtime: ResearchRuntime):
    graph = StateGraph(GraphState)
    for role in ('discovery', 'technical', 'portfolio'):
        def make_node(name):
            async def node(state):
                result = await runtime.run(name, state['payload'])
                reports = dict(state.get('reports', {}))
                if result['report'] is not None:
                    reports[name] = result['report']
                return {'reports': reports, 'status': result['status'],
                        'audit': [*state.get('audit', []), *result['audit']]}
            return node
        graph.add_node(role, make_node(role))
    graph.add_edge(START, 'discovery')
    for role, next_role in [('discovery', 'technical'), ('technical', 'portfolio')]:
        graph.add_conditional_edges(role, lambda state: state['status'],
                                    {'success': next_role, 'invalid': END})
    graph.add_edge('portfolio', END)
    return graph.compile()
