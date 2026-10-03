"""离线任务导出适配原型，不是已验证的飞书/MCP实时连接器。
支持本项目表格式，或显式record-export-v1导出契约；不猜第三方响应。
输出仅映射指定白名单字段，默认打印统计；--output需指定新文件且不覆盖。
用法：python 本文件 输入.json --source-label 标签 [--output 新文件.json]
python 本文件 --self-test
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

FIELDS = ['任务编号', '任务名', '状态', '承担者', '验收标准', '关联文件', '所属阶段', '关联原则', '依赖任务', '计划开始', '计划截止']


def normalize(doc, source_label):
    if not source_label.strip(): raise ValueError('必须明确来源标签')
    if doc.get('ok') is not True: raise ValueError('响应失败或未声明成功')
    body = doc.get('data')
    if not isinstance(body, dict): raise ValueError('data须为对象')
    # 已知有后续页则拒绝；缺分页信息只能标unknown，不能宣称全量。
    if body.get('has_more') is True or body.get('page_token') or body.get('next_cursor'):
        raise ValueError('分页未完成，禁止把局部记录写成全量快照')
    if all(k in body for k in ['fields', 'data', 'record_id_list']):
        columns, arrays, rids = body['fields'], body['data'], body['record_id_list']
        if not isinstance(columns, list) or len(columns) != len(set(columns)): raise ValueError('字段列表无效或重复')
        if not isinstance(arrays, list) or not isinstance(rids, list) or len(arrays) != len(rids): raise ValueError('记录数量不一致')
        if any(not isinstance(row, list) or len(row) != len(columns) for row in arrays): raise ValueError('数据列数不一致')
        records = [dict(zip(columns, row)) for row in arrays]
    elif doc.get('schema') == 'record-export-v1':
        items = body.get('items')
        if not isinstance(items, list): raise ValueError('items须为数组')
        rids, records = [], []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('fields'), dict): raise ValueError('记录形态无效')
            rids.append(item.get('record_id')); records.append(item['fields'])
    else: raise ValueError('未知响应形状，须先验证真实工具输出，不自动猜测')
    if any(not isinstance(rid, str) or not rid for rid in rids) or len(rids) != len(set(rids)): raise ValueError('记录ID缺失或重复')
    if any('任务编号' not in record or '状态' not in record for record in records): raise ValueError('缺必要字段')
    pagination = 'complete_declared' if body.get('has_more') is False else 'unknown'
    dropped = sorted(set().union(*(set(r) for r in records)) - set(FIELDS)) if records else []
    return dict(ok=True, data=dict(fields=FIELDS, record_id_list=rids, data=[[r.get(k) for k in FIELDS] for r in records]), provenance=dict(source_label=source_label, normalized_at_utc=datetime.now(timezone.utc).isoformat(), pagination=pagination, source_currentness='not_verified', dropped_field_names=dropped, limitation='白名单不等于脱敏：保留字段内容仍须人工批准可上云与可分享'))


def self_test():
    row={'任务编号':'ZG-SYN-1','状态':'待启动','验收标准':'合成验收','AI执行记录':'不应进入输出'}
    table=dict(ok=True,data=dict(fields=list(row),record_id_list=['r1'],data=[list(row.values())],has_more=False))
    exported=dict(ok=True,schema='record-export-v1',data=dict(items=[dict(record_id='r1',fields=row)],has_more=False))
    a,b=normalize(table,'合成表'),normalize(exported,'合成记录')
    assert a['data']==b['data'] and 'AI执行记录' not in a['data']['fields']
    assert a['provenance']['pagination']=='complete_declared'
    unknown=dict(ok=True,data=dict(fields=list(row),record_id_list=['r1'],data=[list(row.values())]))
    assert normalize(unknown,'合成未知页')['provenance']['pagination']=='unknown'
    bads=[dict(ok=False,data={}),dict(ok=True,data=dict(has_more=True)),dict(ok=True,data=dict(items=[])),dict(ok=True,schema='record-export-v1',data=dict(items=[dict(record_id='r1',fields=row),dict(record_id='r1',fields=row)],has_more=False))]
    for bad in bads:
        try: normalize(bad,'合成反例')
        except ValueError: pass
        else: raise AssertionError('坏响应被接受')
    print('self-test PASS：两种显式导出等价、白名单、分页完整/未知/未完成、失败响应、未知形状、重复ID')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input',nargs='?');p.add_argument('--source-label');p.add_argument('--output');p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:self_test();sys.exit(0)
    if not a.input or not a.source_label:p.error('需明确输入文件与来源标签')
    try:
        raw=Path(a.input).read_bytes();text=raw.decode('utf-16') if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else raw.decode('utf-8-sig')
        result=normalize(json.loads(text),a.source_label);result['provenance']['source_sha256']=hashlib.sha256(raw).hexdigest()
        if a.output:
            with Path(a.output).open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
        print(json.dumps(dict(records=len(result['data']['data']),pagination=result['provenance']['pagination'],output_written=bool(a.output),source_currentness='not_verified'),ensure_ascii=False))
    except (ValueError,TypeError,KeyError,OSError) as ex:
        print('适配拒绝：'+str(ex),file=sys.stderr);sys.exit(1)
