"""Synthetic-only deterministic registry interleaving counterexamples.
AST-extract actual console read/write/number helpers; ingest full rewrite block.
Never import production modules, run main(), read real registry or write project data.
python SCRIPT PROJECT_ROOT ; stdout JSON, expected vulnerability reproduced != real corruption.
"""
import ast,csv,json,os,sys,tempfile,hashlib
from pathlib import Path
root=Path(sys.argv[1]);console=root/'console_server.py';ingest=root/'05_产品与开发/muse-direct/tools/ingest_session.py'
a=ast.parse(console.read_text(encoding='utf-8-sig'));b=ast.parse(ingest.read_text(encoding='utf-8-sig'))
funcs=[n for n in a.body if isinstance(n,ast.FunctionDef) and n.name in {'_read_registry_rows','_write_registry_rows','_next_session_number'}];assert len(funcs)==3
blocks=[n for n in ast.walk(b) if isinstance(n,ast.With) and any(isinstance(x.context_expr,ast.Call) and isinstance(x.context_expr.func,ast.Name) and x.context_expr.func.id=='open' and len(x.context_expr.args)>1 and isinstance(x.context_expr.args[0],ast.Name) and x.context_expr.args[0].id=='REGISTRY' and isinstance(x.context_expr.args[1],ast.Constant) and x.context_expr.args[1].value=='w' for x in n.items)]
assert len(blocks)==1
cols=['session_id','participant_id','date','session_type','duration_seconds','status','manifest_path']
checks=[]
def record(name,predicate,detail):
 assert predicate,name;checks.append({'name':name,'expected_counterexample_observed':True,'detail':detail})
with tempfile.TemporaryDirectory(prefix='w3_synthetic_registry_') as tmp:
 registry=Path(tmp)/'registry.csv';ns={'csv':csv,'os':os,'REGISTRY_CSV':str(registry)};exec(compile(ast.Module(body=funcs,type_ignores=[]),str(console),'exec'),ns)
 def seed():
  row={'session_id':'ZEN-20990101-P999-S01','participant_id':'P999','date':'2099-01-01','session_type':'test','duration_seconds':'','status':'planned','manifest_path':''};ns['_write_registry_rows']([row])
 def ingest_write(rows):exec(compile(ast.Module(body=blocks,type_ignores=[]),str(ingest),'exec'),{'REGISTRY':registry,'csv':csv,'fieldnames':cols,'rows':rows})
 def prereg_add(rows):
  number=ns['_next_session_number'](rows,'P999');sid='ZEN-20990101-P999-'+number;rows.append({'session_id':sid,'participant_id':'P999','date':'2099-01-01','session_type':'test','duration_seconds':'','status':'planned','manifest_path':''});return sid
 seed();left=ns['_read_registry_rows']();right=ns['_read_registry_rows']();sid=prereg_add(left);ns['_write_registry_rows'](left);right[0]['status']='finished';ingest_write(right);after=ns['_read_registry_rows']()
 record('preregister_then_stale_ingest_loses_new_row',sid not in [r['session_id'] for r in after],'two stale snapshots; exact ingest writer rewrites old rows')
 seed();left=ns['_read_registry_rows']();right=ns['_read_registry_rows']();right[0]['status']='finished';ingest_write(right);prereg_add(left);ns['_write_registry_rows'](left);after=ns['_read_registry_rows']()
 record('ingest_then_stale_preregister_reverts_status',after[0]['status']=='planned','finished backfill reverted by stale console rewrite')
 seed();left=ns['_read_registry_rows']();right=ns['_read_registry_rows']();s1=prereg_add(left);s2=prereg_add(right);ns['_write_registry_rows'](left);ns['_write_registry_rows'](right)
 record('two_prereg_snapshots_allocate_same_id',s1==s2,'both callers can derive S02 before either sees the other write; no runtime request scheduler tested')
 seed();snapshot=ns['_read_registry_rows']();before=registry.read_bytes()
 class CrashWriter:
  def __init__(self,*a,**kw):pass
  def writeheader(self):raise OSError('synthetic failure after open-w truncation')
  def writerows(self,rows):raise AssertionError('must not reach')
 original=ns['csv'];ns['csv']=type('InjectedCSV',(),{'DictWriter':CrashWriter})
 try:ns['_write_registry_rows'](snapshot)
 except OSError:pass
 else:raise AssertionError('failure not raised')
 ns['csv']=original
 record('rewrite_failure_can_leave_truncated_csv',len(registry.read_bytes())==0 and len(before)>0,'controlled injected writeheader error; source open(w) has already truncated synthetic file')
 # This restoration is only from a retained test fixture, not automatic production recovery.
 ns['_write_registry_rows'](snapshot);record('retained_fixture_can_restore_synthetic_rows',ns['_read_registry_rows']()==snapshot,'test manually restores retained snapshot; no production backup/transaction guarantee')
print(json.dumps({'scope':'deterministic synthetic interleavings, NOT evidence real data was lost; NOT end-to-end concurrent HTTP','checks':checks,'source_hash':{p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in [console,ingest]}},ensure_ascii=False,indent=2))
