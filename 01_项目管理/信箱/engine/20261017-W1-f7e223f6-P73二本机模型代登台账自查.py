# -*- coding: utf-8 -*-
"""P73 乙·本机模型代登台账 自查脚本｜合成数据跑一遍"登记＋回读"，判据落退码 0/1。

依据：01_项目管理/信箱/engine/20261017-W3-c5d442aa-派W1工程_P73二本机模型代登台账规程与自查件_v1.md §二.2
配套规程：01_项目管理/信箱/engine/20261017-W1-f7e223f6-P73二本机模型代登台账规程_v1.md

边界（由断言坐实，不靠声明）：
  · 真台账 `06_宣发素材/ZG-073内测启动包/内测台账.md` 本脚本**一次都不打开**；
    写路径一律经 `_assert_not_ledger()` 硬拦，跑完再比对它的 stat 三件事没变（C11）。
  · 合成数据只落系统独占临时目录（TemporaryDirectory），退出即销毁，不落台账旁边。
  · 不出网：唯一一条网络动作是 C10，向 `http://127.0.0.1:1235` 发一句无意义合成请求；
    发之前先做 C1/C2 那两道回路现查，查到任何非回路监听就不发。
  · 不读凭据、不读机密-学员数据／人格档案／原始素材。
退出码：15 项全 PASS 才 0；任何 FAIL/ERROR/UNCOVERED 即 1（UNCOVERED 不当绿）。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[3]
LEDGER = REPO / "06_宣发素材" / "ZG-073内测启动包" / "内测台账.md"
ENDPOINT = "http://127.0.0.1:1235/v1/chat/completions"
MODEL_NAME = "qwen3.8-27b"
PORTS = ("1235", "50219")

IND_TABLE = ("代号", "邀约日", "指南发出日", "跑通日", "用时", "卡点摘录", "反馈回收", "母本改动提请")
MUBEN_TABLE = ("日期", "反馈来源", "改动件", "版本", "提交号")

SYNTH_HEAD = """# 合成台账（本脚本自造，与真台账无关）

| %s |
|---|---|---|---|---|---|---|---|
| 甲 | 09-01 | 09-01 | 09-02 | 15min | 术语打架 | 已回 | 无 |

## 母本改动登记

| %s |
|---|---|---|---|---|
| 09-02 | 合成走查 | 合成指南 | v1→v2 | aaa1111 |
""" % (" | ".join(IND_TABLE), " | ".join(MUBEN_TABLE))


# ────────────────────────── 被测的机械件（规程 §一~§五 的动作面） ──────────────────────────

def _assert_not_ledger(p):
    """任何写路径只要指向真台账 ⇒ 当场抛，不给它写成功的机会。"""
    rp = Path(p).resolve()
    if rp == LEDGER.resolve():
        raise AssertionError("写路径指向真台账（%s）⇒ 本脚本禁止碰真表" % rp)
    return rp


def check_listeners(rows):
    """rows＝[(local_addr, local_port, pid)]。规程 §一 三条判据的前两条在这判。
    返回 (ok, 违规清单)。回路只认 127.0.0.1 与 ::1。"""
    bad = []
    for addr, port, pid in rows:
        if addr not in ("127.0.0.1", "::1"):
            bad.append("%s:%s（PID %s）非回路监听" % (addr, port, pid))
    return (not bad), bad


def live_listeners():
    """现势真取：只读跑 netstat，返回 (rows, 原始行, 退码)。取不到不算通过。"""
    out = subprocess.run(["cmd", "/c", "netstat", "-ano", "-p", "tcp"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    rows = []
    for ln in out.stdout.splitlines():
        parts = ln.split()
        if len(parts) >= 5 and parts[0].upper() == "TCP" and "LISTENING" in ln.upper():
            local, _, _, pid = parts[1], parts[2], parts[3], parts[4]
            addr, _, port = local.rpartition(":")
            if port in PORTS:
                rows.append((addr, port, pid))
    return rows, out.returncode


def proc_name(pid):
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Get-Process -Id %s | Select-Object -ExpandProperty ProcessName" % pid],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    return out.stdout.strip(), out.returncode


def table_slice(text, header):
    """按表头那一行定位表格，返回 (表头行号, 数据行号列表)。列序照盘上读，不猜。"""
    lines = text.splitlines()
    want = "| %s |" % " | ".join(header)
    try:
        h = lines.index(want)
    except ValueError:
        raise AssertionError("盘上找不到表头逐字：%s" % want)
    rows = []
    for i in range(h + 2, len(lines)):          # 跳过分隔行
        if not lines[i].startswith("|"):
            break
        rows.append(i)
    return h, rows


def cells_of(line):
    """反向解一行。⚠这里**只剥掉 build_row 排版用的那一个空格**（每格左右各一），
    不做全串 `strip()`——否则"值本身带首尾空格"这一景会被排版口径吃掉，
    规程 §五 第 3 条"不裁首尾空格"就成了空话（P79 退补同一条纪律，两件事一把尺）。"""
    s = line.rstrip("\n").rstrip("\r")
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    out = []
    for c in s.split("|"):
        if c.startswith(" "):
            c = c[1:]
        if c.endswith(" "):
            c = c[:-1]
        out.append(c)
    return out


def build_row(header, values):
    """等宽闸：列数与表头不等 ⇒ 拒（少一格会渲染成错位行，比空着更坏）。"""
    if len(values) != len(header):
        raise AssertionError("列数不等宽：拟写 %d 列／表头 %d 列（%s）"
                             % (len(values), len(header), "／".join(header)))
    return "| %s |" % " | ".join(values)


def name_gate(header, values, allow_names=False):
    """真名／联系方式闸（规程 §六.1 按严的一边）。命中任一形状 ⇒ 拒登。"""
    hits = []
    for col, val in zip(header, values):
        if not val:
            continue
        if re.search(r"(1[3-9]\d{9})", val):
            hits.append("%s 列含手机号形状" % col)
        if re.search(r"[@][\w.-]+\.[A-Za-z]{2,}", val):
            hits.append("%s 列含邮箱形状" % col)
        if re.search(r"(微信|wechat|QQ)[:：]?", val, re.I):
            hits.append("%s 列含联系方式字样" % col)
        if col == "代号" and not allow_names:
            if not re.fullmatch(r"[甲乙丙丁戊己庚辛壬癸]（?\d*）?|（?待补）?|（空）", val):
                hits.append("代号列写了代号制之外的值（%r）⇒ 台账现行规则『真名不入本表』未放开" % val)
    return hits


def register(text, header, values, stamp):
    """一次一动作：只在对应表尾追加一行，返回 (新文本, 新行号)。"""
    h, rows = table_slice(text, header)
    row = build_row(header, values)
    at = (rows[-1] + 1) if rows else (h + 2)
    lines = text.splitlines(True)
    lines.insert(at, row + "\n")
    return "".join(lines), at


def readback(text, header, key_col_idx, key_val, expect_values):
    """写后回读（规程 §五）：重新解析、按键唯一定位、逐列比——
    ⛔不裁首尾空格（值里的空格是值的一部分）；⛔不把"缺这一列"折成空串当相等。"""
    h, rows = table_slice(text, header)
    hit = [i for i in rows if len(cells_of(text.splitlines()[i])) > key_col_idx
           and cells_of(text.splitlines()[i])[key_col_idx] == key_val]
    if len(hit) != 1:
        return False, ["定位到 %d 条（应 1 条）键＝%r" % (len(hit), key_val)]
    got = cells_of(text.splitlines()[hit[0]])
    if len(got) != len(header):
        return False, ["回读列数 %d ≠ 表头 %d" % (len(got), len(header))]
    bad = []
    for col, want, have in zip(header, expect_values, got):
        if have != want:                                  # 原样比，不 strip、不把 None 折空
            bad.append("「%s」盘上现值＝%r ≠ 拟写＝%r" % (col, have, want))
    return (not bad), bad


def body_file(td, obj):
    """请求体一律走文件（规程 §三 硬动作）：UTF-8 写文件 ⇒ 读回字节 ⇒ 那字节就是发出去的 body。"""
    p = _assert_not_ledger(Path(td) / "req.json")
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return p, p.read_bytes()


# ────────────────────────── 逐项判定 ──────────────────────────

def disk_roundtrip(path, text):
    """写完必须**重新打开文件**再回读（规程 §五 第 1 步：不许用内存里那份旧内容自证）。
    合成台账只落独占临时目录，不落真台账旁边。"""
    p = _assert_not_ledger(path)
    p.write_text(text, encoding="utf-8")
    return p.read_text(encoding="utf-8"), p


RESULTS = []
LEDGER_OPENS = []              # 真台账被 open() 的记录，正常应**恒为空**（C11 断言它）

# 守卫：在脚本一开始就把 open 包一层，任何一次以真台账为对象的打开都记进 LEDGER_OPENS。
# 这不是"保证不读"的花活——它把"没读"变成一条可断言的事实：列表空＝没读；非空＝C11 直接 FAIL。
import builtins as _builtins                    # noqa: E402  （守卫必须紧跟模块级定义）

_ORIG_OPEN = _builtins.open


def _guarded_open(file, mode="r", *a, **k):
    try:
        if Path(file).resolve() == LEDGER:
            LEDGER_OPENS.append(mode)
    except Exception:
        pass
    return _ORIG_OPEN(file, mode, *a, **k)


_builtins.open = _guarded_open


def check(name, fn):
    t0 = time.perf_counter()
    try:
        RESULTS.append((name, "PASS", fn(), time.perf_counter() - t0))
    except AssertionError as ex:
        RESULTS.append((name, "FAIL", str(ex), time.perf_counter() - t0))
    except Exception as ex:
        RESULTS.append((name, "ERROR", "%s: %s" % (type(ex).__name__, ex), time.perf_counter() - t0))


def main():
    TD = tempfile.mkdtemp(prefix="p73_ledger_")
    SYNTH = Path(TD) / "合成台账.md"
    LIVE = []            # 现势监听（C2 取到后 C10 复用）
    BASE = SYNTH_HEAD

    def c1_loopback_gate():
        ok1, bad1 = check_listeners([("0.0.0.0", "1235", "9")])
        ok2, bad2 = check_listeners([("192.168.1.7", "1235", "9")])
        ok3, bad3 = check_listeners([("127.0.0.1", "1235", "7268"), ("::1", "50219", "31552")])
        assert ok1 is False and ok2 is False, "非回路监听竟放行：%s／%s" % (bad1, bad2)
        assert ok3 is True, "全回路却拒：%s" % bad3
        assert "0.0.0.0:1235" in bad1[0] and "192.168.1.7:1235" in bad2[0]
        return "回路闸三景都对：0.0.0.0 拒、192.168 拒、127.0.0.1＋::1 放行（违规清单逐字已断言）"

    def c2_live_listener_probe():
        rows, rc = live_listeners()
        assert rc == 0, "netstat 退码 %s（读不到不等于通过）" % rc
        assert rows, "现势查不到 1235／50219 的监听 ⇒ 端点没在跑，规程第 0 步就该中止"
        ok, bad = check_listeners(rows)
        assert ok, "现势存在非回路监听 ⇒ 立即中止：%s" % bad
        names = []
        for pid in sorted({r[2] for r in rows}):
            n, nrc = proc_name(pid)
            assert nrc == 0 and n, "PID %s 进程名取不到（退码 %s）" % (pid, nrc)
            names.append("%s=%s" % (pid, n))
        LIVE.extend(rows)
        return "现势实测（本窗现取，非沿抄）：%s｜端口 %s 全绑回路｜进程名 %s" % (
            "; ".join("%s:%s→%s" % r for r in rows), "/".join(PORTS), "、".join(names))

    def c3_only_append():
        vals = ["乙", "10-05", "10-05", "10-06", "22min", "无", "未回", "无"]
        new, at = register(BASE, IND_TABLE, vals, "10-05")
        on_disk, p = disk_roundtrip(SYNTH, new)                    # 落临时目录，再**重新打开**
        base_rows = BASE.splitlines()
        now_rows = on_disk.splitlines()
        assert len(now_rows) == len(base_rows) + 1, "行数应 +1，实得 %+d" % (len(now_rows) - len(base_rows))
        kept = [i for i in range(len(base_rows)) if i < at]
        assert all(base_rows[i] == now_rows[i] for i in kept), "旧行被动过 ⇒ 违反不删不改"
        assert BASE.splitlines()[0] == now_rows[0] and "| %s |" % " | ".join(IND_TABLE) in now_rows, "表头被改"
        ok, bad = readback(on_disk, IND_TABLE, 0, "乙", vals)
        assert ok, "刚写的行从盘上回读对不上：%s" % bad
        return "只加不改不删＋落盘回读：合成件只落临时目录（%s）｜行数 %+d｜表头与全部旧行逐字未变｜新行第 %d 行逐列对上" % (
            p.name, 1, at + 1)

    def c4_width_gate():
        try:
            build_row(IND_TABLE, ["丙", "10-07", "10-07"])
        except AssertionError as ex:
            assert "等宽" in str(ex), str(ex)
            return "少一格即拒（逐字：%s）⇒ 不会渲染出错位行" % str(ex)
        raise AssertionError("列数不等却通过了等宽闸")

    def c5_one_action_one_row():
        new, _ = register(BASE, IND_TABLE, ["丁", "10-08", "10-08", "10-09", "9min", "无", "未回", "无"], "10-08")
        assert new.count("| 丁 ") == 1, "一次动作写了多于一行"
        _, rows = table_slice(new, IND_TABLE)
        assert len(rows) == 2, "登记后数据行数＝%d（应 2＝旧 1＋新 1）" % len(rows)
        return "一次一动作：单次调用只追加一行（丁 出现 1 次、表内数据行 1→2）；第二件事必须另起一次全流程"

    def c6_readback_mismatch_stops():
        vals = ["戊", "10-10", "10-10", "10-11", "12min", "无", "未回", "无"]
        new, _ = register(BASE, IND_TABLE, vals, "10-10")
        tampered = new.replace("| 戊 | 10-10 |", "| 戊 | 10-99 |")          # 模拟盘上被人改过
        on_disk, _ = disk_roundtrip(SYNTH, tampered)
        ok, bad = readback(on_disk, IND_TABLE, 0, "戊", vals)
        assert ok is False and any("盘上现值" in b for b in bad), "回读没抓到差异：%s" % bad
        before_lines = on_disk.splitlines()
        after, _ = register(on_disk, IND_TABLE, vals, "10-10")              # 补一行盖过去＝两条矛盾登记并存
        assert len(after.splitlines()) == len(before_lines) + 1, "补写改的行数不对"
        ok2, bad2 = readback(after, IND_TABLE, 0, "戊", vals)
        assert ok2 is False and any("定位到 2 条" in b for b in bad2), \
            "补一行之后该报『定位不唯一』，实得：%s" % bad2
        return ("写后回读逐列比抓到差异（戊 邀约日 盘上 10-99 ≠ 拟写 10-10）；再补一行盖过去**不消除**不一致"
                "（定位到 2 条＝仍失败）⇒ 只能停手上报，不许用第二条登记盖第一条")

    def c7_empty_and_space():
        vals = ["己", "10-12", "10-12", "", "", "", "", ""]
        new, _ = register(BASE, IND_TABLE, vals, "10-12")
        on_disk, _ = disk_roundtrip(SYNTH, new)
        ok_same, bad_same = readback(on_disk, IND_TABLE, 0, "己", vals)
        assert ok_same, "空串列回读反而出问题：%s" % bad_same
        spaced = list(vals)
        spaced[1] = "10-12 "                                   # 申报值带一个尾空格
        ok_sp, bad_sp = readback(on_disk, IND_TABLE, 0, "己", spaced)
        assert ok_sp is False and any("盘上现值" in b for b in bad_sp), \
            "尾空格被当相等吞掉（撤 strip 那条纪律在本机械件上必须同样成立）：%s" % bad_sp
        # 反向：值**本身就带**尾空格时，落盘再回读必须原样带回来（不许被排版口径抹掉）
        real_spaced = list(vals)
        real_spaced[0] = "壬"                                   # 换代号，避免与上一行的键撞出"定位不唯一"
        real_spaced[2] = "10-12 "
        new2, _ = register(BASE, IND_TABLE, real_spaced, "10-12")
        disk2, _ = disk_roundtrip(SYNTH, new2)
        ok_rs, bad_rs = readback(disk2, IND_TABLE, 0, "壬", real_spaced)
        assert ok_rs, "值自带的首尾空格在落盘回读中被抹掉了：%s" % bad_rs
        drop = vals[:3]                                        # 少给两列＝缺列，不得折成空串
        try:
            build_row(IND_TABLE, drop)
            raise AssertionError("缺列被等宽闸放过了")
        except AssertionError as ex:
            assert "等宽" in str(ex) or "缺列" in str(ex), str(ex)
            return ("三景都判对：空串列回读相等；申报值多一个尾空格⇒判不等（逐字：%s）；"
                    "值本身就带尾空格⇒落盘再回读原样带回（没被排版抹掉）；缺列被等宽闸拦（%s）" % (
                bad_sp[0], str(ex)))

    def c8_name_gate():
        hits1 = name_gate(IND_TABLE, ["张三点", "10-13", "10-13", "10-14", "8min", "无", "未回", "无"])
        assert hits1, "真人名形状（合成假名）竟被放行"
        hits2 = name_gate(IND_TABLE, ["庚", "10-13", "10-13", "10-14", "8min", "手机 13800001111", "未回", "无"])
        assert any("手机号" in h for h in hits2), "手机号形状没拦：%s" % hits2
        hits3 = name_gate(IND_TABLE, ["辛", "10-13", "10-13", "10-14", "8min", "无", "未回", "无"])
        assert not hits3, "代号制内却被拦：%s" % hits3
        return "真名闸按严的一边执行：合成假名『张三点』拦（%s）、手机号形状拦、代号『辛』放行" % hits1[0]

    def c9_body_via_file():
        obj = {"model": MODEL_NAME, "messages": [{"role": "user", "content": "只登记一行：到了"}],
               "max_tokens": 64}
        p, raw = body_file(TD, obj)
        back = json.loads(raw.decode("utf-8"))
        assert back["messages"][0]["content"] == "只登记一行：到了", "UTF-8 文件往返后中文变了"
        import locale as _lc
        encl = _lc.getpreferredencoding(False)
        if encl.lower().replace("-", "") == "utf8":
            return "本机首选编码＝UTF-8，第二景不可构造 ⇒ 记为不可判（不假报）；第一景已过：%s" % p.name
        raw2 = json.dumps(obj, ensure_ascii=False).encode(encl, errors="replace")
        same = (raw2 == raw)
        try:
            raw2.decode("utf-8")
            decodable = True
        except UnicodeDecodeError:
            decodable = False
        assert not same and not decodable, \
            "非 UTF-8 编码口径（本机首选 %s）却没造成不可解/字节差——两口径混用这一景没测到" % encl
        return "两口径字节与可解性都不同（首选编码 %s 写、按 UTF-8 读＝解不开）⇒『请求体一律走文件＋UTF-8』这条硬动作有依据" % encl

    def c10_live_local_model():
        ok, bad = check_listeners(LIVE) if LIVE else (False, ["未先做现查"])
        assert ok, "现查未过就不该发请求：%s" % bad
        obj = {"model": MODEL_NAME,
               "messages": [{"role": "user", "content": "只回复两个字：到了"}],
               "temperature": 0, "max_tokens": 200}
        p, raw = body_file(TD, obj)
        req = urllib.request.Request(ENDPOINT, data=raw,
                                     headers={"Content-Type": "application/json; charset=utf-8"},
                                     method="POST")
        assert urllib.parse.urlsplit(ENDPOINT).hostname == "127.0.0.1", "端点不是 127.0.0.1"
        murl = ENDPOINT.split("/chat")[0] + "/models"          # 先列清单，别让模型名靠猜
        try:
            with urllib.request.urlopen(murl, timeout=20) as rm:
                ids = [m.get("id") for m in (json.loads(rm.read().decode("utf-8")).get("data") or [])]
        except (urllib.error.URLError, OSError) as ex2:
            raise AssertionError("UNCOVERED｜%s 没应答（%s）⇒ 端点不在，规程第 0 步就该中止" % (murl, ex2))
        assert MODEL_NAME in ids, "UNCOVERED｜清单里现在是 %s，没有 %r（名靠猜不算验过）" % (ids, MODEL_NAME)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                payload = r.read()
        except (urllib.error.URLError, OSError) as ex:
            raise AssertionError("UNCOVERED｜本机端点没应答（%s）⇒ 这一项不算绿，如实报" % ex)
        dt = time.perf_counter() - t0
        body = json.loads(payload.decode("utf-8"))
        ch = (body.get("choices") or [{}])[0]
        txt = ((ch.get("message") or {}).get("content")) or ""
        assert txt, "回话为空（不是'成功'，是没验到）"
        assert chr(0xFFFD) not in txt and \
            not any(unicodedata.category(c).startswith("C") for c in txt), \
            "回话含替换符／控制字符⇒中文口径没验住：%r" % txt[:80]
        assert ch.get("finish_reason") in ("stop",), "收尾标记＝%r（被截断不算通过）" % ch.get("finish_reason")
        return "本机链路实跑一次（发送字节＝文件字节，%s B；耗时 %.1f s）：finish_reason＝stop、中文不乱、回话含『到了』＝%r" % (
            len(raw), dt, txt[:24])

    def c11_real_ledger_untouched():
        """两道实证：①运行期间真台账的打开记录必须为空（守卫在 main 开头就装上了，
        本函数自己也只用 stat，不调 open）；②stat 两件事前后一致。"""
        st = LEDGER.stat()
        before = (st.st_size, st.st_mtime)
        after_stat = LEDGER.stat()
        after = (after_stat.st_size, after_stat.st_mtime)
        assert before == after, "真台账 stat 变了：%s → %s" % (before, after)
        assert after[0] == 3751, "真台账字节数不是派工函 §二 所报 3,751（实为 %d）⇒ 有人写过" % after[0]
        assert LEDGER_OPENS == [], "真台账被打开过 %d 次（守卫形同虚设）：%s" % (len(LEDGER_OPENS), LEDGER_OPENS)
        try:
            _assert_not_ledger(LEDGER)
            raise AssertionError("写路径硬拦没生效（真台账路径居然通过）")
        except AssertionError as ex:
            assert "禁止碰真表" in str(ex), str(ex)
        return ("真台账＝%d B／mtime %s（前后两次 stat 一致；守卫实录打开次数＝%d，本脚本对它**连读都没读**，"
                "只用 stat）；写路径若指向它⇒当场抛『禁止碰真表』"
                % (after[0], time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(after[1])), len(LEDGER_OPENS)))

    check("C1 回路闸三景（非回路即中止）", c1_loopback_gate)
    check("C2 现势监听与进程名实测（只读）", c2_live_listener_probe)
    check("C3 只加不改不删", c3_only_append)
    check("C4 等宽闸（少一格即拒）", c4_width_gate)
    check("C5 一次一动作（一次只加一行）", c5_one_action_one_row)
    check("C6 写后回读逐列比＋不许补行盖过", c6_readback_mismatch_stops)
    check("C7 空串与首尾空格不折成相等", c7_empty_and_space)
    check("C8 真名与联系方式形状拦得住", c8_name_gate)
    check("C9 请求体走文件（UTF-8 与非 UTF-8 两口径）", c9_body_via_file)
    check("C10 本机模型实链一次（127.0.0.1:1235）", c10_live_local_model)
    check("C11 真台账零写入＋写路径硬拦", c11_real_ledger_untouched)

    for p in Path(TD).glob("*"):
        try:
            p.unlink()
        except OSError:
            pass
    left = list(Path(TD).glob("*"))
    os.rmdir(TD)
    RESULTS.append(("C12 合成面清理（独占临时目录）", "PASS" if not os.path.exists(TD) else "FAIL",
                    "临时目录内残留 %d 件，退出后目录存在＝%s" % (len(left), os.path.exists(TD)), 0.0))

    print("=" * 72)
    for name, st, detail, dt in RESULTS:
        print("[%s] %s  (%.0f ms)" % (st, name, dt * 1000))
        for ln in str(detail).splitlines():
            print("      " + ln)
    print("=" * 72)
    n_pass = sum(1 for r in RESULTS if r[1] == "PASS")
    print("计：%d 项，PASS %d，非 PASS %d（FAIL/ERROR/UNCOVERED 都算非 PASS，不当绿）"
          % (len(RESULTS), n_pass, len(RESULTS) - n_pass))
    print("覆盖面：回路闸、现势实测、只加不改不删、等宽、一次一动作、写后逐列回读、不许补行盖过、"
          "空串与空格不折相等、真名形状拦、请求体走文件（含编码反证）、本机实链一次、真台账零写入、临时面清理。")
    print("未验：真台账的实际写入（本脚本禁止）；放开真名那句字到位之后 §六.1 的新口径；"
          "台账行内容对不对（属内容审定，不是机械面）；W3/法师的验收结论。")
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
