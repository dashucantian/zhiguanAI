"""真机长跑实录：按固定间隔从 HMD 页面回读段时钟与张力读数，落 JSONL。

用法：python vr_gates/record_headset_run.py <url子串> <输出文件> [秒数]
"""
import asyncio
import json
import sys
import time
import urllib.request

import websockets

PORT = 9223
INTERVAL = 0.5

EXPROBE = """(async () => {
  const d = window.__mandalaDiag || null;
  const ps = d ? d.pathStage : null;
  const ctl = window.__stageCtl;
  const st = ctl ? ctl.state() : null;
  const r = { ok: !!(ps && ps.enabled && st) };
  if (st) {
    r.idx = st.idx;
    r.phase = ps ? ps.phases[st.idx] : null;
    r.wall = st.wallT0 === null ? null : +((performance.now()/1000 - st.wallT0)).toFixed(3);
    r.events = (st.events || []).map(e => ({
      at: +(e.atSec == null ? -1 : e.atSec).toFixed(3), phase: e.phase, kind: e.kind }));
    r.fault = st.fault || false;
    r.tickErr = st.tickErr || null;
    r.synthEmitted = st.synthEmitted;
    r.session = !!st.sessionActive;
  }
  if (ps) {
    r.tensionEnabled = ps.tension ? ps.tension.enabled : null;
    r.tensionMode = ps.tension ? ps.tension.mode : null;
    r.tensors = ps.tensors || null;
  }
  /* 退出报告每拍都抓：报告只活在页面内存里，标签一旦被重载就没了
     （10-12 真机首跑的退出报告即因此被一份 2D 空点退出覆盖）。 */
  r.report = window.__stageReport || null;
  return JSON.stringify(r);
})()"""


async def send(ws, method, params=None):
    send.counter = getattr(send, "counter", 0) + 1
    mid = send.counter
    await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == mid:
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result", {})


async def main():
    pat, out_path = sys.argv[1], sys.argv[2]
    limit = float(sys.argv[3]) if len(sys.argv) > 3 else 130.0
    deadline = time.time() + limit
    ws = None
    with open(out_path, "w", encoding="utf-8") as fh:
        while time.time() < deadline:
            if ws is None:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=3) as r:
                        pages = [t for t in json.load(r)
                                 if t.get("type") == "page" and pat in t.get("url", "")]
                    if not pages:
                        await asyncio.sleep(1)
                        continue
                    ws = await websockets.connect(pages[0]["webSocketDebuggerUrl"],
                                                  max_size=16 * 1024 * 1024)
                    await send(ws, "Runtime.enable")
                except Exception as e:
                    sys.stderr.write(f"attach fail: {e}\n")
                    ws = None
                    await asyncio.sleep(1)
                    continue
            try:
                res = await send(ws, "Runtime.evaluate",
                                 {"expression": EXPROBE, "returnByValue": True,
                                  "awaitPromise": True})
                val = res.get("result", {}).get("value")
                rec = json.loads(val) if isinstance(val, str) else {"raw": str(val)}
                rec["pc_ts"] = round(time.time(), 3)
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
            except Exception as e:
                sys.stderr.write(f"eval fail (re-attach): {e}\n")
                try:
                    await ws.close()
                except Exception:
                    pass
                ws = None
            await asyncio.sleep(INTERVAL)
    if ws is not None:
        await ws.close()
    print(f"recorded -> {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
