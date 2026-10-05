"""AST-extracted lock takeover counterexamples; synthetic TemporaryDirectory only.
No production imports, real registry reads, process termination or service calls.
Run python SCRIPT PROJECT_ROOT. Expected vulnerability observations != real incident.
"""
import ast,os,time,tempfile,json,sys,hashlib
from pathlib import Path
root=Path(sys.argv[1]);source=root/'registry_tx.py';raw=source.read_bytes();tree=ast.parse(raw.decode('utf-8-sig'))
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_try_stale_takeover')
ns={'os':os,'time':time,'LOCK_STALE_S':120.0,'_pid_alive':lambda pid:True};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
checks=[]
with tempfile.TemporaryDirectory(prefix='w3_lock_synthetic_') as temp:
 p=Path(temp)/'registry.csv.lock'
 p.write_text('holder_pid=999999\n');old=time.time()-180;os.utime(p,(old,old));ns['_try_stale_takeover'](str(p));assert not p.exists()
 checks.append({'name':'live_holder_age_alone_removes_lock','observed':True,'meaning':'mock holder alive; old lock removed by actual predicate'})
 p.write_text('holder_pid=999999\n');ns['_pid_alive']=lambda pid:False;ns['_try_stale_takeover'](str(p));assert not p.exists()
 checks.append({'name':'fresh_dead_holder_removes_lock','observed':True,'meaning':'dead PID alone sufficient without stale-age condition'})
 p.write_text('');os.utime(p,(old,old));ns['_pid_alive']=lambda pid:True;ns['_try_stale_takeover'](str(p));assert not p.exists()
 checks.append({'name':'missing_holder_old_lock_removed','observed':True,'meaning':'old incomplete lock has no verified owner but removed'})
 p.write_text('holder_pid=999999\n');ns['_try_stale_takeover'](str(p));assert p.exists()
 checks.append({'name':'fresh_live_holder_retained','observed':True,'meaning':'control case, young live lock retained'})
print(json.dumps({'scope':'synthetic counterexample, not actual holder death/live proof','checks':checks,'source_sha256':hashlib.sha256(raw).hexdigest()},ensure_ascii=False,indent=2))
