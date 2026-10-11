"""One turn at a time, using only documented chat and practice routes.

python second-view/run_chat.py start SV1-01
python second-view/run_chat.py send SV1-01 'Yes, that is me.'
python second-view/run_chat.py end SV1-01
"""
import json, os, pathlib, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
import freya
from score import http, score_ledger

def save(path, data):
    text=json.dumps(data,indent=2,default=str)
    for k in ('FREYA_API_KEY','FREYA_BANK_TEAM_KEY','ANTHROPIC_API_KEY'):
        if os.environ.get(k): text=text.replace(os.environ[k], '[REDACTED]')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text+'\n')

def main():
    action, caseid=sys.argv[1:3]
    cases=json.loads((ROOT/'second-view/customers/live.json').read_text())
    case=next(x for x in cases if x['id']==caseid)
    path=ROOT/'second-view/results'/('chat-'+caseid+'.json')
    if action=='start':
        assert not path.exists(), 'Do not overwrite an existing measurement'
        slot='sv-one'
        ids=json.loads((ROOT/'.freya-agents.json').read_text())[slot]
        assert slot.startswith('sv-')
        v=http('/v1/practice/sessions',{'case':case['session']})['variables']
        v['now']=case['variables']['now']
        data={'case':caseid,'slot':slot,**ids,'variables':v,'turns':[], 'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z')}
        save(path,data)
        message='Hello?'
    else:
        data=json.loads(path.read_text())
        message=' '.join(sys.argv[3:])
    if action!='end':
        body={'message':message,'customerVariables':data['variables']}
        body.update({'callId':data['call_id']} if data.get('call_id') else {'workflowId':data['workflow_id']})
        start=time.monotonic()
        try:
            r=freya.api('POST','/api/v2/chat/message',body)
            data['call_id']=r.get('callId') or data.get('call_id')
            row={'user':message,'elapsed_s':round(time.monotonic()-start,3),'response':r}
            data['turns'].append(row); save(path,data)
            print(json.dumps(row,ensure_ascii=False),flush=True)
        except Exception as exc:
            row={'user':message,'elapsed_s':round(time.monotonic()-start,3),'platform_error':str(exc)}
            data['turns'].append(row); save(path,data)
            print(json.dumps(row),flush=True)
        return
    if data.get('call_id'):
        try: data['end_response']=freya.api('POST','/api/v2/chat/end',{'callId':data['call_id']})
        except Exception as exc: data['end_error']=str(exc)
        save(path,data)
        try: data['call']=freya.get_call(data['call_id'])
        except Exception as exc: data['call_read_error']=str(exc)
    data['ledger']=http('/v1/practice/ledger/'+data['variables']['customer_id'])
    data['ledger_score']=score_ledger(case,data['ledger'])
    save(path,data)
    print(json.dumps({'call_id':data.get('call_id'),'score':data['ledger_score'],'ledger':data['ledger']},ensure_ascii=False),flush=True)

if __name__=='__main__': main()
