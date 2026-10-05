"""Suggested lock-takeover acceptance checks, NOT a new project rule.
python SCRIPT PROJECT_ROOT ; exit 0 suggested cases pass, 2 known gaps, 1 unsupported.
AST-extract current _try_stale_takeover only; local TemporaryDirectory + mock liveness.
Does NOT test whole lock protocol, Windows process probe, multiprocess race or real locks.
"""
import ast,hashlib,json,os,sys,tempfile,time
from pathlib import Path

def audit(root):
 source=Path(root)/'registry_tx.py';raw=source.read_bytes();tree=ast.parse(raw.decode('utf-8-sig'))
 fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_try_stale_takeover')
 ns={'os':os,'time':time,'LOCK_STALE_S':120.0};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
 cases=[('live_old_holder',True,'holder_pid=999999\n',180,True),('live_young_holder',True,'holder_pid=999999\n',1,True),('missing_holder_old',True,'',180,True),('unknown_holder_old',None,'holder_pid=999999\n',180,True),('dead_old_holder',False,'holder_pid=999999\n',180,False)]
 results=[]
 with tempfile.TemporaryDirectory(prefix='w3_candidate_lock_') as tmp:
  p=Path(tmp)/'registry.csv.lock'
  for name,alive,content,age,expected_exists in cases:
   p.write_text(content);stamp=time.time()-age;os.utime(p,(stamp,stamp));ns['_pid_alive']=lambda pid,a=alive:a
   error=None
   try:ns['_try_stale_takeover'](str(p))
   except Exception as e:error=type(e).__name__
   actual=p.exists();results.append({'case':name,'expected_lock_retained':expected_exists,'actual_lock_retained':actual,'error':error,'passed':error is None and actual==expected_exists})
 return {'scope':'candidate proposal-level takeover checks; not overall lock safety approval','source_sha256':hashlib.sha256(raw).hexdigest(),'results':results,'all_passed':all(r['passed'] for r in results),'not_tested':['Windows PID access-denied','owner-token release','takeover TOCTOU','multiprocess persistence','crash recovery']}
if __name__=='__main__':
 try:r=audit(sys.argv[1]);print(json.dumps(r,ensure_ascii=False,indent=2));sys.exit(0 if r['all_passed'] else 2)
 except (OSError,ValueError,StopIteration,IndexError,NameError) as e:print('unsupported input: '+str(e),file=sys.stderr);sys.exit(1)
