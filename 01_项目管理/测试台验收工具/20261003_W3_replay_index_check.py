"""只读回放索引验证；不联网、不改索引、不执行索引中的代码或命令。
python 本文件 明确索引路径 项目根目录
python 本文件 --self-test
Git证据从确切commit解析；工作区证据核hash。仅输出事件ID与检查状态。
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def structure(doc):
    events = doc.get('events')
    if not isinstance(events, list): raise ValueError('events须为数组')
    ids = [e['id'] for e in events]
    if len(ids) != len(set(ids)): raise ValueError('事件ID重复')
    by_id = {e['id']: e for e in events}
    for e in events:
        parent = e.get('parent')
        if parent and parent not in by_id: raise ValueError('父事件缺失')
        seen = set(); current = e['id']
        while current:
            if current in seen: raise ValueError('事件父链成环')
            seen.add(current); current = by_id[current].get('parent')
    for b in doc.get('branch_trials', []):
        if b.get('parent_event') not in by_id: raise ValueError('分支父事件缺失')
    return events


def verify(doc, index, root):
    events = structure(doc); root = root.resolve(); results = []
    for e in events:
        for item in e.get('evidence', []):
            target = (index.parent / item['path']).resolve()
            try: rel = target.relative_to(root).as_posix()
            except ValueError: raise ValueError('证据路径越出项目根目录')
            # 工具层仍需目录授权；此处按当前项目规约加内容目录阻断。
            if any(k in rel for k in ['原始素材', '人格档案', '机密-学员数据']):
                raise ValueError('禁止访问的证据目录')
            version = item.get('version', '')
            if version.startswith('git:'):
                commit = version[4:]
                if not commit or not all(c in '0123456789abcdefABCDEF' for c in commit):
                    raise ValueError('Git版本须为明确hash，不接受任意表达式')
                r = subprocess.run(['git', '-C', str(root), 'show', commit + ':' + rel], capture_output=True)
                status = 'git_version_verified' if r.returncode == 0 else 'git_evidence_missing'
                raw = r.stdout if r.returncode == 0 else None
            else:
                expected = item.get('working_tree_sha256_at_index_verification')
                raw = target.read_bytes() if target.is_file() else None
                status = 'working_tree_missing' if raw is None else ('working_tree_hash_unpinned' if not expected else ('working_tree_hash_verified' if hashlib.sha256(raw).hexdigest() == expected else 'working_tree_changed'))
            results.append(dict(event=e['id'], status=status, sha256=hashlib.sha256(raw).hexdigest() if raw is not None else None))
    return results


def self_test():
    structure(dict(events=[dict(id='A'), dict(id='B', parent='A')], branch_trials=[dict(parent_event='B')]))
    for events in [[dict(id='A'), dict(id='A')], [dict(id='A', parent='B')], [dict(id='A', parent='B'), dict(id='B', parent='A')]]:
        try: structure(dict(events=events))
        except ValueError: pass
        else: raise AssertionError('错误结构未拒绝')
    print('self-test PASS：有效父链、重复ID、父节点缺失、循环')


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('index', nargs='?'); p.add_argument('root', nargs='?'); p.add_argument('--self-test', action='store_true'); a = p.parse_args()
    if a.self_test: self_test(); sys.exit(0)
    if not a.index or not a.root: p.error('需明确索引路径与项目根目录')
    try:
        index = Path(a.index); doc = json.loads(index.read_text(encoding='utf-8-sig'))
        results = verify(doc, index, Path(a.root))
        print(json.dumps(dict(scope='只核证据可追溯性，不核判断正确或授权充分', results=results), ensure_ascii=False, indent=2))
        sys.exit(0 if all(r['status'] in ['git_version_verified', 'working_tree_hash_verified'] for r in results) else 2)
    except (ValueError, KeyError, TypeError, OSError) as ex:
        print('回放校验拒绝：' + str(ex), file=sys.stderr); sys.exit(1)
