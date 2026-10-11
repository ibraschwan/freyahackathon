"""Check only this audit's artifacts and trace outputs; never print matched secret values."""
import json,os,pathlib,re,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
paths=list((ROOT/'second-view').rglob('*'))+list((ROOT/'out').glob('sv-*'))+list((ROOT/'traces').glob('sv-*.log'))
bad=[]; checked=[]
prefixes=['fa'+'k_','for'+'ge-']
for p in paths:
    if not p.is_file() or p.suffix=='.pyc': continue
    text=p.read_text(errors='replace'); checked.append(str(p.relative_to(ROOT)))
    if any(re.search(re.escape(x)+r'[A-Za-z0-9]{8,}',text) for x in prefixes): bad.append({'path':str(p.relative_to(ROOT)),'reason':'credential prefix match'})
    for name in ('FREYA_API_KEY','FREYA_BANK_TEAM_KEY','ANTHROPIC_API_KEY'):
        if os.environ.get(name) and os.environ[name] in text: bad.append({'path':str(p.relative_to(ROOT)),'reason':name+' actual value match'})
delta=subprocess.check_output(['git','diff','de4f07e','--','builder/'],cwd=ROOT,text=True)
result={'checked_files':checked,'secret_matches':bad,'builder_unchanged_from_de4f07e':not delta,'submission_files_will_not_be_staged':True}
out=ROOT/'second-view/results/artifact-check.json';out.write_text(json.dumps(result,indent=2)+'\n')
print('checked',len(checked),'files; secret matches',len(bad),'builder unchanged',not delta)
if bad: raise SystemExit(1)
