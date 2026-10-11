"""Generate the independent nested Cedar API fixture; never contacts a server."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
def obj(p, required=None):
    return {'type':'object','properties':p,'required':list(p) if required is None else required}
def s(**kw): return dict(type='string', **kw)
def enum(*values): return s(enum=list(values))
num={'type':'number'}
integer={'type':'integer'}
status=obj({'state':enum('ACCEPTED','REJECTED'), 'message':s()}, ['state'])
facility=obj({'facility_key':s(),'kind':enum('revolving','equipment'),'overdue_total':num,'late_days':integer,'urgency_rank':integer})
requests={
 'verify_identity':{'challenge':enum('membership_word','postal_code','birth_year'),'response_text':s()},
 'get_account':{},
 'create_promise':{'facility_key':s(),'committed_sum':num,'due_on':s(format='date')},
 'add_note':{'facility_key':s(),'note_code':enum('decline','vulnerability','ownership_question','settled_claim','write_failure'),'narrative':s()},
 'schedule_callback':{'return_day':s(format='date'),'return_time':s(description='HH:MM')},
 'transfer_to_agent':{'destination':enum('desk','arrangements','care')},
 'close_call':{'resolution':enum('saved','settled','escalated','unresolved','unverified','unreachable'),'explanation':s()},
}
responses={
 'verify_identity':{'challenge_passed':{'type':'boolean'},'fully_authenticated':{'type':'boolean'},'remaining_for_challenge':integer},
 'get_account':{'facilities':{'type':'array','items':facility}},
 'create_promise':{'commitment_key':s()},
}
api={'openapi':'3.0.3','info':{'title':'Cedar nested tools','version':'1.0'},'servers':[{'url':'https://example.invalid/cedar/v3'}],'paths':{}}
for name, fields in requests.items():
    req=obj({'member_token':s(description='The call variable customer_id; identifies the synthetic session'),'request':obj(fields,[k for k in fields if k not in ('narrative','explanation')])})
    resp=obj({'result':status,'payload':obj(responses.get(name,{}))})
    api['paths']['/'+name]={'post':{'operationId':name,'summary':name+'; success ONLY when result.state equals ACCEPTED. All fields are inside request; member_token carries customer_id.','requestBody':{'required':True,'content':{'application/json':{'schema':req}}},'responses':{'200':{'description':'Envelope. REJECTED means no mutation occurred. Identity failures are per challenge.','content':{'application/json':{'schema':resp}}}}}}
(ROOT/'briefs/sv-two.openapi.json').write_text(json.dumps(api,indent=2)+'\n')
# Additional robustness probe only: contest guarantees the original seven names.
aliases=dict(zip(requests, ['authenticate_member','list_facilities','save_commitment','annotate_facility','reserve_return_call','route_to_desk','finish_contact']))
renamed=json.loads(json.dumps(api))
renamed['paths']={'/'+aliases[k.lstrip('/')]:v for k,v in renamed['paths'].items()}
for name, path in renamed['paths'].items(): path['post']['operationId']=name.lstrip('/')
(ROOT/'briefs/sv-two-renamed.openapi.json').write_text(json.dumps(renamed,indent=2)+'\n')
