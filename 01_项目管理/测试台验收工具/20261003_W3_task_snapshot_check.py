"""只读任务快照审计：不联网、不回写、不输出任务正文或人员信息。
输入兼容现有_records_raw.json。输出仅字段统计、ZG编号及结构性发现。
python 本文件 --self-test
python 本文件 <明确快照路径> --source-label <来源标签>
非空问题退出2，输入错误退出1；不自行判定任务完成或法师裁决。
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone


def scalar(v):
    if v is None: return ''
    if isinstance(v, list): return '/'.join(scalar(x) for x in v)
    if isinstance(v, dict): return str(v.get('text') or v.get('name') or v.get('id') or '')
    return str(v)


def date(v):
    if v in (None, ''): return None
    if isinstance(v, (int, float)) and v > 1e12: return int(v)
    if isinstance(v, str):
        dt = datetime.fromisoformat(v.replace('Z', '+00:00'))
        if dt.tzinfo is None: raise ValueError('日期无时区，禁止依赖运行机器猜时区')
        return int(dt.timestamp() * 1000)
    raise ValueError('未知日期格式')


def audit(doc):
    if doc.get('ok') is not True: raise ValueError('源响应未声明ok=true')
    data = doc['data']; fields = data['fields']; arrays = data['data']; rids = data['record_id_list']
    if len(fields) != len(set(fields)): raise ValueError('字段名重复')
    if len(arrays) != len(rids): raise ValueError('记录ID与数据行数不一致')
    if len(rids) != len(set(rids)): raise ValueError('记录ID重复')
    if not all(len(r) == len(fields) for r in arrays): raise ValueError('数据列数不一致')
    rows = [dict(zip(fields, r)) for r in arrays]
    ids = set(rids); nodes = {}; issues = []; labels = {}
    statuses = {'待启动', '进行中', '待法师审定', '待法师决策', '已完成', '已搁置'}
    scheduled = principles = deps = 0; zg_seen = set()
    for rid, row in zip(rids, rows):
        zg = scalar(row.get('任务编号')); labels[rid] = zg or '(无编号)'
        def issue(kind, **more): issues.append(dict(kind=kind, task=zg or '(无编号)', **more))
        if not zg: issue('missing_task_number')
        elif zg in zg_seen: issue('duplicate_task_number')
        zg_seen.add(zg)
        if not scalar(row.get('验收标准')).strip(): issue('missing_acceptance')
        status = scalar(row.get('状态'))
        if status not in statuses: issue('unknown_status')
        links = row.get('依赖任务') or []
        if not isinstance(links, list): raise ValueError('依赖任务须为数组，未知形态不得静默忽略')
        links = [x.get('id') if isinstance(x, dict) else x for x in links]
        if any(not isinstance(x, str) or not x for x in links): raise ValueError('依赖项缺明确记录ID')
        if len(links) != len(set(links)): issue('duplicate_dependency')
        deps += len(links)
        for link in links:
            if link == rid: issue('self_dependency')
            elif link not in ids: issue('unresolved_dependency', note='可能外部任务或分页未取全，须核对来源')
        try:
            start, end = date(row.get('计划开始')), date(row.get('计划截止'))
            if (start is None) != (end is None): issue('partial_schedule')
            if start is not None and end is not None:
                scheduled += 1
                if end < start: issue('reversed_schedule')
        except (ValueError, OverflowError):
            issue('invalid_schedule'); start = end = None
        principles += bool(row.get('关联原则'))
        nodes[rid] = dict(dep=links, start=start, end=end)
    visiting, done, cycles = set(), set(), set()
    def visit(rid, path):
        if rid in visiting:
            cyc = path[path.index(rid):]
            cycles.add(tuple(sorted(labels[x] for x in cyc))); return
        if rid in done: return
        visiting.add(rid)
        for dep in nodes[rid]['dep']:
            if dep in nodes: visit(dep, path + [rid])
        visiting.remove(rid); done.add(rid)
    for rid in nodes: visit(rid, [])
    for cycle in sorted(cycles): issues.append(dict(kind='dependency_cycle', tasks=list(cycle)))
    for rid, node in nodes.items():
        for dep in node['dep']:
            if dep in nodes and node['start'] is not None and nodes[dep]['end'] is not None and node['start'] < nodes[dep]['end']:
                issues.append(dict(kind='schedule_dependency_overlap', task=labels[rid], dependency=labels[dep], note='按完成后启动假设提示，若允许重叠需明确依赖类型'))
    return dict(record_count=len(rows), with_principles=principles, with_full_schedule=scheduled, dependency_edge_count=deps, issues=issues, limitations=['本地快照不是远端实时状态', '不以文件mtime当业务更新时间', '零依赖不证明任务互相独立', '本工具只查结构，不能判定验收证据充分或法师授权有效'])


def self_test():
    fields = ['任务编号', '状态', '验收标准', '依赖任务', '计划开始', '计划截止', '关联原则']
    def doc(rows, rids): return dict(ok=True, data=dict(fields=fields, data=rows, record_id_list=rids))
    good = ['ZG-T1', '进行中', '合成验收', [], None, None, ['合成原则']]
    assert not audit(doc([good], ['r1']))['issues']
    bad = ['ZG-T2', '待启动', '', ['r2', 'missing'], '2026-10-03T00:00:00+08:00', '2026-10-02T00:00:00+08:00', []]
    kinds = {x['kind'] for x in audit(doc([bad], ['r2']))['issues']}
    assert {'missing_acceptance', 'self_dependency', 'unresolved_dependency', 'reversed_schedule', 'dependency_cycle'} <= kinds
    a = ['ZG-A', '待启动', 'a', ['rb'], None, None, []]
    b = ['ZG-B', '待启动', 'b', ['ra'], None, None, []]
    assert any(x['kind'] == 'dependency_cycle' for x in audit(doc([a, b], ['ra', 'rb']))['issues'])
    for broken in [doc([good], []), dict(ok=False, data={})]:
        try: audit(broken)
        except ValueError: pass
        else: raise AssertionError('错误输入未拒绝')
    print('self-test PASS：正常输入、缺验收、自依赖、悬空依赖、反向日期、双向循环、行数与失败响应')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('snapshot', nargs='?'); parser.add_argument('--self-test', action='store_true'); parser.add_argument('--source-label', default='未标来源')
    args = parser.parse_args()
    if args.self_test: self_test(); sys.exit(0)
    if not args.snapshot: parser.error('需明确快照路径')
    try:
        raw = Path(args.snapshot).read_bytes()
        text = raw.decode('utf-16') if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else raw.decode('utf-8-sig')
        result = audit(json.loads(text)); result['source_label'] = args.source_label
        result['snapshot_sha256'] = hashlib.sha256(raw).hexdigest()
        result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
        print(json.dumps(result, ensure_ascii=False, indent=2)); sys.exit(2 if result['issues'] else 0)
    except (KeyError, TypeError, ValueError, OSError) as ex:
        print('输入校验失败：' + str(ex), file=sys.stderr); sys.exit(1)
