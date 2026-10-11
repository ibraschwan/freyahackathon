"""Deterministic probes of the UNCHANGED engine, using the actual generated spec.

These are mechanism tests, not conversations or estimates of hidden pass rates.
"""
import copy, json, pathlib, sys, traceback
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from local_sim import Sim, Rule
from builder import engine, extract

def main():
    slot=sys.argv[1] if len(sys.argv)>1 else 'sv-one'
    spec=json.loads((ROOT/'out'/f'{slot}.spec.json').read_text())
    ident={'phone_last4':'7319','date_of_birth':'1985-04-23'}
    p={'product_id':'p1','type':'credit_card','card_last4':'9012','past_due':401.01,'minimum_payment':80.,'days_late':8}
    def sim(products=None, now='2026-10-14T11:00',login=True,**kw):
        s=Sim(spec,copy.deepcopy(products or [p]),now,identity=ident,**kw)
        return s.login() if login else s
    results=[]
    def probe(name,expected,run):
        try: actual=run()
        except Exception as exc: actual={'exception':str(exc),'type':type(exc).__name__}
        results.append({'probe':name,'expected':expected,'actual':actual})
    def snap(s): return {'state':s.state,'said':s.said,'ledger':s.ledger,'ended':s.ended}
    def wrong():
        s=sim(login=False); s.verify('phone_last4','0000'); s.verify('phone_last4','1111'); return snap(s)
    probe('O3 wrong answer cutoff','After exactly two wrong answers: ended, not_verified/failed, no DOB',wrong)
    probe('O8 max and half-cent rounding',{'floor':200.51},lambda:sim().state['products'][0])
    probe('O8 max selects larger service floor',{'floor':300.},lambda:sim([dict(p,minimum_payment=300.)]).state['products'][0])
    def terms(date,now,amount='full'):
        s=sim(now=now)
        try: s.tool('set_promise',product_id='p1',amount=amount,date=date); response='ACCEPTED'
        except Rule as exc: response=str(exc)
        return {'response':response,**snap(s)}
    probe('O4 cutoff today','Reject 2026-10-15 at 15:00; offer 2026-10-17',lambda:terms('2026-10-15','2026-10-15T15:00'))
    probe('O4 preceding holiday adjustment','Offer 2026-10-15 for holiday 2026-10-16',lambda:terms('2026-10-16','2026-10-14T11:00'))
    probe('O4 Saturday is working','ACCEPTED',lambda:terms('2026-10-17','2026-10-14T11:00'))
    probe('O8 reject half-cent under floor','Reject 200.50, floor 200.51',lambda:terms('2026-10-14','2026-10-14T11:00',200.50))
    def refused():
        s=sim([dict(p,days_late=22)]); s.tool('refusal',product_id='p1',kind='flat_refusal'); return snap(s)
    probe('O7 zero extra offers','Immediately note p1 refused and close no_promise/refused',refused)
    def declined():
        s=sim(login=False); s.tool('no_answer',about='security_question'); return snap(s)
    probe('O3 first security refusal','Immediately close not_verified/declined',declined)
    def cb():
        s=sim(login=False); s.callback('2026-10-17','11:30'); return snap(s)
    probe('O5 callback next two working days','Callback 2026-10-17 11:30, not_reached/callback',cb)
    ps=[dict(p,days_late=4),{'product_id':'p2','type':'personal_loan','past_due':600.,'instalment_amount':100.,'days_late':22}]
    probe('O6 product sort','p2 then p1',lambda:sim(ps).state['products'])
    def perproduct():
        s=sim(ps); s.tool('set_promise',product_id='p2',amount='full',date='2026-10-14'); return snap(s)
    probe('O6 individual readback before next product','Read back p2 600 today and await assent, without an offer for p1',perproduct)
    def transfer():
        s=sim(ps); s.tool('set_note',product_id='p1',reason='dispute'); s.transfer('general'); return snap(s)
    probe('O12/O15 notes survive transfer','p1 dispute note and p2 refused note, transfer general, transferred/human',transfer)
    def singleton_dispute():
        s=sim(); s.tool('set_note',product_id='p1',reason='dispute')
        if not s.ended: s.transfer('general')
        return snap(s)
    probe('O12 singleton dispute must transfer','note dispute, transfer general, transferred/human',singleton_dispute)
    def stalls():
        s=sim([dict(p,days_late=22)]); s.stall(); s.stall(); return snap(s)
    probe('O9 non-answer not refusal','Two stall events must not consume a refusal budget or close as refused',stalls)
    def note_failure():
        s=sim([dict(p,days_late=22)],fail_first={'add_note':2}); s.tool('refusal',product_id='p1',kind='flat_refusal'); return snap(s)
    probe('O14 note write failure','After two failed notes, close no_promise/service_error',note_failure)
    for result in results: print(result['probe'],json.dumps(result['actual'])[:300])
    out=ROOT/'second-view/results'/f'local-{slot}.json'; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({'spec':f'out/{slot}.spec.json','builder_commit':'de4f07e','results':results},indent=2)+'\n')

if __name__=='__main__': main()
