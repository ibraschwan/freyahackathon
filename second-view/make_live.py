"""Bind frozen behavioral scenarios to public bank fixtures; no builder inputs are changed."""
import json,pathlib,copy
ROOT=pathlib.Path(__file__).resolve().parents[1]
pub={x['id']:x for x in json.loads((ROOT/'public-test-set.json').read_text())}
mapping=['PUB-01','PUB-06','PUB-03','PUB-01','PUB-02','PUB-05','PUB-08','PUB-13']
rows=[]
for i,source in enumerate(mapping,1):
    p=pub[source]
    r={'id':f'SV1-{i:02}','session':source,'variables':p['variables'],'identity':p['identity'],'products':p['products'],
       'expected':{'outcome':'promise','reason':None,'promises':[],'notes':[],'callbacks':[],'transfers':[]}}
    r=copy.deepcopy(r); e=r['expected']
    if i in (1,2,4):
        e['promises']=[{'product_id':'p1','amount':1062.55 if i==2 else 420.0,'date':'2026-10-17' if i==4 else '2026-10-14'}]
    if i==3: e.update(outcome='not_verified',reason='failed')
    if i==4: r['variables']['now']='2026-10-15T15:00'
    if i==5: e.update(outcome='not_reached',reason='callback',callbacks=[{'date':'2026-10-17','time':'11:30'}])
    if i==6: e.update(outcome='no_promise',reason='refused',notes=[{'product_id':'p1','reason':'refused'}])
    if i==7: e.update(outcome='transferred',reason='human',notes=[{'product_id':'p1','reason':'dispute'}],transfers=[{'queue':'general'}])
    if i==8: e.update(promises=[{'product_id':'p2','amount':900.,'date':'2026-10-14'}],notes=[{'product_id':'p1','reason':'paid'}])
    rows.append(r)
(ROOT/'second-view/customers/live.json').write_text(json.dumps(rows,indent=2)+'\n')
