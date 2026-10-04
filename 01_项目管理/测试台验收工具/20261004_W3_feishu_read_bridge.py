"""Offline bridge for observed Feishu record_search payload -> existing W3 adapter.
No network, imports only existing pure adapter/check modules. No production code.
Explicit selected fields; missing checkbox stays null, false remains false.
Completeness means complete query result, NEVER full table unless unfiltered.
Run: python SCRIPT --root PROJECT --input FILE --output NEW_FILE --query-scope TEXT
Use --self-test for synthetic checks. Existing outputs are never overwritten.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone

SAFE = ['任务编号','任务名','状态','验收标准','所属阶段','关联原则','依赖任务','计划开始','计划截止','裁决确认','承接状态','更新时间']


def load(root, filename, name):
    path = root / '01_项目管理/测试台验收工具' / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(payload):
    if not isinstance(payload, dict) or payload.get('code', 0) != 0 or 'errorMessage' in payload:
        raise ValueError('failed/unknown response')
    if payload.get('has_more') is not False or payload.get('page_token'):
        raise ValueError('query pagination incomplete or unknown')
    items, total = payload.get('items'), payload.get('total')
    if not isinstance(items, list) or type(total) is not int or total != len(items):
        raise ValueError('query total mismatch')
    prepared = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('fields'), dict):
            raise ValueError('invalid record')
        fields = {k: copy.deepcopy(v) for k,v in item['fields'].items() if k in SAFE}
        if '依赖任务' not in fields:
            raise ValueError('dependency field not returned; cannot assert no dependencies')
        links = fields['依赖任务']
        if links == {}:
            fields['依赖任务'] = []
        elif isinstance(links, dict) and isinstance(links.get('link_record_ids'), list):
            ids = links['link_record_ids']
            if any(not isinstance(x, str) or not x for x in ids):
                raise ValueError('invalid dependency ID')
            fields['依赖任务'] = ids
        else:
            raise ValueError('unobserved dependency shape')
        if '裁决确认' in fields and type(fields['裁决确认']) is not bool:
            raise ValueError('checkbox must be explicit bool; never bool(container)')
        prepared.append({'record_id':item.get('record_id'), 'fields':fields})
    return {'ok':True,'schema':'record-export-v1','data':{'items':prepared,'has_more':False}}


def bridge(payload, root, query_scope):
    if not query_scope.strip(): raise ValueError('query scope required')
    adapter = load(root, '20261003_W3_task_export_adapter.py', 'old_adapter')
    checker = load(root, '20261003_W3_task_snapshot_check.py', 'old_checker')
    prepared = prepare(payload)
    normalized = adapter.normalize(prepared, 'offline capture of observed Feishu record_search shape')
    # Preserve boolean/control metadata deliberately omitted by old presentation adapter.
    controls = ['裁决确认','承接状态','更新时间']
    normalized['data']['fields'].extend(controls)
    for row, record in zip(normalized['data']['data'], prepared['data']['items']):
        row.extend(record['fields'].get(k) for k in controls)
    normalized['provenance'].update({
        'query_scope':query_scope, 'table_complete':False,
        'capture_processed_at_utc':datetime.now(timezone.utc).isoformat(),
        'remote_retrieved_at_utc':None,
        'capture':'tool response manually transcribed; semantic spot-readback, not original wire bytes',
        'checkbox_missing_semantics':'null means not returned; false is retained explicitly',
        'not_requested_fields':['承担者','关联文件','AI执行记录','裁决'],
        'null_cell_semantics':'not returned/not requested, not proof of empty remote field',
        'source_currentness':'not independently verified by this offline bridge'})
    normalized['provenance']['dropped_field_names'] = sorted(
        set().union(*(set(r['fields']) for r in payload['items'])) - set(SAFE))
    audit = checker.audit(normalized)
    audit['scope'] = 'selected-query structure, not full-table audit or task acceptance'
    return normalized, audit


def self_test(root):
    def doc(fields):return {'has_more':False,'total':1,'items':[{'record_id':'r1','fields':fields}]}
    f={'任务编号':'ZG-SYN','状态':'进行中','验收标准':'synthetic','依赖任务':{},'裁决确认':False}
    n,a=bridge(doc(f),root,'synthetic single query')
    i=n['data']['fields'].index('裁决确认')
    assert n['data']['data'][0][i] is False
    del f['裁决确认'];assert bridge(doc(f),root,'synthetic')[0]['data']['data'][0][i] is None
    for bad in [dict(doc(f),has_more=True),dict(doc(f),total=2),{'code':1254018},dict(doc(f),has_more=None)]:
        try:bridge(bad,root,'synthetic')
        except ValueError:pass
        else:raise AssertionError('bad payload accepted')
    f['裁决确认']=[False]
    try:bridge(doc(f),root,'synthetic')
    except ValueError:pass
    else:raise AssertionError('container treated as checkbox')
    f['裁决确认']=False;f['依赖任务']={'link_record_ids':['outside']}
    n,a=bridge(doc(f),root,'synthetic')
    assert any(x['kind']=='unresolved_dependency' for x in a['issues'])
    assert n['provenance']['table_complete'] is False
    print('PASS: false/missing/container checkbox; incomplete/unknown/error/count rejection; dependency shape; query scope')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--query-scope');p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:self_test(a.root);raise SystemExit(0)
    if not a.input or not a.output or not a.query_scope:p.error('input/output/query-scope required')
    raw=a.input.read_bytes();payload=json.loads(raw.decode('utf-8-sig'))
    normalized,audit=bridge(payload,a.root,a.query_scope)
    normalized['provenance']['capture_file_sha256']=hashlib.sha256(raw).hexdigest()
    with a.output.open('x',encoding='utf-8') as f:json.dump({'snapshot':normalized,'audit':audit},f,ensure_ascii=False,indent=2)
    print(json.dumps({'records':len(normalized['data']['data']),'audit':audit},ensure_ascii=False))
