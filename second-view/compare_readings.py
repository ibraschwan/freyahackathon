"""Extract intermediate readings from recovered final SDK text, without model calls."""
import json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from builder.llm import json_of
from builder.extract import differences
evidence=json.loads((ROOT/'second-view/results/model-evidence.json').read_text())
policies=[]
for r in evidence:
    for m in r['messages']:
        for b in m['content']:
            if b['type']!='text': continue
            try: s=json_of(b['text'])
            except Exception: continue
            if not isinstance(s,dict) or 'bands' not in s or 'bank_name' not in s: continue
            policies.append({'session':r['sdk_session'],'timestamp':m['timestamp'],'bank':s['bank_name'],'spec':s,'limitations':b['text'].split('```')[0]})
policies.sort(key=lambda x:x['timestamp'])
result={'readings':policies,'adjacent_differences':[]}
for a,b in zip(policies,policies[1:]):
    if a['bank']==b['bank']:
        result['adjacent_differences'].append({'from':a['session'],'to':b['session'],'differences':differences(a['spec'],b['spec'])})
(ROOT/'second-view/results/reading-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
for p in policies:
    print(p['timestamp'],p['session'],p['bank'],'floors', {k:v.get('floor') for k,v in p['spec']['product']['types'].items()},'attempts',[x['attempts'] for x in p['spec']['bands']])
