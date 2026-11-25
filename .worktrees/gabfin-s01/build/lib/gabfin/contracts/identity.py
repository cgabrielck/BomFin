"""Untrusted identity/resource declarations; parsing grants no authority.

Task 3 must resolve server-owned sessions/registry, enforce role ceilings,
capability scope and resource ownership before any privileged service call.
"""
from enum import StrEnum
from typing import Self
from uuid import UUID
from pydantic import model_validator
from gabfin.contracts.common import VersionedContract


class Role(StrEnum):
    OWNER = 'owner'
    CHAT = 'chat'
    RESEARCH = 'research'
    STRATEGY = 'strategy'
    EXECUTOR = 'executor'


class Capability(StrEnum):
    READ_ACCOUNT = 'read_account'
    RESOLVE_SYMBOLS = 'resolve_symbols'
    START_RESEARCH = 'start_research'
    READ_REPORT = 'read_report'
    DRAFT_TRADE_PLAN = 'draft_trade_plan'
    READ_MARKET = 'read_market'
    MANAGE_WATCHLIST = 'manage_watchlist'
    PROPOSE_STRATEGY = 'propose_strategy'
    EMIT_STRATEGY_INTENT = 'strategy:emit'
    SUBMIT_ORDER = 'submit_order'
    CANCEL_ORDER = 'cancel_order'
    START_WORKER = 'start_worker'
    PAUSE_WORKER = 'pause_worker'
    RESUME_WORKER = 'resume_worker'
    WRITE_POLICY = 'write_policy'
    APPROVE_PROPOSAL = 'approve_proposal'


class Principal(VersionedContract):
    actor_id: UUID
    role: Role
    scope: tuple[Capability, ...]

    @model_validator(mode='after')
    def distinct_scope(self) -> Self:
        if len(set(self.scope)) != len(self.scope):
            raise ValueError('Capability scope cannot contain duplicates')
        return self


class ResourceKind(StrEnum):
    ACCOUNT = 'account'
    INSTRUMENT = 'instrument'
    RESEARCH_JOB = 'research_job'
    RESEARCH_REPORT = 'research_report'
    WATCHLIST = 'watchlist'
    ORDER = 'order'
    STRATEGY = 'strategy'
    POLICY = 'policy'
    PROPOSAL = 'proposal'
    ARTIFACT = 'artifact'


class Resource(VersionedContract):
    kind: ResourceKind
    id: UUID
    owner: UUID
