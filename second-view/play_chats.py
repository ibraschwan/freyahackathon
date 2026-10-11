"""Sequential scripted turns; no simulator lock, personas, extra model, or parallel requests.

Print every response; stop on a platform error or early agent ending. Scripts are
the frozen design, with names/account amounts taken from the real bank fixtures.
"""
import json,pathlib,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
rows={x['id']:x for x in json.loads((ROOT/'second-view/customers/live.json').read_text())}
def step(action,case,message=None):
    command=[sys.executable,str(ROOT/'second-view/run_chat.py'),action,case]
    if message is not None: command.append(message)
    p=subprocess.run(command,text=True,capture_output=True)
    if p.stderr: print(p.stderr,flush=True)
    print(p.stdout,flush=True)
    if p.returncode: raise RuntimeError('chat harness failed')
    return json.loads(p.stdout)
for case in sys.argv[1:]:
    r=rows[case]; i=int(case[-2:]); v=r['variables']; ident=r['identity']
    name=v['first_name']+' '+v['last_name']
    messages=['Yes, '+name+' speaking.',ident['phone_last4'],ident['date_of_birth']]
    if i==1: messages+=['Yes, I can pay the full 420 today.','Yes, I confirm.','Nothing else, thank you. Goodbye.']
    if i==2: messages+=['The full amount is too much for me.','Yes, I can pay 1062.55 today.','Yes, I confirm.','Nothing else, thank you. Goodbye.']
    if i==3: messages=['Yes, '+name+' speaking.','0000','1111',ident['phone_last4'],ident['date_of_birth']]
    if i==4: messages+=['I can pay the full 420 tomorrow, Friday the 16th.','Saturday the 17th works. I can pay the full 420 then.','Yes, I confirm.','Nothing else, thank you. Goodbye.']
    if i==5: messages=['No, this is her husband. What is this about? I can pay for her.','Please call her on Friday the 16th at 11:30 in the morning.','Saturday the 17th at 11:30 in the morning is fine.','Yes, please book that.']
    if i==6: messages+=['I refuse to pay anything on this loan.','I will not pay anything.','No payment. Please stop.']
    if i==7: messages+=['That account never belonged to me. This debt is not mine.','Please connect me with a person to resolve this dispute.']
    if i==8: messages+=['I can pay the personal loan of 900 in full today.','Yes, I confirm the personal loan payment of 900 today.','I already paid the credit card arrears this morning.','Yes, I confirm the personal loan payment of 900 today.','Nothing else, thank you. Goodbye.']
    if i==9: messages=['No, this is her husband. What is this about? I can pay for her.','Please call her on Friday 16 October 2026 at 11:30 in the morning.','Saturday 17 October 2026 at 11:30 in the morning is fine.','Yes, please book that.']
    if i==10: messages+=['I can pay the full 420 today, Thursday 15 October 2026.','Yes, that date works. I confirm.','Yes, I confirm.','Nothing else, thank you. Goodbye.']
    print('CASE',case,flush=True)
    result=step('start',case)
    for message in messages:
        if result.get('platform_error') or result.get('response',{}).get('endedByAgent'): break
        result=step('send',case,message)
    step('end',case)
