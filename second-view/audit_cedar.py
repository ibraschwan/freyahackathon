"""Compare kit fake-bank response assumptions against Cedar's actual API envelope.

If no final spec exists, use the latest saved model-produced Cedar configuration,
clearly labelling it as intermediate; never fabricate a successful build.
"""
import json,pathlib,sys,copy
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from local_sim import Sim
from builder import engine,extract

def nested_set(out,path,value):
    parts=path.split('.')
    for p in parts[:-1]: out=out.setdefault(p,{})
    out[parts[-1]]=value

class NativeResponseSim(Sim):
    """Keep Sim's bank behavior but return REAL nested response shape, not dotted keys."""
    def _bank(self, tool, body):
        status,data=super()._bank(tool,body)
        native={}
        for k,v in data.items(): nested_set(native,k,v)
        native.setdefault('result',{})['state']='ACCEPTED' if status==200 and not data.get('error') else 'REJECTED'
        self.ledger['calls'][-1]['native_response']=copy.deepcopy(native)
        return status,native

def main():
    slot=sys.argv[1] if len(sys.argv)>1 else 'sv-two'
    final=ROOT/'out'/f'{slot}.spec.json'
    if final.exists(): spec=json.loads(final.read_text()); source=str(final.relative_to(ROOT)); intermediate=False
    else:
        readings=json.loads((ROOT/'second-view/results/reading-comparison.json').read_text())['readings']
        p=[x for x in readings if 'Cedar' in x['bank']][-1]
        spec=p['spec']; source='recovered SDK session '+p['session']; intermediate=True
    api=json.loads((ROOT/'second-view/briefs/sv-two.openapi.json').read_text())
    ident={'membership_word':'maple','postal_code':'K2A7','birth_year':'1981'}
    products=[{'facility_key':'f1','kind':'revolving','overdue_total':300.01,'late_days':12,'urgency_rank':2}]
    results={}
    for cls in (Sim,NativeResponseSim):
        s=cls(spec,products,'2026-10-14T11:00',identity=ident)
        errors=[]
        for f,a in ident.items():
            try: s.verify(f,a)
            except Exception as exc: errors.append(str(exc))
        results[cls.__name__]={'errors':errors,'state':s.state,'ledger':s.ledger,'said':s.said}
    read=engine.read_api(api)
    t=engine.bank_tool(read,'verify_identity',spec['call_variables'],'test')
    body=t['function']['parameters']['properties']['body']
    out={'source':source,'intermediate_not_completed_build':intermediate,
         'check_errors':extract.check(spec,api),'compiled_identity_body_schema':body,
         'contract_identity_body_schema':api['paths']['/verify_identity']['post']['requestBody']['content']['application/json']['schema'],
         'results':results}
    path=ROOT/'second-view/results'/f'cedar-api-{slot}.json'; path.write_text(json.dumps(out,indent=2)+'\n')
    print('source',source,'intermediate',intermediate)
    for k,v in results.items(): print(k,'stage',v['state']['stage'],'products',len(v['state']['products']),'errors',v['errors'])
    print('compiled request type',body['properties']['request']['type'],'required member token baked?',body['properties']['member_token'])

if __name__=='__main__': main()
