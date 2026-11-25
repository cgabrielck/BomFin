"""Deterministic Futu US subscription targets and advisory, context-owned deltas."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter

from gabfin.contracts.common import UtcTimestamp
from gabfin.contracts.market import AssetClass, MarketSession, Timeframe, NonNegativeCounter
from gabfin.contracts.subscriptions import Demand, FeedCapabilities, SubscriptionKey, SubscriptionPlan, SubscriptionRejection
from gabfin.providers.futu.symbols import InstrumentCatalog, valid_us_symbol

PRIORITY = {name: index for index, name in enumerate(('holding', 'chart', 'strategy', 'watchlist', 'candidate'))}


@dataclass(frozen=True)
class ChannelSupport:
    channel: str
    timeframe: Timeframe | None = None
    asset_class: AssetClass = field(kw_only=True)
    session: MarketSession = field(kw_only=True)

    def __post_init__(self):
        object.__setattr__(self, 'asset_class', AssetClass(self.asset_class))
        object.__setattr__(self, 'session', MarketSession(self.session))
        if self.channel not in ('quote', 'trade', 'bar') or (self.channel == 'bar') != (self.timeframe is not None):
            raise ValueError('Explicit channel/timeframe support is required')
        if self.timeframe is not None:
            object.__setattr__(self, 'timeframe', Timeframe.model_validate(self.timeframe.model_dump()))

    @property
    def identity(self):
        return self.asset_class, self.session, (self.channel, None if self.timeframe is None else (self.timeframe.count, self.timeframe.unit))


@dataclass(frozen=True)
class QuotaBudget:
    """Net target capacities including our current keys, after external reservations."""
    equity_slots: int | None
    option_chain_slots: int | None
    checked_at: datetime

    def __post_init__(self):
        for name in ('equity_slots', 'option_chain_slots'):
            TypeAdapter(NonNegativeCounter | None).validate_python(getattr(self, name))
        object.__setattr__(self, 'checked_at', TypeAdapter(UtcTimestamp).validate_python(self.checked_at))


@dataclass(frozen=True)
class SubscriptionSchedule:
    plan: SubscriptionPlan
    subscribe: tuple[SubscriptionKey, ...]
    unsubscribe: tuple[SubscriptionKey, ...]
    apply_allowed: bool
    blocked_reasons: tuple[str, ...]


def _sort_key(key):
    tf = key.timeframe
    return str(key.instrument_id), key.channel, '' if tf is None else tf.unit, 0 if tf is None else tf.count


def plan_subscriptions(demands, caps: FeedCapabilities, catalog: InstrumentCatalog, *,
                       as_of: datetime, session: MarketSession, max_snapshot_age: timedelta,
                       budget: QuotaBudget, supported, current=()) -> SubscriptionSchedule:
    """Plan only. Caller authenticates demands and supplies only its owned current keys."""
    now = TypeAdapter(UtcTimestamp).validate_python(as_of)
    caps = FeedCapabilities.model_validate(caps.model_dump(mode='python'))
    if caps.source != 'futu':
        raise ValueError('Quota grouping is implemented only for Futu')
    if not isinstance(max_snapshot_age, timedelta) or max_snapshot_age <= timedelta(0):
        raise ValueError('A positive explicit snapshot TTL is required')
    session = MarketSession(session)
    support = {item.identity for item in supported}
    owned = {}
    owned_instruments = {}
    current_errors = []
    for value in current:
        key = SubscriptionKey.model_validate(value.model_dump(mode='python'))
        instrument = catalog.get(key.instrument_id)
        if instrument is None or not valid_us_symbol(instrument.vendor_symbols.get('futu', '')):
            current_errors.append('current_identity_unverified')
        else:
            owned_instruments[key.identity] = instrument
            if (instrument.asset_class not in caps.asset_classes
                    or (instrument.asset_class, session, key.channel_identity) not in support):
                current_errors.append('current_capability_unverified')
        owned[key.identity] = key
    groups = {}
    seen = {}
    for value in demands:
        demand = Demand.model_validate(value.model_dump(mode='python'))
        if demand.demand_id in seen and seen[demand.demand_id] != demand:
            raise ValueError('Conflicting demand ID')
        seen[demand.demand_id] = demand
        groups.setdefault(demand.key.identity, []).append(demand)
    active = {identity: [d for d in group if d.expires_at > now] for identity, group in groups.items()}
    active = {identity: group for identity, group in active.items() if group}
    reasons = {}
    eligible = {}
    for identity, group in groups.items():
        key = group[0].key
        errors = []
        instrument = catalog.get(key.instrument_id)
        if identity not in active:
            errors.append('demand_expired')
        elif instrument is None:
            errors.append('unknown_instrument')
        else:
            symbol = instrument.vendor_symbols.get('futu')
            if symbol is None:
                errors.append('vendor_symbol_missing')
            elif not symbol.startswith('US.'):
                errors.append('market_unsupported')
            elif not valid_us_symbol(symbol):
                errors.append('vendor_symbol_invalid')
            if instrument.asset_class not in caps.asset_classes:
                errors.append('asset_class_unverified')
            if (instrument.asset_class, session, key.channel_identity) not in support:
                errors.append('channel_unverified')
            if (instrument.option is not None and valid_us_symbol(symbol or '')
                    and instrument.option.expiry < now.astimezone(ZoneInfo('America/New_York')).date()):
                errors.append('instrument_expired')
        if errors:
            reasons[identity] = tuple(errors)
        else:
            eligible[identity] = instrument
    global_errors = sorted(set(current_errors))
    if caps.checked_at > now:
        global_errors.append('capability_in_future')
    elif now - caps.checked_at > max_snapshot_age:
        global_errors.append('capability_stale')
    if budget.checked_at != caps.checked_at:
        global_errors.append('quota_snapshot_mismatch')
    if caps.permission_errors:
        global_errors.append('permission_error')
    if session in (MarketSession.UNKNOWN, MarketSession.CLOSED) or session not in caps.sessions:
        global_errors.append('session_unverified')
    classes = {i.asset_class for i in (*eligible.values(), *owned_instruments.values())}
    if AssetClass.EQUITY in classes:
        if budget.equity_slots is None or caps.max_subscriptions is None:
            global_errors.append('equity_quota_unknown')
        elif budget.equity_slots > caps.max_subscriptions:
            global_errors.append('quota_snapshot_conflict')
    if AssetClass.OPTION in classes and budget.option_chain_slots is None:
        global_errors.append('option_quota_unknown')
    accepted = []
    used = {'equity': set(), 'option': set()}
    ordered = sorted(groups, key=lambda identity: (
        min((PRIORITY[d.priority] for d in active.get(identity, ())), default=len(PRIORITY)),
        _sort_key(groups[identity][0].key)))
    for identity in ordered:
        key = groups[identity][0].key
        if identity in active and global_errors:
            reasons[identity] = tuple(dict.fromkeys((*reasons.get(identity, ()), *global_errors)))
        if identity in reasons:
            continue
        instrument = eligible[identity]
        terms = instrument.option
        if terms is None:
            pool, cost_key, capacity = 'equity', key.identity, budget.equity_slots
        else:
            pool, cost_key, capacity = 'option', (terms.underlying_id, terms.expiry, key.channel_identity), budget.option_chain_slots
        if cost_key not in used[pool] and len(used[pool]) >= capacity:
            reasons[identity] = ('equity_quota_exhausted' if pool == 'equity' else 'option_quota_exhausted',)
            continue
        used[pool].add(cost_key)
        accepted.append(key)
    plan = SubscriptionPlan(schema_version='1.0', source=caps.source, as_of=now,
                            accepted=tuple(accepted), rejected=tuple(
                                SubscriptionRejection(key=groups[i][0].key, reason_codes=reasons[i])
                                for i in ordered if i in reasons))
    apply_allowed = not global_errors
    target = {key.identity: key for key in accepted}
    return SubscriptionSchedule(
        plan=plan, apply_allowed=apply_allowed, blocked_reasons=tuple(global_errors),
        subscribe=tuple(key for key in accepted if key.identity not in owned) if apply_allowed else (),
        unsubscribe=tuple(sorted((key for identity, key in owned.items() if identity not in target), key=_sort_key)) if apply_allowed else ())
