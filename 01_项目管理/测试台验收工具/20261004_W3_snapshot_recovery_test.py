"""隔离合成验证快照排定与可恢复文件的区别。AST提取真实方法，不导入服务。
真实写入仅TemporaryDirectory，不读真人数据，不物理断电，不改工程。
"""
import ast, hashlib, json, os, sys, tempfile, threading, time
from pathlib import Path
from datetime import datetime
import numpy as np
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[2]
source=ROOT/'muse2-repo/muse2-master/muse_local_server.py'
tree=ast.parse(source.read_text(encoding='utf-8-sig')); cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DataBuffer')
methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ['snapshot','_snapshot_write']]
ns=dict(np=np,os=os,time=time,datetime=datetime,threading=threading)
exec(compile(ast.Module(body=methods,type_ignores=[]),str(source),'exec'),ns)
class Buffer:
 snapshot=ns['snapshot']; _snapshot_write=ns['_snapshot_write']
 def __init__(self,d):
  self.lock=threading.Lock();self.channels=['synthetic'];self.n_ch=1;self.sfreq=10;self.device='synthetic';self.eeg_all={'synthetic':[1.,2.,3.]};self.has_raw=False;self.timestamps=[100.,100.1,100.2];self.session_start=100.;self.snapshot_dir=d;self.snapshot_interval_s=0;self._saved_data_path=None;self._last_snapshot_t=0;self._snap_thread=None;self._last_snapshot_path=None;self._snapshot_count=0;self._snap_lock_max_ms=0;self._snap_write_max_ms=0
class FailNP:
 def __getattr__(self,n):return getattr(np,n)
 def savez(self,*a,**k):raise OSError('synthetic injected save failure')
results=[]
with tempfile.TemporaryDirectory(prefix='zg_w3_recovery_') as d:
 b=Buffer(d);entered,release=threading.Event(),threading.Event();writer=b._snapshot_write
 def delayed(*a):
  entered.set();assert release.wait(5);writer(*a)
 b._snapshot_write=delayed;p=b.snapshot(force=True)
 try:
  assert entered.wait(5);assert p and not Path(p).exists();assert b.snapshot(force=True) is None
  results.append('首次返回路径但文件尚不存在；后续轮跳过')
 finally:release.set();b._snap_thread.join(5)
 assert not b._snap_thread.is_alive() and Path(p).is_file()
 # 第二轮失败保留旧成功快照；不据此证明断电耐久性。
 before=hashlib.sha256(Path(p).read_bytes()).hexdigest();ns['np']=FailNP();b._snapshot_write=writer
 try:
  b.eeg_all['synthetic'].append(999.);b.timestamps.append(100.3);p2=b.snapshot(force=True);b._snap_thread.join(5)
  assert not b._snap_thread.is_alive() and p2==p and b._snapshot_count==1
  assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==before
  results.append('后续写失败仍返回排定路径，最近成功文件保持旧截点')
 finally:ns['np']=np
with tempfile.TemporaryDirectory(prefix='zg_w3_first_fail_') as d:
 b=Buffer(d);ns['np']=FailNP()
 try:
  p=b.snapshot(force=True);b._snap_thread.join(5);assert p and not Path(p).exists() and b._snapshot_count==0
  results.append('首次写失败：路径返回但无成功快照')
 finally:ns['np']=np
 p=b.snapshot(force=True);b._snap_thread.join(5);assert Path(p).is_file() and b._snapshot_count==1
 results.append('注入撤销后顺序重试成功')
print(json.dumps(dict(passed=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),checks=results,limits=['不是物理断电或Windows真机验证','未解释原采集停顿根因','不强求测试输出hash一致']),ensure_ascii=False,indent=2))
