"""Add two diagnostic controls after the independent eight cases, without changing them."""
import json,pathlib,copy
root=pathlib.Path(__file__).resolve().parent
p=root/'customers/live.json';rows=json.loads(p.read_text())
for source,target in [('SV1-05','SV1-09'),('SV1-04','SV1-10')]:
    if any(r['id']==target for r in rows): continue
    r=copy.deepcopy(next(r for r in rows if r['id']==source)); r['id']=target; r['diagnostic_control_of']=source
    rows.append(r)
p.write_text(json.dumps(rows,indent=2)+'\n')
