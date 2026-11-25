"""Deterministic capability ceilings; principals must originate from trusted stores."""
from gabfin.contracts.identity import Capability as C,Role,Principal,Resource
CHAT={C.READ_ACCOUNT,C.RESOLVE_SYMBOLS,C.START_RESEARCH,C.READ_REPORT,C.DRAFT_TRADE_PLAN}
CEILINGS={Role.CHAT:CHAT,Role.RESEARCH:CHAT|{C.READ_MARKET,C.PROPOSE_STRATEGY},Role.STRATEGY:{C.READ_MARKET,C.READ_ACCOUNT,C.EMIT_STRATEGY_INTENT},Role.EXECUTOR:{C.READ_MARKET,C.READ_ACCOUNT,C.SUBMIT_ORDER,C.CANCEL_ORDER},Role.OWNER:set(C)-{C.SUBMIT_ORDER,C.EMIT_STRATEGY_INTENT}}
KINDS={C.READ_ACCOUNT:'account',C.RESOLVE_SYMBOLS:'instrument',C.START_RESEARCH:'research_job',C.READ_REPORT:'research_report',C.DRAFT_TRADE_PLAN:'instrument',C.READ_MARKET:'instrument',C.MANAGE_WATCHLIST:'watchlist',C.PROPOSE_STRATEGY:'proposal',C.EMIT_STRATEGY_INTENT:'strategy',C.SUBMIT_ORDER:'order',C.CANCEL_ORDER:'order',C.START_WORKER:'strategy',C.PAUSE_WORKER:'strategy',C.RESUME_WORKER:'strategy',C.WRITE_POLICY:'policy',C.APPROVE_PROPOSAL:'proposal'}
def authorize(principal:Principal,capability:C,resource:Resource)->None:
    if capability not in CEILINGS[principal.role] or capability not in principal.scope or resource.owner!=principal.actor_id or resource.kind.value!=KINDS[capability]:
        raise PermissionError('Forbidden')
