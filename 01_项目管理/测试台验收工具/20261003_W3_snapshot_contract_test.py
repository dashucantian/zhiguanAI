"""W3独立合成快照契约测试。仅AST提取方法，不导入服务、不读真人数据。
所有快照写入TemporaryDirectory；不触碰项目output、不启动服务。
用法：python 本文件 [项目根目录]；默认从文件位置推导。
"""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from datetime import datetime
from types import SimpleNamespace
import numpy as np

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'muse2-repo/muse2-master/muse_local_server.py'
text = SOURCE.read_text(encoding='utf-8-sig')
tree = ast.parse(text)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DataBuffer')
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {'snapshot', '_snapshot_write', 'discard_snapshot'}]
ns = dict(np=np, os=os, time=time, datetime=datetime, threading=threading)
exec(compile(ast.Module(body=methods, type_ignores=[]), str(SOURCE), 'exec'), ns)

class Buffer:
    snapshot = ns['snapshot']
    _snapshot_write = ns['_snapshot_write']
    discard_snapshot = ns['discard_snapshot']
    def __init__(self, directory):
        self.lock = threading.Lock()
        self.channels = ['synthetic_A', 'synthetic_B']
        self.n_ch = 2
        self.sfreq = 10.0
        self.device = 'synthetic_test_not_human'
        self.eeg_all = {c: [1.0, 2.0, 3.0] for c in self.channels}
        self.has_raw = False
        self.timestamps = [100.0, 100.1, 100.2]
        self.session_start = 100.0
        self.snapshot_dir = directory
        self.snapshot_interval_s = 0
        self._saved_data_path = None
        self._last_snapshot_t = 0
        self._snap_thread = None
        self._last_snapshot_path = None
        self._snapshot_count = 0
        self._snap_lock_max_ms = 0
        self._snap_write_max_ms = 0

results = []
def record(name, passed, detail):
    results.append(dict(test=name, passed=bool(passed), detail=detail))

with tempfile.TemporaryDirectory(prefix='zg_w3_synthetic_') as tmp:
    b = Buffer(tmp)
    path = b.snapshot(force=True)
    b._snap_thread.join(5)
    with np.load(path, allow_pickle=True) as z:
        ok = z['eeg'].shape == (3, 2) and z['meta'].item()['snapshot'] is True
    record('background_atomic_file', ok and b._snapshot_count == 1, '真实方法写入合成数据；后台完成后文件可读')

    class SlowThread:
        def is_alive(self): return True
        def join(self, timeout=None): self.timeout = timeout
    b._snap_thread = SlowThread()
    ok = b.discard_snapshot() is False and Path(path).exists()
    record('timeout_preserves_file', ok, '模拟join超时，不等30秒；应返回False且保留文件')
    b._snap_thread = None
    record('completed_discard', b.discard_snapshot() is True and not Path(path).exists(), '已完成写线程的快照可删')

    # 保证后台尚未完成，验证第二次调度被跳过及首次数据截点不被后来追加污染。
    b = Buffer(tmp)
    enter, release = threading.Event(), threading.Event()
    writer = b._snapshot_write
    def delayed(*args):
        enter.set()
        assert release.wait(5)
        return writer(*args)
    b._snapshot_write = delayed
    path = b.snapshot(force=True)
    assert enter.wait(5)
    for c in b.channels: b.eeg_all[c].append(999.0)
    second = b.snapshot(force=True)
    release.set()
    b._snap_thread.join(5)
    with np.load(path, allow_pickle=True) as z: values = z['eeg'].copy()
    record('single_caller_skip_and_capture', second is None and values.shape == (3, 2) and not (values == 999.0).any(), '首次快照不应含排定之后追加值；第二次调用跳过')

    # 调度器替身让两调用都检查到尚未存活的线程；只测重入守卫，不写文件。
    barrier = threading.Barrier(2)
    starts = []
    class FakeThread:
        def __init__(self, **kwargs): pass
        def is_alive(self): return False
        def start(self):
            starts.append(1)
            barrier.wait(timeout=5)
    real_threading = ns['threading']
    ns['threading'] = SimpleNamespace(Thread=FakeThread)
    b = Buffer(tmp)
    errors = []
    def call():
        try: b.snapshot(force=True)
        except Exception as e: errors.append(str(e))
    a, c = threading.Thread(target=call), threading.Thread(target=call)
    a.start(); c.start(); a.join(6); c.join(6)
    ns['threading'] = real_threading
    record('concurrent_guard_counterexample', len(starts) == 2 and not errors, '条件性反例：两个调用者可排定两次；不证明当前生产单调用点会触发')

print(json.dumps({'source': str(SOURCE.relative_to(ROOT)), 'method': 'AST提取真实方法＋合成夹具，非完整服务/真机验收', 'results': results}, ensure_ascii=False, indent=2))
sys.exit(0 if all(r['passed'] for r in results) else 1)
