"""Safe allowlisted metadata inspection of an injected quote-only context.

Call only inside a bounded SDK child process in the later real adapter. This
module neither imports futu nor opens contexts/subscriptions or trade access.
"""
from datetime import datetime,timezone

def _data(response):
    if not isinstance(response,tuple) or len(response)!=2 or type(response[0]) is not int or response[0]!=0 or not isinstance(response[1],dict):
        raise ValueError('Invalid provider response')
    return response[1]

def _counter(value):
    return value if type(value) is int and 0<=value<=9007199254740991 else None

def inspect_quote_context(context,*,checked_at:datetime)->dict:
    errors=[]
    result={'checked_at':None,'status':'metadata_incomplete','quote_logged_in':None,'total_used_quota':None,'remaining_quota':None,'errors':errors}
    try:
        if not isinstance(checked_at,datetime) or checked_at.tzinfo is None or checked_at.utcoffset() is None:
            raise ValueError('Aware diagnostic timestamp required')
        result['checked_at']=checked_at.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
        try:
            state=_data(context.get_global_state())
            login=state.get('qot_logined')
            if type(login) is bool:result['quote_logged_in']=login
            else:errors.append('quote_login_unknown')
        except Exception:errors.append('global_state_failed')
        try:
            quota=_data(context.query_subscription(is_all_conn=True))
            result['total_used_quota']=_counter(quota.get('total_used'))
            result['remaining_quota']=_counter(quota.get('remain'))
            if result['total_used_quota'] is None or result['remaining_quota'] is None:errors.append('quota_unknown')
        except Exception:errors.append('subscription_metadata_failed')
    finally:
        try:context.close()
        except Exception:errors.append('context_close_failed')
    if result['quote_logged_in'] is False:result['status']='quote_not_logged_in'
    elif result['quote_logged_in'] is True and not errors:result['status']='metadata_available'
    return result
