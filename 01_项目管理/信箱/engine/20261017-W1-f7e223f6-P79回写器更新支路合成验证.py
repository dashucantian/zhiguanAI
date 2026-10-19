# -*- coding: utf-8 -*-
"""P79 甲｜维那源表回写器·更新支路 合成验证（一次运行·零网络）。

依据：01_项目管理/信箱/engine/20261017-W3-c5d442aa-P73P79P82P83批准后派工_v1.md §P79
被测件：01_项目管理/任务关系图/20261012_W3_维那源表回写器_v1.py（现工作树版）
对照件：同路径 HEAD 版（本件用 `git show` 取字节，写进本次独占临时目录，只读不回写）

边界（由断言坐实，不靠声明）：
  · 绝不连飞书：拉取器的 http_json／tenant_token／读凭据面全部换成本脚本的内存假表；
    dry-run 面另装哨兵——一旦代码去碰拉取器即当场 ERROR。
  · 不读凭据：假 token 是字面 FAKE_TOKEN，不打开任何配置文件；假表只在内存。
  · 不写真实源表：payload 只落在本次独占 TemporaryDirectory，退出即销毁。
  · 不读真实脑电／数据根／人员信息。**批二（10-17 退补函）起不再读取真实候登稿**，
    该景改由同型合成行覆盖（T12）。
退出码：全 PASS 才 0；存在 FAIL/ERROR 即 1。
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]                                  # 本件→engine→信箱→01_项目管理→仓库根
TARGET = REPO / "01_项目管理" / "任务关系图" / "20261012_W3_维那源表回写器_v1.py"
REL = "01_项目管理/任务关系图/20261012_W3_维那源表回写器_v1.py"

BASE_TOKEN = "X4xXbTF57acOnZs1ZzZcF4P2nJg"
TABLE_ID = "tblLf45tgSgBoLue"
RID = "recFAKE0001"

FIELDS = [
    {"field_name": "任务名", "type": 1},
    {"field_name": "关联文件", "type": 1},
    {"field_name": "AI执行记录", "type": 1},
    {"field_name": "承接状态", "type": 3, "property": {"options": [
        {"name": "待启动"}, {"name": "待承接"}, {"name": "执行中"}, {"name": "分析完成"}, {"name": "已完成"}]}},
    {"field_name": "状态", "type": 3, "property": {"options": [
        {"name": "待启动"}, {"name": "进行中"}, {"name": "已完成"}]}},
    {"field_name": "裁决", "type": 3, "property": {"options": [{"name": "准"}, {"name": "缓"}, {"name": "驳"}]}},
    # 10-17 退补函第 2 条点名「`AI执行窗口` 至少可能承载文本」⇒ 本假表把它配成**文本列**（不带选项），
    # 这样才试得出"拟写空串"与"首尾空格差"两景；真表上它到底是单选还是文本，属未验项（见输出末行）。
    {"field_name": "AI执行窗口", "type": 1},
    {"field_name": "任务编号", "type": 22},          # 自动编号＝服务端持有列
    {"field_name": "更新时间", "type": 1002},        # 系统修改时间＝服务端持有列
]


class FakeTable:
    """内存假表：既记调用，也存行值。不落盘、不联网。

    两个可控故障口子（只为把闸验到，不为让结果变绿）：
      · `hide_after_put`＝PUT 之后 GET 再也读不到该记录（退补函第 1 条那一景）；
      · `put_suffix`＝服务端落下的值与拟写值差一个尾空格（退补函第 2 条那一景）。"""

    def __init__(self, rows=None, hide_after_put=False, put_suffix=None):
        self.records = {k: dict(v) for k, v in (rows or {}).items()}
        self.created = []
        self.calls = []
        self.hide_after_put = hide_after_put
        self.put_suffix = put_suffix
        self.puts = 0

    def http_json(self, url, method, head, payload=None):
        self.calls.append({"url": url, "method": method, "head": head, "payload": payload})
        after = url.split("/tables/")[1] if "/tables/" in url else url
        tid, _, seg = after.partition("/")          # 表号与路径段分开（首版混在一起⇒fields 分支永不命中）
        path = seg.split("?")[0]
        if path == "fields":
            return 200, {"code": 0, "data": {"items": FIELDS, "has_more": False}}
        if path == "records/search":
            items = [{"fields": {"任务编号": f.get("任务编号")}}
                     for f in self.created if f.get("任务编号")]
            return 200, {"code": 0, "data": {"items": items, "has_more": False}}
        if path == "records/batch_create":
            new = []
            for r in (payload or {}).get("records") or []:
                rec = dict(r.get("fields") or {})
                self.created.append(rec)
                new.append({"record_id": "recNEW%d" % len(self.created)})
            return 200, {"code": 0, "data": {"records": new}}
        if path.startswith("records/"):
            rid = path[len("records/"):]
            if method == "PUT":
                self.puts += 1
                fields = dict((payload or {}).get("fields") or {})
                if self.put_suffix is not None:
                    fields = {k: (v + self.put_suffix if isinstance(v, str) else v)
                              for k, v in fields.items()}
                self.records.setdefault(rid, {}).update(fields)
                return 200, {"code": 0, "data": {"record": {
                    "record_id": rid, "fields": dict(self.records[rid])}}}
            if self.hide_after_put and self.puts:
                return 200, {"code": 0, "data": {}}   # 写后读不到记录，就是这一景
            if rid not in self.records:
                return 200, {"code": 0, "data": {}}
            return 200, {"code": 0, "data": {"record": {
                "record_id": rid, "fields": dict(self.records[rid])}}}
        raise AssertionError("假表收到未预期的路径：%s（method=%s）" % (path, method))


class _FakeLoader:
    """顶掉拉取器的模块面：鉴权与 HTTP 全变假件，被替换的只有 m 的属性。

    ⚠本 loader 一旦被调用就记一笔（次数＋它挡下的真身路径），用来证明**拉取器文件本身
    没有被执行**（真执行＝会去读本机凭据）；被测件里真跑的只有 _load_puller 内那层闭包。"""

    def __init__(self, table):
        self.table = table
        self.seen = []
        self.executed = 0

    def create_module(self, spec):
        # module_from_spec 的硬要求：自定义 loader 只给 exec_module 会 ImportError
        # 「loaders that define exec_module() must also define create_module()」；返回 None＝用默认建模块。
        return None

    def exec_module(self, module):
        t = self.table
        self.executed += 1
        module.dsh_home = lambda: Path("FAKE_HOME_NOT_READ")
        module.load_bots = lambda p: [{"name": "维那", "appId": "FAKE_APP", "secretRef": "FAKE_REF"}]
        module.pick_bot = lambda bots, name: bots[0]
        module.read_secret = lambda p, ref: "FAKE_SECRET_NOT_READ"
        module.tenant_token = lambda app, secret: "FAKE_TOKEN"
        module.http_json = t.http_json
        module.__file__ = "FAKE_PULLER_NOT_READ"


def load_writer(path=TARGET, table=None, puller_forbidden=False):
    """载入被测件。table≠None ⇒ 只把 importlib 的取模块函数临时换成假 loader（拉取器本体真跑）；
    puller_forbidden ⇒ 把 _load_puller 换成抛错哨兵（证明该档一次都不碰鉴权／网络面）。"""
    spec = importlib.util.spec_from_file_location("weina_writer_%d" % id(path), str(path))
    w = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(w)
    w._fake_loader = None
    if puller_forbidden:
        def _boom():
            raise AssertionError("该档却去加载了鉴权／网络面（拉取器）")
        w._load_puller = _boom
    elif table is not None:
        orig = importlib.util.spec_from_file_location
        real_load = w._load_puller
        fl = _FakeLoader(table)
        w._fake_loader = fl

        def patched(name, location):
            fl.seen.append(str(location))
            # ModuleSpec 的真身在 importlib.machinery（首版误写成 importlib.util⇒AttributeError）
            return importlib.machinery.ModuleSpec(name, fl)

        def wrapped():
            importlib.util.spec_from_file_location = patched
            try:
                return real_load()
            finally:
                importlib.util.spec_from_file_location = orig
        w._load_puller = wrapped
    return w


def run(w, argv, env_write=None):
    old_argv, old_env = sys.argv, os.environ.get("ZIGUAN_WRITE_OK")
    if env_write is None:
        os.environ.pop("ZIGUAN_WRITE_OK", None)
    else:
        os.environ["ZIGUAN_WRITE_OK"] = env_write
    buf = io.StringIO()
    try:
        sys.argv = ["verify"] + argv
        with contextlib.redirect_stdout(buf):
            try:
                rc = w.main()
            except SystemExit as ex:
                # SystemExit 不是 Exception：真 CLI 由解释器收成退码，本脚本必须同样处理，
                # 否则 FATAL｜找不到拉取器 一类硬退出会把整个验证带崩（而不是记成一项 FAIL）
                rc = 0 if ex.code is None else (ex.code if isinstance(ex.code, int) else 1)
                buf.write("[SystemExit] %s\n" % ex.code)
        return rc, buf.getvalue()
    finally:
        sys.argv = old_argv
        if old_env is None:
            os.environ.pop("ZIGUAN_WRITE_OK", None)
        else:
            os.environ["ZIGUAN_WRITE_OK"] = old_env


def write_payload(td, rows):
    n = len([x for x in os.listdir(td) if x.startswith("p_")]) + 1
    p = Path(td) / ("p_%d.json" % n)
    p.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")
    return p


def upd(new=None, old=None, rid=RID, op="update"):
    r = {"ref": "ZG-070", "fields": new or {"承接状态": "执行中"}}
    if op is not None:
        r["op"] = op
    if rid is not None:
        r["record_id"] = rid
    if old is not None:
        r["expect_old"] = old
    return r


def head_copy(td):
    """取 HEAD 版字节写进独占临时目录，作对照件（不改仓库、不回写）。"""
    out = subprocess.run(["git", "-C", str(REPO), "show", "HEAD:" + REL],
                         capture_output=True)
    assert out.returncode == 0, "git show 退码 %s：%s" % (out.returncode, out.stderr[:200])
    p = Path(td) / "HEAD_对照版.py"
    p.write_bytes(out.stdout)
    # 被测件按 `Path(__file__).parent / 拉取器名` 找鉴权面，文件不在⇒_load_puller 直接 SystemExit，
    # 对照档就跑到不了同一档。这里放一枚**同名空壳**只为了让 is_file() 过关：它的 exec_module 已被
    # 假 loader 顶掉，真身（读凭据那一层）从头到尾没被执行，空壳内容也永远不会被求值。
    stub = Path(td) / "20261007_W3_维那快照拉取_v1.py"
    if not stub.exists():
        stub.write_text("# 空壳：只为 is_file() 过关，exec_module 由假 loader 顶替，永不求值\n",
                        encoding="utf-8")
    return p, out.stdout, len(out.stdout)


RESULTS = []


def decision_lines(out):
    """拆成两把尺：
      · 决策行＝FATAL／[已写]／[跑后…]／[写前…]——**必须与 HEAD 逐字相同**，这类行决定"写不写、写几条"；
      · 横幅行＝═══ 开头，只取到第一个「：」或「。」为止——P79 在横幅尾巴上加了
        「新建 N 条、更新 M 条」的条数，语义（哪一档、通过还是拒）不变，所以按前缀比。
    逐字差异不藏着：调用方把整行差集打出来给 W3 看。"""
    keep, banners = [], []
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("═══"):
            banners.append(s.split("：")[0].split("。")[0])
        elif s.startswith(("FATAL", "[已写]", "[跑后", "[写前")):
            keep.append(s)
    return keep, banners


def check(name, fn):
    t0 = time.perf_counter()
    try:
        RESULTS.append((name, "PASS", fn(), time.perf_counter() - t0))
    except AssertionError as ex:
        RESULTS.append((name, "FAIL", str(ex), time.perf_counter() - t0))
    except Exception as ex:
        RESULTS.append((name, "ERROR", "%s: %s\n%s" %
                        (type(ex).__name__, ex, traceback.format_exc(limit=4)), time.perf_counter() - t0))


def main():
    t_start = time.perf_counter()
    td_ctx = tempfile.TemporaryDirectory(prefix="p79_weina_")
    TD = td_ctx.name

    def t1_dry_run_zero_network():
        w = load_writer(puller_forbidden=True)
        rows = [{"ref": "ZG-081", "fields": {"任务名": "合成新建行", "状态": "待启动",
                                             "承接状态": "待承接", "AI执行窗口": "W1工程"}},
                upd(new={"承接状态": "执行中"}, old={"承接状态": "待启动"})]
        rc, out = run(w, ["--dry-run", "--rows", str(write_payload(TD, rows))])
        assert rc == 0, "预演退出码 %s（应 0）；尾部输出：%s" % (rc, out[-400:])
        assert "未发任何网络调用" in out, out[-400:]
        assert "［更新］record_id＝%s" % RID in out, "预演未显示 record_id：\n%s" % out[-500:]
        assert "申报旧值" in out and "拟写新值" in out, "预演未显示旧值→新值：\n%s" % out[-500:]
        assert "新建 1／更新 1" in out, "op 分类计数不符：\n%s" % out[-300:]
        return "混合批次（新建 1＋更新 1）预演 rc=0；哨兵未触发⇒预演档一次都没碰拉取器/HTTP/凭据面"

    def t2_over_column():
        w = load_writer(puller_forbidden=True)
        rc, out = run(w, ["--dry-run", "--rows", str(write_payload(TD, [
            upd(new={"承接状态": "执行中", "AI执行记录": "顺手扩一列"}, old={"承接状态": "待启动"})]))])
        assert rc == 1, "越列更新竟被放行（rc=%s）" % rc
        assert "［update］：越列" in out and "AI执行记录" in out, out[-400:]
        assert "更新只许" in out and "裁决" in out, "未回显四列范围：\n%s" % out[-400:]
        return ("更新带第 5 列（AI执行记录）即拒：拦在 load_payload 的列白名单层，"
                "回显逐字＝%s" % [l.strip() for l in out.splitlines() if "越列" in l])

    def t3_no_record_id():
        w = load_writer(puller_forbidden=True)
        rc, out = run(w, ["--dry-run", "--rows", str(write_payload(TD, [
            upd(new={"承接状态": "执行中"}, old={"承接状态": "待启动"}, rid=None)]))])
        assert rc == 1, "无 record_id 的更新竟被放行（rc=%s）" % rc
        assert "不把更新降为新建" in out, out[-400:]
        return "缺稳定 record_id ⇒ 拒绝，不退化成 batch_create"

    def t4_op_mix():
        w = load_writer(puller_forbidden=True)
        rc1, out1 = run(w, ["--dry-run", "--rows", str(write_payload(TD, [
            {"ref": "ZG-082", "op": "create", "record_id": RID,
             "fields": {"任务名": "合成行", "状态": "待启动"}}]))])
        assert rc1 == 1, "create 带 record_id 竟放行（rc=%s）" % rc1
        assert "明确区分" in out1, out1[-400:]
        rc2, out2 = run(w, ["--dry-run", "--rows", str(write_payload(TD, [
            upd(rid=RID, op=None, new={"承接状态": "执行中"}, old={"承接状态": "待启动"})]))])
        assert rc2 == 1, "带 record_id 但未标 op 竟被默认成新建（rc=%s）" % rc2
        assert "未标 op" in out2, out2[-400:]
        return "两种混标都拒：create 不许带 record_id；带 record_id 不标 op ⇒ 拒绝猜意图"

    def t5_expect_old():
        w = load_writer(puller_forbidden=True)
        rc1, out1 = run(w, ["--dry-run", "--rows", str(write_payload(TD, [upd(old=None)]))])
        assert rc1 == 1 and "expect_old" in out1, "缺 expect_old 未拒（rc=%s）：%s" % (rc1, out1[-300:])
        rc2, out2 = run(w, ["--dry-run", "--rows", str(write_payload(TD, [
            upd(new={"承接状态": "执行中", "裁决": "准"}, old={"承接状态": "待启动"})]))])
        assert rc2 == 1 and "改哪几列就先报哪几列旧值" in out2, "键不齐未拒（rc=%s）：%s" % (rc2, out2[-300:])
        return "更新必须有 expect_old，且键与拟改列一一对应"

    def t6_forbidden_both():
        w = load_writer(puller_forbidden=True)
        rc1, out1 = run(w, ["--dry-run", "--rows", str(write_payload(TD, [
            {"ref": "ZG-084", "fields": {"任务名": "x", "承担者": "真人名", "状态": "待启动"}}]))])
        assert rc1 == 1 and "承担者" in out1, out1[-300:]
        rc2, out2 = run(w, ["--dry-run", "--rows", str(write_payload(TD, [
            upd(new={"裁决": "准", "承担者": "真人名"}, old={"裁决": "缓"})]))])
        assert rc2 == 1 and "承担者" in out2, out2[-300:]
        # 现列配置下一个结构性事实（非本次改动造成，HEAD 同）：承担者一类列都在白名单外，
        # 所以先被"越列"闸拦下，`FATAL｜禁写列出现在 payload` 那一层在本 payload 面**走不到**。
        reached = "禁写列出现在 payload" in (out1 + out2)
        return ("承担者在 create 与 update 两路都拒（逐字：%s｜%s）。⚠现态观察：FORBIDDEN_COLS 那层"
                "在现列配置下**不可达**（四列全在白名单外⇒先被越列闸拦），属冗余防线，本次一字未动"
                % ([l.strip() for l in out1.splitlines() if "承担者" in l],
                   [l.strip() for l in out2.splitlines() if "承担者" in l])
                + ("；本轮竟可达⇒请看 diff" if reached else ""))

    def t7_endpoint():
        tb = FakeTable({RID: {"承接状态": "待启动", "任务名": "合成已有行"}})
        w = load_writer(table=tb)
        rc, out = run(w, ["--落笔", "--rows", str(write_payload(TD, [
            upd(new={"承接状态": "执行中"}, old={"承接状态": "待启动"})]))], env_write="1")
        assert rc == 0, "更新落笔 rc=%s：%s" % (rc, out[-600:])
        put = [c for c in tb.calls if c["method"] == "PUT"]
        assert len(put) == 1, "PUT 次数＝%d（应 1）" % len(put)
        want = "https://open.feishu.cn/open-apis/bitable/v1/apps/%s/tables/%s/records/%s" % (
            BASE_TOKEN, TABLE_ID, RID)
        assert put[0]["url"] == want, "端点不符：%s" % put[0]["url"]
        assert put[0]["payload"] == {"fields": {"承接状态": "执行中"}}, put[0]["payload"]
        assert tb.records[RID]["承接状态"] == "执行中", "假表未更新⇒PUT 没落到 record_id 上"
        assert not tb.created, "更新批次却建了新行：%s" % tb.calls
        gets = [c for c in tb.calls if c["method"] == "GET" and ("/records/" + RID) in c["url"]]
        assert len(gets) == 2, "写前旧值核对＋写后回读应各 1 次 GET，实得 %d" % len(gets)
        assert all(c["head"]["Authorization"] == "Bearer FAKE_TOKEN" for c in tb.calls)
        assert "写后回读] 更新 1 条逐列复核一致" in out, out[-500:]
        # 拉取器真身（读凭据那层）没被执行：假 loader 记下它挡下的路径，须正是 10-07 拉取器
        assert w._fake_loader.executed == 1 and len(w._fake_loader.seen) == 1, \
            "假 loader 执行 %d 次／挡下 %d 条（应各 1）" % (w._fake_loader.executed, len(w._fake_loader.seen))
        blocked = w._fake_loader.seen[0]
        assert "20261007_W3_维那快照拉取_v1.py" in blocked, "挡下的不是拉取器：%s" % blocked
        return ("PUT＝%s/records/{record_id}（record_id 与 payload 一致），"
                "GET 两次（旧值核对＋写后回读），零 batch_create，鉴权走假 token；"
                "拉取器真身未执行，被挡下的路径逐字＝%s" % ("/bitable/v1/apps/{base}/tables/{table}", blocked))

    def t8_old_value_conflict():
        tb = FakeTable({RID: {"承接状态": "已完成", "任务名": "合成已有行"}})
        w = load_writer(table=tb)
        rows = [{"ref": "ZG-085", "fields": {"任务名": "合成新建行", "状态": "待启动"}},
                upd(new={"承接状态": "执行中"}, old={"承接状态": "待启动"})]
        rc, out = run(w, ["--落笔", "--rows", str(write_payload(TD, rows))], env_write="1")
        assert rc == 1, "旧值冲突未拒（rc=%s）：%s" % (rc, out[-500:])
        assert "旧值冲突" in out and "整批不写" in out, out[-500:]
        writes = [c for c in tb.calls if c["method"] == "PUT" or c["url"].endswith("batch_create")]
        assert not writes, "冲突后仍发出写调用：%s" % [c["url"] for c in writes]
        assert tb.created == [], "冲突后新建仍落了：%s" % tb.created
        return "盘上现值（已完成）≠申报旧值（待启动）⇒ rc=1、零写调用，同批新建一并扣住"

    def t9_write_gate():
        tb = FakeTable({RID: {"承接状态": "待启动"}})
        w = load_writer(table=tb)
        rc, out = run(w, ["--落笔", "--rows", str(write_payload(TD, [
            upd(new={"承接状态": "执行中"}, old={"承接状态": "待启动"})]))], env_write=None)
        assert rc == 1 and "ZIGUAN_WRITE_OK" in out, out[-300:]
        assert not [c for c in tb.calls if c["method"] == "PUT"], "无环境变量仍写了"
        return "缺 ZIGUAN_WRITE_OK=1 ⇒ 更新支路同样拒写（双闸未被新支路旁路）"

    def t10_no_regression_vs_head():
        hp, head_bytes, nbytes = head_copy(TD)
        scen, wording = [], []
        rows_a = [{"ref": "ZG-086", "fields": {"任务名": "甲", "状态": "待启动",
                                               "承接状态": "待承接", "AI执行窗口": "W1工程"}},
                  {"ref": "ZG-087", "fields": {"任务名": "乙", "状态": "待启动", "裁决": "准"}}]
        pa = write_payload(TD, rows_a)
        rows_b = [{"ref": "ZG-088", "fields": {"任务编号": "ZG-088", "任务名": "丙", "状态": "待启动"}}]
        pb = write_payload(TD, rows_b)
        for tag, argv, env in (("预演", ["--dry-run", "--rows", str(pa)], None),
                               ("只读联网校验", ["--check-remote", "--rows", str(pa)], None),
                               ("落笔", ["--落笔", "--rows", str(pa)], "1"),
                               ("预演·含任务编号行", ["--dry-run", "--rows", str(pb)], None)):
            tb_now, tb_head = FakeTable({}), FakeTable({})
            rc_now, out_now = run(load_writer(table=tb_now), argv, env_write=env)
            rc_head, out_head = run(load_writer(path=hp, table=tb_head), argv, env_write=env)
            k_now, b_now = decision_lines(out_now)
            k_head, b_head = decision_lines(out_head)
            assert rc_now == rc_head, "%s 退码不同：现版 %s／HEAD %s" % (tag, rc_now, rc_head)
            assert k_now == k_head, "%s 决策行不同：\n现版 %s\nHEAD %s" % (tag, k_now, k_head)
            assert b_now == b_head, "%s 横幅语义不同：\n现版 %s\nHEAD %s" % (tag, b_now, b_head)
            assert [(c["method"], c["url"]) for c in tb_now.calls] == \
                [(c["method"], c["url"]) for c in tb_head.calls], "%s 调用序列不同" % tag
            diff = sorted(set(out_now.splitlines()) ^ set(out_head.splitlines()))
            for d in diff:
                if d.strip():
                    wording.append("%s｜%s" % (tag, d.strip()[:150]))
            scen.append("%s(rc=%s%s)" % (tag, rc_now, "、逐字同" if not diff else "、措辞差%d行" % len(diff)))
        return ("新建路径四档与 HEAD 同退码、同决策行、同横幅语义、同调用序列（method＋url）：%s\n"
                "      对照件＝git show HEAD 的 %d 字节／%d 个换行符（LF）。本处**只报 LF 个数**，行数口径一律以外部 `wc -l` 现测为准（LF＋1 会多报一行，上批函里 261／262 不一致就是这么来的——退补函文书订正第 2 条）\n"
                "      ⚠措辞差逐字（不改判、只加条数，供 W3 核对是否可接受）：\n%s"
                % ("、".join(scen), nbytes, head_bytes.count(b"\n"),
                   ("\n      ".join(wording) if wording else "（无）")))

    def t11_create_deadend_note():
        tb = FakeTable({})
        w = load_writer(table=tb)
        rows = [{"ref": "ZG-089", "fields": {"任务名": "不带号的合成新建行", "状态": "待启动"}}]
        rc, out = run(w, ["--落笔", "--rows", str(write_payload(TD, rows))], env_write="1")
        hp, _, _ = head_copy(TD)
        rc_h, out_h = run(load_writer(path=hp, table=FakeTable({})), ["--落笔", "--rows", str(
            write_payload(TD, rows))], env_write="1")
        same = (rc == rc_h) and ("未全命中" in out) == ("未全命中" in out_h)
        assert same, "现版与 HEAD 在该景不一致：现版 rc=%s／HEAD rc=%s" % (rc, rc_h)
        verdict = "两版同样在写后校验和处拒（未全命中）" if "未全命中" in out else "两版同样通过"
        return ("⚠现态观察（非本次改动造成，已与 HEAD 同景对照）：%s——新建路径的写后校验和按 `任务编号` 命中计数，"
                "而 `任务编号` 自 10-14 起在 FORBIDDEN_COLS 内⇒不带该列的批次无号可对、带该列的批次被硬拒。"
                "此面归 W3 在实际改表阶段裁定，本次未动（rc 现版 %s／HEAD %s）" % (verdict, rc, rc_h))

    def t12_over_column_synthetic():
        """退补函明令「不再读取真实候登稿」⇒ 此景改为**同型合成行**：新建行带 `任务编号` 即拒。
        真实 8 行稿的现态沿用上批交验函 §五 第 2 条已交记录，本轮不重读、不重报。"""
        w = load_writer(puller_forbidden=True)
        rc, out = run(w, ["--dry-run", "--rows", str(write_payload(TD, [
            {"ref": "ZG-090", "fields": {"任务编号": "ZG-090", "任务名": "合成行", "状态": "待启动"}}]))])
        assert rc == 1 and "越列" in out and "任务编号" in out, out[-300:]
        return ("合成新建行带 `任务编号` ⇒ rc=1、点名越列（逐字：%s）。本轮**未读真实候登稿**，"
                "该稿的死结仍按上批记录挂在 W3 名下"
                % [l.strip() for l in out.splitlines() if "越列" in l][:1])

    def t14_missing_record_after_put():
        tb = FakeTable({RID: {"AI执行窗口": "W1工程"}}, hide_after_put=True)
        w = load_writer(table=tb)
        rc, out = run(w, ["--落笔", "--rows", str(write_payload(TD, [
            upd(new={"AI执行窗口": ""}, old={"AI执行窗口": "W1工程"})]))], env_write="1")
        assert rc == 1, "写后读不到记录却通过了（rc=%s）：%s" % (rc, out[-500:])
        assert "写后回读不到记录" in out and "存在性未证实" in out, out[-500:]
        assert "落笔完成" not in out, "缺记录却报了完成：\n%s" % out[-400:]
        assert "逐列复核一致" not in out, out[-400:]
        assert tb.puts == 1, "PUT 次数＝%d（应 1，写前一切正常）" % tb.puts
        return ("写前记录存在、PUT 之后 GET 返回无 record、拟写值＝空串 ⇒ 判失败、不报完成。"
                "旧写法把缺记录折成空字段再比，空 vs 空会假报「逐列一致」——这一景正是退补函第 1 条")

    def t15_space_difference():
        # a) 申报旧值带尾空格、盘上现值不带 ⇒ 旧值核对必须判不符、整批不写
        tb1 = FakeTable({RID: {"AI执行窗口": "W1工程"}})
        w1 = load_writer(table=tb1)
        rc1, out1 = run(w1, ["--落笔", "--rows", str(write_payload(TD, [
            upd(new={"AI执行窗口": "W2文档"}, old={"AI执行窗口": "W1工程 "})]))], env_write="1")
        assert rc1 == 1 and "旧值冲突" in out1, "旧值带空格却对上盘上不带空格的值⇒%s" % out1[-400:]
        assert not [c for c in tb1.calls if c["method"] == "PUT"], "已判冲突还写了"
        # b) 写后服务端落下的值多一个尾空格 ⇒ 回读必须判不一致、不报完成
        tb2 = FakeTable({RID: {"AI执行窗口": "W1工程"}}, put_suffix=" ")
        w2 = load_writer(table=tb2)
        rc2, out2 = run(w2, ["--落笔", "--rows", str(write_payload(TD, [
            upd(new={"AI执行窗口": "W2文档"}, old={"AI执行窗口": "W1工程"})]))], env_write="1")
        assert rc2 == 1 and "写后回读未对上" in out2, "尾空格差异被吞⇒%s" % out2[-400:]
        assert "落笔完成" not in out2, out2[-400:]
        # c) 反证：把比较函数换回"一律 strip"的旧口径，同两景都会**假报成功**⇒ 证明这两闸真在挡东西
        old_norm = lambda v: ("" if v is None else
                              ("｜".join(old_norm(x) for x in v) if isinstance(v, list)
                               else (v.get("text") if isinstance(v, dict) and "text" in v
                                     else ((v.get("name") or "") if isinstance(v, dict) else str(v).strip()))))
        tb3 = FakeTable({RID: {"AI执行窗口": "W1工程"}})
        w3 = load_writer(table=tb3)
        w3._norm_val = old_norm
        rc3, out3 = run(w3, ["--落笔", "--rows", str(write_payload(TD, [
            upd(new={"AI执行窗口": "W2文档"}, old={"AI执行窗口": "W1工程 "})]))], env_write="1")
        tb4 = FakeTable({RID: {"AI执行窗口": "W1工程"}}, put_suffix=" ")
        w4 = load_writer(table=tb4)
        w4._norm_val = old_norm
        rc4, out4 = run(w4, ["--落笔", "--rows", str(write_payload(TD, [
            upd(new={"AI执行窗口": "W2文档"}, old={"AI执行窗口": "W1工程"})]))], env_write="1")
        assert rc3 == 0 and rc4 == 0, "旧口径反证不成立（rc3=%s rc4=%s）⇒ 本项没测到东西" % (rc3, rc4)
        return ("两景都拒：申报旧值带尾空格与盘上现值不等⇒整批不写、零 PUT；服务端落下多一个尾空格⇒写后回读判不等、不报完成。"
                "反证同两景喂给旧「一律 strip」口径＝都假报成功（rc3=%s、rc4=%s）⇒ 撤 strip 这一步真的在挡东西"
                % (rc3, rc4))

    check("T1 默认预演零网络（混合批次）", t1_dry_run_zero_network)
    check("T2 更新越列拒绝", t2_over_column)
    check("T3 无 record_id 更新拒绝、不降为新建", t3_no_record_id)
    check("T4 新建与更新明确区分", t4_op_mix)
    check("T5 expect_old 缺失或键不齐拒绝", t5_expect_old)
    check("T6 承担者两路硬拒（现配置下由越列闸先拦，禁写列层不可达）", t6_forbidden_both)
    check("T7 更新端点与 record_id 正确（模拟 HTTP）", t7_endpoint)
    check("T8 旧值冲突拒绝⇒整批不写", t8_old_value_conflict)
    check("T9 落笔双闸对更新同样生效", t9_write_gate)
    check("T10 新建路径无回归（逐档对照 HEAD，含措辞差逐字）", t10_no_regression_vs_head)
    check("T11 新建校验和死结现态（与 HEAD 对照）", t11_create_deadend_note)
    check("T12 新建行带任务编号即拒（合成，本轮不读真实稿）", t12_over_column_synthetic)
    check("T14 写后读不到记录⇒判失败、不报完成（退补第1条）", t14_missing_record_after_put)
    check("T15 首尾空格差不被吞（退补第2条，含旧口径反证）", t15_space_difference)

    leftovers = len(os.listdir(TD))
    td_ctx.cleanup()
    RESULTS.append(("T13 临时面清理（独占目录）",
                    "PASS" if not os.path.exists(TD) else "FAIL",
                    "独占目录内产物 %d 个（合成 payload＋HEAD 对照件），退出后目录存在＝%s"
                    % (leftovers, os.path.exists(TD)), 0.0))

    print("=" * 74)
    for name, st, detail, dt in RESULTS:
        print("[%s] %s  (%.0f ms)" % (st, name, dt * 1000))
        for line in str(detail).splitlines():
            print("      " + line)
    print("=" * 74)
    n_pass = sum(1 for r in RESULTS if r[1] == "PASS")
    print("计：%d 项，PASS %d，非 PASS %d" % (len(RESULTS), n_pass, len(RESULTS) - n_pass))
    print("覆盖面（全内存假表＋独占临时目录内合成 payload，且对照 HEAD 版同景跑）："
          "预演零网络、更新四列闸、record_id 三闸、expect_old 闸、旧值核对、写后回读、"
          "写后缺记录不报完成、首尾空格差不被吞（含旧口径反证）、落笔双闸、"
          "新建路径四档无回归、临时目录即用即清。本轮未读真实候登稿。")
    print("未验：真实飞书连通与真实源表读写（本轮禁止）；端点在官方文档层面的最终核定"
          "（本件只断言代码构造出的 URL 原文，**不据此起「官方已确认」这句话**）；"
          "真表各列到底是单选还是文本——本假表把 `AI执行窗口` 配成**文本列**，"
          "这是为试「拟写空串」与「首尾空格差」两景而设的**假设**，真表若为单选则空串会先被选项闸拦；"
          "真实凭据取用路径；新建校验和死结与候登稿禁列的修法（归 W3 裁，本窗未动）。")
    print("总耗时 %.2f s；退出码约定：全 PASS 才 0，任何 FAIL/ERROR 即 1"
          % (time.perf_counter() - t_start))
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
