"""看板自测（只读＋本机回环，不出网、不改他窗文件）。

跑法：python selftest.py
判据全部为实测，不接受名义值。
"""
from __future__ import annotations

import json
import re
import socket
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

FAIL = []
PASS = []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name}｜{detail}")
    print(("[PASS] " if cond else "[FAIL] ") + name + (f"｜{detail}" if detail else ""))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    print("═" * 62)
    print("止观AI 任务看板 · 自测")
    print("═" * 62)

    # ── 0 文件卫生：无 BOM、无 NUL ──
    print("\n【0】文件卫生")
    for p in sorted(HERE.rglob("*")):
        if not p.is_file() or p.suffix not in {".py", ".html", ".md", ".txt"}:
            continue
        if "state" in p.parts:
            continue
        raw = p.read_bytes()
        check(f"{p.name} 无 BOM", not raw.startswith(b"\xef\xbb\xbf"))
        check(f"{p.name} 无 NUL", b"\x00" not in raw)

    # ── 1 数据适配层 ──
    print("\n【1】只读数据适配层")
    import board_config as cfg
    import board_sources as src

    reg = src.models_registry()
    check("模型注册表非空", len(reg["models"]) >= 1, f"{len(reg['models'])} 个")
    check("有默认模型", bool(reg["default"]), reg["default"] or "")
    dumped = json.dumps(reg, ensure_ascii=False)
    leak = [k for k, v in __import__("os").environ.items() if "KEY" in k and v and v in dumped]
    check("注册表不含任何密钥值", not leak, f"泄漏项 {leak}" if leak else "只报 present")
    check("注册表含出网分级标注", all(m.get("egress") for m in reg["models"]))

    sess = src.scan_sessions(limit=15)
    wins = sess["windows"]
    check("扫到 Qoder 会话", len(wins) > 0, f"{len(wins)} 窗")
    check("已登记窗口带项目窗口号", any(w["registered"] and w["window"] for w in wins),
          f"已登记 {sum(1 for w in wins if w['registered'])} 窗")
    check("执行类别一律未验或有据", all(w["execClass"] for w in wins))
    check("不读对话正文（无 message 字段外泄）",
          not any("message" in w for w in wins))
    check("lastPrompt 已截断 ≤120 字", all(len(w.get("lastPrompt") or "") <= 120 for w in wins))
    withtasks = [w for w in wins if w["taskTotal"]]
    check("读到会话内任务进度", len(withtasks) > 0,
          f"{len(withtasks)} 窗有任务，共 {sum(w['taskTotal'] for w in withtasks)} 项")

    res = src.resources()
    check("资源采样有 CPU 数", res["cpuPercent"] is not None, f"CPU {res['cpuPercent']}%")
    check("资源采样有内存数", 0 < res["memPercent"] <= 100, f"内存 {res['memPercent']}%")
    check("进程表只给名字不给命令行", all("cmdline" not in p for p in res["procs"]))

    bl = src.backlog()
    check("维那快照可读", bl.get("ok") is True, bl.get("reason", ""))
    if bl.get("ok"):
        check("快照行数与 total 一致", len(bl["rows"]) == bl["total"], f"{len(bl['rows'])}/{bl['total']}")
        check("字段名动态解析（非硬编码索引）", len(bl["fields"]) >= 10, f"{len(bl['fields'])} 字段")
        check("状态分布非空", bool(bl["byStatus"]), json.dumps(bl["byStatus"], ensure_ascii=False)[:80])
        check("待承接裁决可计数", isinstance(bl["needAccept"], int), f"{bl['needAccept']} 条")

    # ── 2 服务真跑 ──
    print("\n【2】服务端真跑（本机回环）")
    import requests
    import uvicorn

    port = free_port()
    import board_server as bs

    server = uvicorn.Server(uvicorn.Config(bs.app, host="127.0.0.1", port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    up = False
    for _ in range(60):
        try:
            requests.get(base + "/api/health", timeout=1)
            up = True
            break
        except Exception:
            time.sleep(0.25)
    check("服务 15 秒内起来", up)
    if not up:
        return finish()

    t0 = time.perf_counter()
    r = requests.get(base + "/api/health", timeout=5)
    check("/api/health 200", r.status_code == 200, r.text[:80])
    check("health 只报密钥 present 不报值",
          isinstance(r.json().get("keyPresent"), bool))

    r = requests.get(base + "/", timeout=5)
    check("/ 返回界面", r.status_code == 200 and "任务看板" in r.text, f"{len(r.text)} 字节")

    r = requests.get(base + "/api/overview", timeout=20)
    ov = r.json()
    check("/api/overview 200", r.status_code == 200)
    check("overview 有窗口计数", ov.get("windowTotal", 0) > 0, f"窗口 {ov.get('windowTotal')}，活跃 {ov.get('windowRunning')}")
    check("overview 有积压计数", (ov.get("backlogTotal") or 0) > 0, f"{ov.get('backlogTotal')} 行")

    # 等作业队列真跑一轮
    for _ in range(40):
        jobs = requests.get(base + "/api/jobs", timeout=5).json()["jobs"]
        if all(j["runs"] > 0 for j in jobs if j["kind"] == "auto"):
            break
        time.sleep(0.5)
    jobs = requests.get(base + "/api/jobs", timeout=5).json()["jobs"]
    auto = [j for j in jobs if j["kind"] == "auto"]
    check("自动作业都真跑过", all(j["runs"] > 0 for j in auto),
          "、".join(f"{j['id']}={j['runs']}次/{j['lastDurMs']}ms" for j in auto))
    check("自动作业无错误", all(not j["lastError"] for j in auto),
          "；".join(j["lastError"] for j in auto if j["lastError"])[:120])

    # 控制真生效：暂停 → 恢复 → 优先级
    tgt = next(j for j in jobs if j["id"] == "resources")

    def get_job(jid):
        return next(j for j in requests.get(base + "/api/jobs", timeout=5).json()["jobs"] if j["id"] == jid)

    r = requests.post(base + "/api/jobs/resources/control", json={"action": "pause"}, timeout=5).json()
    check("暂停生效", r["ok"] and r["job"]["paused"] is True, r["job"]["state"])
    for _ in range(40):                      # 等在跑的那一次落地，再数增量
        if get_job("resources")["state"] != "running":
            break
        time.sleep(0.25)
    runs_at_pause = get_job("resources")["runs"]
    time.sleep(7)                            # 跨过 interval=5 一个周期
    j2 = get_job("resources")
    check("暂停期间不再跑", j2["runs"] == runs_at_pause, f"{runs_at_pause} → {j2['runs']}")
    r = requests.post(base + "/api/jobs/resources/control", json={"action": "priority", "value": 3}, timeout=5).json()
    check("优先级改到 3", r["ok"] and r["job"]["priority"] == 3)
    r = requests.post(base + "/api/jobs/resources/control", json={"action": "priority", "value": 0}, timeout=5)
    check("越界优先级被拒（0）", r.status_code == 400)
    r = requests.post(base + "/api/jobs/resources/control", json={"action": "resume"}, timeout=5).json()
    check("恢复生效", r["ok"] and r["job"]["paused"] is False)
    time.sleep(7)
    j3 = get_job("resources")
    check("恢复后继续跑", j3["runs"] > runs_at_pause, f"{runs_at_pause} → {j3['runs']}")
    check("低频作业未被饿死（sessions/backlog 各跑过）",
          get_job("sessions")["runs"] > 0 and get_job("backlog")["runs"] > 0,
          f"sessions={get_job('sessions')['runs']} backlog={get_job('backlog')['runs']}")

    # agent 类作业不得假装能跑
    r = requests.post(base + "/api/jobs/live_snapshot/control", json={"action": "run"}, timeout=5).json()
    check("需 AI 窗口的作业如实拒绝", r.get("ok") is False and "AI 窗口" in (r.get("reason") or ""))

    # 投递单
    sid = ov and (requests.get(base + "/api/windows", timeout=20).json()["windows"] or [{}])[0].get("sessionId")
    if sid:
        r = requests.post(base + "/api/dispatch", json={"sessionId": sid, "action": "加速"}, timeout=5).json()
        check("投递单可生成", r.get("ok") is True)
        check("投递单含硬口径", "禁 git add ." in (r.get("text") or ""))
        check("投递单声明不代发", "不代发" in (r.get("note") or ""))

    # SSE
    with requests.get(base + "/api/stream", stream=True, timeout=8) as resp:
        chunk = next(resp.iter_content(2048), b"").decode("utf-8", "replace")
    check("SSE 有推流", chunk.startswith("data: ") and "overview" in chunk, f"{len(chunk)} 字节首帧")

    # 对话：本机规则应答必须真答得出数；云端模型要么答、要么给可执行错误
    r = requests.post(base + "/api/chat", json={"text": "现在几个窗口在跑", "modelId": "board-local"}, timeout=30)
    body = r.text
    check("/api/chat 200", r.status_code == 200)
    check("本机规则应答有流式内容", '"delta"' in body, body[:80])
    joined = "".join(json.loads(p[6:])["delta"] for p in body.split("\n\n")
                     if p.startswith("data: ") and "delta" in p)
    check("本机应答含真实窗口数", str(ov.get("windowTotal")) in joined, joined[:70])

    r = requests.post(base + "/api/chat", json={"text": "今天天气如何", "modelId": "board-local"}, timeout=30)
    fb = "".join(json.loads(p[6:])["delta"] for p in r.text.split("\n\n")
                 if p.startswith("data: ") and "delta" in p)
    check("答不了的开放问题如实说明边界（不谎称大模型）",
          "本机规则应答" in fb and "不是大模型" in fb, fb[:80])

    r = requests.post(base + "/api/chat", json={"text": "资源占用", "modelId": "board-local"}, timeout=30)
    j2txt = "".join(json.loads(p[6:])["delta"] for p in r.text.split("\n\n")
                    if p.startswith("data: ") and "delta" in p)
    check("本机应答能报资源", "CPU" in j2txt and "内存" in j2txt, j2txt[:60])

    r = requests.post(base + "/api/chat", json={"text": "在吗", "modelId": "qwen-flash"}, timeout=40)
    check("云端模型：通或给出可执行错误", ('"delta"' in r.text) or ("error" in r.text), r.text[:110])
    r = requests.post(base + "/api/chat", json={"text": "   "}, timeout=10)
    check("空消息被拒", r.status_code == 400)

    # 探活：本机模型恒通；云端如实报断，不得假装通
    r = requests.post(base + "/api/models/board-local/probe", timeout=10).json()
    check("本机模型探活=通", r.get("ok") is True)
    r = requests.post(base + "/api/models/qwen-flash/probe", timeout=40).json()
    key_ok = bool(__import__("os").environ.get("QIANWEN_API_KEY"))
    check("云端探活如实回报（不伪造通）",
          (r.get("ok") is True) or (key_ok and not r.get("ok") and r.get("reason")),
          ("通 " + str(r.get("ms")) + "ms") if r.get("ok") else str(r.get("reason"))[:90])

    # ── 3 界面离线可用与脱敏 ──
    print("\n【3】界面自查")
    html = (HERE / "static" / "index.html").read_text(encoding="utf-8")
    check("界面无外链 CDN", not re.search(r'(src|href)="https?://', html))
    check("界面含一级内容警示", "一级内容" in html and "禁止" in html)
    check("界面含语音出网提示", "出网" in html)
    check("界面声明不代发消息", "不代发" in html)
    check("界面无硬编码密钥", "sk-" not in html)
    check("界面含隐私闸门面板", "隐私闸门" in html and "屏幕共享" in html)
    check("界面声明截图不入库不出网", "不入库" in html and "不出网" in html)
    check("state/.gitignore 全排除＋保留自身",
          (HERE / "state" / ".gitignore").read_text(encoding="utf-8").strip().splitlines()[-1] == "!.gitignore")
    phone = re.findall(r'1[3-9]\d{9}', html)
    check("界面无手机号", not phone, str(phone))
    blk = html.split("$$('#jobTbl [data-j]')")[1].split("/* ── 窗口")[0]
    blk = re.sub(r"//[^\n]*", "", blk)   # 剥行内注释：注释里提到旧写法会误伤位置判定
    i_cmp, i_asg = blk.rfind("==='inc'"), blk.find("action='priority'")
    check("优先级 ＋/− 先判增量后改 action（曾错序致两键同向）",
          i_cmp != -1 and i_asg != -1 and i_cmp < i_asg, f"判位 {i_cmp}／改位 {i_asg}")

    # ── 4 隐私闸门（服务端强制） ──
    print("\n【4】隐私闸门：屏幕共享／权限控制／脱敏一律本机")
    import board_privacy as priv

    cloud = src.get_model("qwen-flash")
    localm = src.get_model("board-local")
    lm = src.get_model("lmstudio-local")
    check("出网判定：千问=出网", priv.is_local(cloud) is False)
    check("出网判定：本机规则=不出网", priv.is_local(localm) is True)
    check("出网判定：LM Studio=不出网（127.0.0.1）", priv.is_local(lm) is True)

    before = priv.counters()
    dummy_phone = "138" + "0013" + "8000"          # 拼接构造，避免仓库里出现真手机号字面量
    dummy_card = "6222" + "0212" + "3456" + "7890123"
    g = priv.guard_outbound(f"请把学员曾某某的督导记录发我，手机 {dummy_phone}", cloud)
    check("闸2：一级内容＋云端=拒发", g["allowed"] is False and "闸2" in g["reason"], g["reason"][:50])
    check("闸2 计数真增", priv.counters()["blockedTier1"] == before["blockedTier1"] + 1)
    check("闸2 拒发时不返回原文", g["text"] == "")

    g = priv.guard_outbound(f"联系人 {dummy_phone}，邮箱 a.b@c.com，卡号 {dummy_card}", cloud)
    check("闸3：个人标识被脱敏后放行", g["allowed"] is True and dummy_phone not in g["text"]
          and "a.b@c.com" not in g["text"] and dummy_card not in g["text"], g["text"][:70])
    check("闸3 命中三类", set(g["hits"]) >= {"手机号", "邮箱", "银行卡"}, str(g["hits"]))
    check("闸3 计数真增", priv.counters()["redacted"] > before["redacted"])

    g = priv.guard_outbound("学员督导记录与声纹样本", localm)
    check("本机模型：一级内容原文放行（不出网）", g["allowed"] is True and "学员" in g["text"])

    check("闸1：截图拒送云端模型", priv.guard_screen(cloud)["allowed"] is False)
    check("闸1：截图允许送本机模型", priv.guard_screen(lm)["allowed"] is True)

    r = requests.post(base + "/api/screen/capture", json={"modelId": "qwen-flash"}, timeout=10)
    check("HTTP：截图送云端被 403 拒", r.status_code == 403 and "闸1" in r.text, r.text[:70])

    r = requests.post(base + "/api/chat", json={"text": "把学员档案发我", "modelId": "qwen-flash"}, timeout=20)
    check("HTTP：一级内容走云端被拦", '"blocked": true' in r.text and "闸2" in r.text, r.text[:90])

    r = requests.get(base + "/api/privacy", timeout=10).json()
    check("/api/privacy 给出原则与三道闸", len(r["policy"]["gates"]) == 3 and "不上云端" in r["policy"]["principle"])
    check("/api/privacy 计数不含原文", all(isinstance(v, (int, str)) for v in r["counters"].values()))

    r = requests.post(base + "/api/screen/capture", json={}, timeout=30).json()
    check("本机截屏真出图", r.get("ok") is True and r.get("sizeKB", 0) > 20,
          f"{r.get('width')}×{r.get('height')}｜{r.get('sizeKB')} KB")
    if r.get("ok"):
        shot = HERE / "state" / "screen" / r["file"]
        check("截图落在 state/screen/", shot.exists())
        import subprocess
        ci = subprocess.run(["git", "check-ignore", "-v", str(shot)], capture_output=True, cwd=str(HERE))
        ci_out = (ci.stdout + ci.stderr).decode("utf-8", "replace")
        check("截图被 git 忽略（不可能入库）", ci.returncode == 0, ci_out.strip()[:90])
        rk = requests.get(base + "/api/screen/latest", timeout=10)
        check("截图只经回环取回", rk.status_code == 200 and rk.headers["content-type"] == "image/png",
              f"{len(rk.content)} 字节")
        shot.unlink()                      # 自测产物，按显式文件名清理
        check("自测截图已按显式文件名清除", not shot.exists())

    server.should_exit = True
    time.sleep(0.4)
    return finish()


def finish() -> int:
    print("\n" + "═" * 62)
    print(f"通过 {len(PASS)} 项｜失败 {len(FAIL)} 项")
    for f in FAIL:
        print("  [FAIL] " + f)
    print("═" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
