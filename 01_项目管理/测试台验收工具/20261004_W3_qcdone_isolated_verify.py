"""Isolated AST qc_done payload/append contract verification; no service imports.
Run python SCRIPT PROJECT_ROOT. TemporaryDirectory only; no shared results overwrite.
This does not exercise Monitor/Experiment lifecycle, qc calculation or devices.
"""
import ast
import json
import os
import hashlib
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

root=Path(sys.argv[1]); server=root/'console_server.py'; sc=root/'session_contract.py'
tree=ast.parse(server.read_text(encoding='utf-8-sig'))
calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='append_event' and len(n.args)>1 and isinstance(n.args[1],ast.Constant) and n.args[1].value=='qc_done']
assert len(calls)==2
contract=ast.parse(sc.read_text(encoding='utf-8-sig'))
selected=[n for n in contract.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in {'_now','make_event','append_event'}]
assert len(selected)==3
ns={'json':json,'os':os,'datetime':datetime,'CONTRACT_VERSION':'1.0'}
exec(compile(ast.Module(body=selected,type_ignores=[]),str(sc),'exec'),ns)
version_tree=ast.parse((root/'qc_pipeline.py').read_text(encoding='utf-8-sig'))
constants={n.targets[0].id:ast.literal_eval(n.value) for n in version_tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in {'THRESHOLD_VERSION','QC_VERSION'}}
checks=[]
def ok(name,detail):checks.append({'name':name,'passed':True,'detail':detail})
with tempfile.TemporaryDirectory(prefix='w3_qcdone_') as tmp:
 missing=Path(tmp)/'absent.jsonl'
 assert ns['append_event'](str(missing),'qc_done','system','derived',{}) is False and not missing.exists()
 ok('absent_event_file_skip','real append_event extracted from AST; no event file created')
 for c in sorted(calls,key=lambda x:x.lineno):
  expr=ast.Expression(c.args[4]);env={'qc_pipeline':SimpleNamespace(**constants)}
  for label,qc in [('quarantine',{'recommend':'quarantine','metrics':{'clean_ratio':0.25,'packet_loss_rate':0.3},'reasons':['synthetic failure']}),('keep',{'recommend':'keep','metrics':{'clean_ratio':0.99,'packet_loss_rate':0},'reasons':[]}),('missing_metrics_reasons',{'recommend':'quarantine'})]:
   payload=eval(compile(expr,str(server),'eval'),dict(env,qc=qc))
   assert payload['threshold_version']==constants['THRESHOLD_VERSION'] and payload['qc_version']==constants['QC_VERSION']
   assert payload['reasons']==(qc.get('reasons') or [])
   assert payload['recommend']==qc['recommend']
   ev=Path(tmp)/f'{c.lineno}_{label}.jsonl';ev.touch()
   assert ns['append_event'](str(ev),'qc_done','system','derived',payload)
   data=json.loads(ev.read_text());assert data['payload']==payload and data['type']=='qc_done'
   ok(f'payload_line_{c.lineno}_{label}','actual AST payload expression + actual append_event; synthetic qc only')
 # Isolate failure by injecting open, never change a production path or real permissions.
 original=ns.get('open');ns['open']=lambda *a,**k:(_ for _ in ()).throw(PermissionError('synthetic denied'))
 existing=Path(tmp)/'denied.jsonl';existing.touch()
 try:ns['append_event'](str(existing),'qc_done','system','derived',{})
 except PermissionError:ok('append_write_failure_propagates','caller silent except policy NOT behavior-tested')
 else:raise AssertionError('failure swallowed by append_event')
 if original is None:del ns['open']
 else:ns['open']=original
print(json.dumps({'scope':'isolated payload serialization, not full lifecycle/QC calculation','checks':checks,'thresholds':constants,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [server,sc,root/'qc_pipeline.py']}},ensure_ascii=False,indent=2))
