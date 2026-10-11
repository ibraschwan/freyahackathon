"""Compact, indexed evidence from fetched provider transcripts and bank ledgers."""
import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
rows=[]
for p in sorted((ROOT/'second-view/results').glob('chat-SV1-*.json')):
    d=json.loads(p.read_text())
    row={'case':d['case'],'call_id':d.get('call_id'),'ledger_score':d.get('ledger_score'),
         'transport_errors':[t for t in d['turns'] if t.get('platform_error')],
         'speech':[],'events':[],'ledger':d.get('ledger'), 'fetched_call_status':d.get('call',{}).get('status')}
    for index,m in enumerate(d.get('call',{}).get('messages',[])):
        if m.get('role') in ('user','assistant'):
            row['speech'].append({'message_index':index,'role':m['role'],'text':m.get('message'),'timestamp':m.get('timestamp'),'seconds':m.get('secondsFromStart')})
        elif m.get('role')=='system':
            try: event=json.loads(m.get('message',''))
            except Exception: continue
            if event.get('event') in ('function_call_start','function_call_complete','function_call_error','call_ended','turn_completed'):
                if event.get('function')=='code_exec': continue
                event=json.loads(json.dumps(event))
                if isinstance(event.get('args'),dict):
                    event['args'].pop('code',None)
                    event['args'].pop('headers',None)
                row['events'].append({'message_index':index,'timestamp':m.get('timestamp'),'node':m.get('nodeId'),**event})
    row['bank_close_count']=sum(c['tool']=='close_call' for c in (d.get('ledger') or {}).get('calls',[]))
    rows.append(row)
(ROOT/'second-view/results/chat-summary.json').write_text(json.dumps(rows,indent=2)+'\n')
for row in rows: print(row['case'],row['call_id'],'ledger',row['ledger_score'],'close count',row['bank_close_count'],'504s',len(row['transport_errors']))
