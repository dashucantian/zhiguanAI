"""真机 CDP 探针：从 PICO 头显的 WebLayer 里读页面实时状态。

用法：python vr_gates/probe_headset_cdp.py [url_substring]
不带参数时列出所有 page 目标；带参数时选中 URL 含该子串的第一个页面并回读状态。
"""
import asyncio
import json
import sys
import urllib.request

import websockets

PORT = 9223
_id = 0


async def send(ws, method, params=None):
    global _id
    _id += 1
    mine = _id
    await ws.send(json.dumps({"id": mine, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(await ws.recv())
        if msg.get("id") == mine:
            if "error" in msg:
                raise RuntimeError(f"{method}: {msg['error']}")
            return msg.get("result", {})


async def evaluate(ws, expr):
    r = await send(ws, "Runtime.evaluate", {
        "expression": expr, "returnByValue": True, "awaitPromise": True})
    exc = r.get("exceptionDetails")
    if exc:
        return {"EVAL_ERROR": str(exc.get("exception", exc))[:300]}
    return r.get("result", {}).get("value")


EXPROBE = """(async () => {
  const d = window.__mandalaDiag || null;
  const ps = d ? d.pathStage : null;
  const ctl = window.__stageCtl;
  const st = ctl ? ctl.state() : null;
  const out = {
    href: location.href,
    ready: document.readyState,
    isSecureContext: window.isSecureContext,
    hasNavigatorXr: !!navigator.xr,
    vrErr: window.__vrErr || null,
    hidden: document.visibilityState,
    canvasCount: document.querySelectorAll('canvas').length,
    badgeText: (document.getElementById('stageBadge')||{}).textContent || null,
    xrSupported: navigator.xr ? await navigator.xr.isSessionSupported('immersive-vr') : 'no-xr',
    hasStageCtl: !!ctl,
    diagStage: d ? d.stage : null,
    variant: d ? d.variant : null,
  };
  if (ps && ps.enabled) {
    out.phases = ps.phases;
    out.segSec = ps.segSec;
    out.tensionSelf = ps.tension;
    out.tensors = ps.tensors;
  }
  if (st) {
    out.stageIdx = st.idx;
    out.phaseKey = (window.__mandalaDiag && st.idx != null && ps) ? ps.phases[st.idx] : null;
    out.events = (st.events || []).map(e => e.phase + ':' + e.kind);
    out.fault = st.fault || false;
    out.tickErr = st.tickErr || null;
    out.report = (ctl.report && ctl.report()) || null;
  }
  return JSON.stringify(out);
})()"""


async def main():
    pat = sys.argv[1] if len(sys.argv) > 1 else None
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=4) as r:
        targets = [t for t in json.load(r) if t.get("type") == "page"]
    if not pat:
        for t in targets:
            print(t["url"][:110])
        return
    hits = [t for t in targets if pat in t["url"]]
    if not hits:
        print(json.dumps({"NO_TARGET_FOR": pat, "pages": [t["url"][:90] for t in targets]},
                         ensure_ascii=False))
        return
    ws = await websockets.connect(hits[0]["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024)
    await send(ws, "Runtime.enable")
    val = await evaluate(ws, EXPROBE)
    print(val if isinstance(val, str) else json.dumps(val, ensure_ascii=False))
    ws.close()


if __name__ == "__main__":
    asyncio.run(main())
