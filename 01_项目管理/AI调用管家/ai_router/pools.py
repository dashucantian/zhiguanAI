"""跨池兜底：这条调用走哪个池、哪个模型，以及为什么。

三池顺序（2026-11-05 法师准）：本地 Qwen → 百炼／Token Plan → OpenCode Go。
理由：本地与百炼不限量或按量计价，Go 最贵（按模型美元封顶＋三层窗口）。

规矩：
  · 客户端点名了模型 → 先在「能接这个模型」的池里按上面顺序找。
  · 客户端没点名（auto）→ 先按 Go 的规则选模型；Go 这一路走不通，才按本地→百炼往下兜。
  · 每池都有单池配额；Go 还有每模型美元封顶与 5 小时／周窗口，超了当这一池接不了。
  · Go 的按月总额度用完后改走充值余额（按量计费，不吃订阅封顶）；余额也空了才接不了。
  · 密钥只从环境变量读，不落盘、不进日志；没有密钥的池直接判为不可用。
"""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass, field

from . import plans, router, store

PROBE_TIMEOUT = 0.4
GO_PLAN_POOL = plans.GO_PLAN_POOL
GO_BALANCE_POOL = plans.GO_BALANCE_POOL


def local_address() -> tuple[str, int]:
    """本地 Qwen 的地址。默认 127.0.0.1:8080，可用环境变量改（端口是本机 llama.cpp 定的）。"""
    raw = os.environ.get("AI_ROUTER_LOCAL_QWEN", "127.0.0.1:8080")
    host, _, port = raw.rpartition(":")
    try:
        return (host or "127.0.0.1"), int(port or 8080)
    except ValueError:
        return "127.0.0.1", 8080


@dataclass
class Route:
    pool: str
    upstream_model: str
    notes: list[str] = field(default_factory=list)
    entrance: str = ""
    base_url: str = ""


def pool_name(pool: str) -> str:
    spec = plans.POOLS.get(pool) or {}
    return str(spec.get("名称") or pool)


def pool_base(pool: str) -> str:
    if pool == "local-qwen":
        host, port = local_address()
        return f"http://{host}:{port}/v1"
    return str((plans.POOLS.get(pool) or {}).get("接口") or "")


def pool_key_name(pool: str) -> str:
    return str((plans.POOLS.get(pool) or {}).get("密钥变量") or "")


def pool_candidates(pool: str) -> list[str]:
    spec = plans.POOLS.get(pool) or {}
    candidates = list(spec.get("候选") or [])
    if pool == "opencode":
        candidates = []
    return candidates


def all_pools() -> tuple[str, ...]:
    """所有池：自动兜底的在前，只点名才走的在后。"""
    return tuple(plans.POOL_ORDER) + tuple(plans.POOL_NAMED_ONLY)


def qoder_bridge_state() -> tuple[bool, str]:
    """Qoder 客户端窗口桥的状态：桥在不在、客户端登录了没有。"""
    import urllib.request

    from . import qoder_bridge

    host, port = qoder_bridge.address()
    # 用 ASCII 路径：中文路径过不了 http.client 的 ascii 编码（会抛 UnicodeEncodeError）。
    url = "http://%s:%d/health" % (host, port)
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - 桥没起不是异常，是状态
        return False, "窗口桥没起（%s:%d）" % (host, port)
    ready = bool(data.get("就绪"))
    return ready, str(data.get("说明") or ("已就绪" if ready else "还没就绪"))


def map_model(pool: str, model: str) -> str | None:
    """客户端点的模型，这一池能不能接；能接就给出该池真正要发的模型名。"""
    spec = plans.POOLS.get(pool) or {}
    models = spec.get("模型") or {}
    equivalent = spec.get("等价模型") or {}
    if model in models:
        return model
    if pool == "opencode" and model in plans.CAP_GO:
        return model
    if model in equivalent:
        return str(equivalent[model])
    return None


def local_up() -> bool:
    try:
        with socket.create_connection(local_address(), timeout=PROBE_TIMEOUT):
            return True
    except OSError:
        return False


def _pool_remaining(channel: str, pool_name_filter: str) -> float | None:
    return store.pool_remaining_by_name(channel, pool_name_filter)


def go_plan_remaining() -> float | None:
    """Go 的按月总额度池剩余。没录过就返回 None（不拿它当闸门，只按每模型封顶算）。"""
    return store.pool_remaining_by_name("opencode", GO_PLAN_POOL)


def go_balance_remaining() -> float | None:
    """Go 的超额按量余额池剩余。没录过就返回 None（没有这个池就当没有余额可用）。"""
    return store.pool_remaining_by_name("opencode", GO_BALANCE_POOL)


def go_billing_mode() -> str:
    """Go 现在按哪一池计费。返回池名；返回空串＝两池都空了，Go 接不了。"""
    return store.go_billing_mode()


def go_model_block(model: str) -> str:
    """这个模型现在为什么接不了；返回空串＝能接。"""
    if go_billing_mode() == GO_BALANCE_POOL:
        # 走的是充值余额：上游按量价计费，不吃订阅的每模型封顶与三层窗口。
        # 这时唯一的上限是余额本身，由 pool_ready 那一关守。
        return ""
    cap = plans.cap_for(model)
    if cap is None:
        return ""
    used = store.spend_by_model(store.month_key()).get(model, 0.0)
    if cap > 0 and used / cap >= router.SOFT_STOP:
        return f"本月已用 {used:.2f} 美元、封顶 {cap:.0f} 美元"
    five_cap = cap * router.WINDOW_5H_RATIO
    if five_cap > 0:
        ratio = router.spend_in_window(model, 5) / five_cap
        if ratio >= router.SOFT_STOP:
            return f"5 小时窗口已用掉 {ratio:.0%}"
    week_cap = cap * router.WINDOW_WEEK_RATIO
    if week_cap > 0:
        ratio = router.spend_in_window(model, 24 * 7) / week_cap
        if ratio >= router.SOFT_STOP:
            return f"一周窗口已用掉 {ratio:.0%}"
    return ""


def pool_ready(pool: str) -> tuple[bool, str]:
    """这一池现在能不能接活；返回（能不能，说明）。"""
    key_name = pool_key_name(pool)
    if key_name and not store.env_value(key_name):
        return False, f"环境变量 {key_name} 没设"
    if pool == "local-qwen":
        host, port = local_address()
        if not local_up():
            return False, f"{host}:{port} 上没服务"
        return True, "在跑"
    if pool == "bailian":
        remaining = _pool_remaining("bailian", "月额度")
        if remaining is not None and remaining <= 0:
            return False, "月额度 Credits 已用尽"
        return True, "有额度"
    if pool == "opencode":
        mode = go_billing_mode()
        if mode == GO_BALANCE_POOL:
            balance = go_balance_remaining() or 0.0
            return True, f"{GO_PLAN_POOL}已用尽，走{GO_BALANCE_POOL}（剩 {balance:.2f} 美元）"
        if not mode:
            return False, f"{GO_PLAN_POOL}已用尽，{GO_BALANCE_POOL}也没余额了"
        return True, "还有额度"
    if pool == "qoder-window":
        return qoder_bridge_state()
    return False, "不知道这个池"


def _go_candidates(task: str, context_tokens: int) -> list[str]:
    candidates = list(plans.TASK_CANDIDATES.get(task, plans.TASK_CANDIDATES["短问"]))
    if context_tokens > 120_000:
        candidates = [m for m in candidates if m not in plans.BIG_CONTEXT_BANNED]
    return [m for m in candidates if m not in plans.TRAIN_ON_REQUEST]


_LAST_NOTES: list[str] = []


def last_notes() -> list[str]:
    return list(_LAST_NOTES)


def _native_pool(model: str) -> str | None:
    """这个模型是哪一池原生就有的（模型名一样，不用换名）。"""
    for pool in all_pools():
        spec = plans.POOLS.get(pool) or {}
        if model in (spec.get("模型") or {}):
            return pool
        if pool == "opencode" and model in plans.CAP_GO:
            return pool
    return None


def _go_in_balance_mode() -> bool:
    """Go 现在是不是按「超额按量余额」计费。

    订阅内额度用尽后上游改走充值余额，这时 Go 不再是订阅价，而是按量价；
    百炼／Token Plan 那池的 Credits 还躺着，就该先用它，别把余额烧光。
    """
    return store.go_billing_mode() == GO_BALANCE_POOL


def _pool_order_for(model: str) -> list[str]:
    """点名模型时的池顺序：原生那一池先走，再按兜底顺序往下。

    Go 走充值余额时顺序换掉：本地 → 百炼／Token Plan → Go。
    原生池优先这条只在同档里保留（本地永远第一，Token Plan 次之）。
    只点名才走的池（Qoder 客户端窗口）不参与自动兜底顺序，只在它就是原生池时排在最前。
    """
    native = _native_pool(model)
    if native in plans.POOL_NAMED_ONLY:
        order = [native]
        order += [p for p in plans.POOL_ORDER]
        return order
    if _go_in_balance_mode():
        prefer = {"local-qwen": 0, "bailian": 1, "opencode": 2}
        return sorted(plans.POOL_ORDER,
                      key=lambda pool: (prefer[pool], 0 if pool == native else 1))
    order = [p for p in plans.POOL_ORDER if p == native]
    order += [p for p in plans.POOL_ORDER if p != native]
    return order


def choose(requested: str, context_tokens: int = 40_000, task: str = "改码") -> Route | None:
    """定这条路：走哪个池、哪个模型。三个池都接不了就返回 None。"""
    global _LAST_NOTES
    notes: list[str] = []
    wanted = (requested or "").strip()
    auto = wanted in ("", "auto", "管家", "auto-router")

    if not auto:
        for pool in _pool_order_for(wanted):
            mapped = map_model(pool, wanted)
            if mapped is None:
                continue
            ok, why = pool_ready(pool)
            if not ok:
                notes.append(f"{pool_name(pool)}接不了：{why}")
                continue
            if pool == "opencode":
                blocked = go_model_block(mapped)
                if blocked:
                    notes.append(f"OpenCode Go 的 {mapped} 接不了：{blocked}")
                    continue
            notes.append(f"客户端点了 {wanted}，走{pool_name(pool)}的 {mapped}")
            _LAST_NOTES = notes
            return Route(pool=pool, upstream_model=mapped, notes=notes,
                         entrance=entrance_of(pool), base_url=pool_base(pool))
        notes.append(f"点名的 {wanted} 现在没有池能接，改按自动选")

    go_candidates = _go_candidates(task, context_tokens)
    deferred_go: list[str] = []
    for model in go_candidates:
        if _go_in_balance_mode():
            # Go 正在花充值余额：先把 Token Plan 用掉，Go 的活留到按月额度回来再说。
            notes.append(f"Go 在走{GO_BALANCE_POOL}，先走百炼／Token Plan")
            deferred_go = list(go_candidates)
            break
        blocked = go_model_block(model)
        if blocked:
            notes.append(f"OpenCode Go 的 {model} 接不了：{blocked}")
            continue
        ok, why = pool_ready("opencode")
        if not ok:
            notes.append(f"OpenCode Go 接不了：{why}")
            break
        notes.append(f"走 OpenCode Go 的 {model}")
        _LAST_NOTES = notes
        return Route(pool="opencode", upstream_model=model, notes=notes,
                     entrance="Go", base_url=pool_base("opencode"))

    for pool in plans.POOL_ORDER:
        if pool == "opencode":
            continue
        ok, why = pool_ready(pool)
        if not ok:
            notes.append(f"{pool_name(pool)}接不了：{why}")
            continue
        candidates = pool_candidates(pool)
        if not candidates:
            continue
        notes.append(f"兜底走{pool_name(pool)}的 {candidates[0]}")
        _LAST_NOTES = notes
        return Route(pool=pool, upstream_model=candidates[0], notes=notes,
                     entrance=entrance_of(pool), base_url=pool_base(pool))

    # 百炼／Token Plan 也接不了时，才轮到 Go——宁可烧余额，也不能让这条调用彻底断掉。
    for model in deferred_go:
        ok, why = pool_ready("opencode")
        if not ok:
            notes.append(f"OpenCode Go 接不了：{why}")
            continue
        notes.append(f"前面几池都接不了，改走 OpenCode Go 的 {model}")
        _LAST_NOTES = notes
        return Route(pool="opencode", upstream_model=model, notes=notes,
                     entrance="Go", base_url=pool_base("opencode"))

    _LAST_NOTES = notes
    return None


def entrance_of(pool: str) -> str:
    if pool == "bailian":
        return "Token Plan"
    if pool == "opencode":
        return "Go"
    if pool == "qoder-window":
        return "Qoder 窗口"
    return pool_name(pool)


def state() -> list[dict]:
    """面板用：各个池现在各是什么状态。"""
    rows = []
    for pool in all_pools():
        ok, why = pool_ready(pool)
        rows.append({"池": pool_name(pool), "可用": ok, "说明": why,
                     "接口": pool_base(pool), "密钥变量": pool_key_name(pool)})
    return rows


def stamp() -> float:
    return time.time()
