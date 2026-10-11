"""Recover only final assistant text and usage from this audit's SDK sessions.

Never exports thinking blocks, environment, credentials, or other workspaces.
The unchanged builder discards its own policy limitations and intermediate readings.
"""
import json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
source=pathlib.Path('/Users/ibrahim/.claude/projects/-Users-ibrahim-conductor-workspaces-freyahackathon-second-view')
rows=[]
for path in sorted(source.glob('*.jsonl')):
    row={'sdk_session':path.stem,'source_file':str(path),'messages':[]}
    for line in path.read_text().splitlines():
        d=json.loads(line); m=d.get('message') or {}
        if d.get('type')!='assistant': continue
        content=[b for b in m.get('content',[]) if b.get('type') in ('text','tool_use')]
        if not content: continue
        row['messages'].append({'id':m.get('id'),'timestamp':d.get('timestamp'),'stop_reason':m.get('stop_reason'),'model':m.get('model'),'usage':m.get('usage'),'content':content})
    if row['messages']: rows.append(row)
out=ROOT/'second-view/results/model-evidence.json'
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(rows,indent=2)+'\n')
for row in rows:
    for m in row['messages']:
        for b in m['content']:
            if b['type']=='text': print(m['timestamp'],row['sdk_session'],b['text'].split('```')[0][:1600])
            else: print(m['timestamp'],'tool attempt:',b.get('name'))
