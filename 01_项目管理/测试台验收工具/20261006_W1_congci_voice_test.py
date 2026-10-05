#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
20261006_W1_congci_voice_test.py — 批 C3 轻量自测：声带五态＋单飞＋上屏接线
==========================================================================

施工正本《20261005_驾驶舱×从此接入方案稿_v2.md》§四（L3）＋金口#3/#4：
  五态句式（voice_cue 纯函数，判语011 确定性）／data_saved 与「学习成功」
  不混称／TTS 独立单飞线程（忙时丢弃不堆积）／三级弃权链（pyttsx3→SAPI→
  打印，打印层为开发默认，语音验收须法师在场）／上屏 SSE 事件（congci_said）
  经管线 UI 回调接线（附属物纪律：回调失败不影响管线）。

运行环境：runtime python（无 cadence 依赖；管线回调测试复用 C2 夹具索引）。

测试件头（契约 v0.2 纪律）：运行时打印源码 sha16＋被测函数＋时刻。
退出码 0=全过。
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, r"D:\Project\zhiguanAI")

PASS = 0


def ok(name):
    global PASS
    PASS += 1
    print(f"[ok] {name}")


def sha16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main() -> int:
    srcs = {p: sha16(os.path.join(r"D:\Project\zhiguanAI", p))
            for p in ("congci_voice.py", "congci_pipeline.py",
                      "console_server.py")}
    print(f"[header] 2026-10-06 {time.strftime('%H:%M:%S')} src_sha16={srcs}")

    from congci_voice import CongciVoice, get_voice
    import congci_pipeline as cp

    try:
        # ── 1. voice_cue 五态句式确定性（纯函数）────────────────────
        five = {"data_saved", "brain_queued", "brain_committed",
                "brain_failed", "brain_duplicate", "brain_abstained"}
        for st in five:
            a = CongciVoice.voice_cue({"status": st, "session_key": "SK-1"})
            b = CongciVoice.voice_cue({"status": st, "session_key": "SK-1"})
            assert a == b, f"五态句式不确定：{st}"
            assert "SK-1" in a, f"句末缺会话标注：{st}"
        assert CongciVoice.voice_cue({"status": "brain_queued"}) != \
            CongciVoice.voice_cue({"status": "brain_committed"}), "queued/committed 句式混淆"
        assert "已存好" in CongciVoice.voice_cue({"status": "data_saved"})
        assert "入脑" in CongciVoice.voice_cue({"status": "brain_committed"})
        assert "可重试" in CongciVoice.voice_cue({"status": "brain_failed"})
        assert "不重复学习" in CongciVoice.voice_cue({"status": "brain_duplicate"})
        assert "未入脑" in CongciVoice.voice_cue({"status": "brain_abstained"})
        assert "未知事件" in CongciVoice.voice_cue({"status": "weird"})
        # data_saved 不混称「学习成功」
        assert "学习成功" not in CongciVoice.voice_cue({"status": "data_saved"})
        ok("五态句式：确定性＋不混称＋未知事件兜底")

        # ── 2. say_async 单飞通道 ────────────────────────────────────
        vp = CongciVoice(enabled=False)                 # 强制 print 后端
        assert vp.backend == "print"
        assert vp.say_async("测试句") == "print", "print 后端应直落打印层"
        # 忙时丢弃：伪造音频后端＋busy 标记 → dropped-print（不堆积）
        va = CongciVoice(enabled=False)
        va.backend = "pyttsx3"                          # 模拟音频可用
        va._tts_busy.set()                              # 上一句未播完
        assert va.say_async("忙时句") == "dropped-print", "忙时应丢弃音频落打印"
        ok("单飞通道：print 直落／忙时丢弃（dropped-print）不堆积")

        # ── 3. 管线 UI 回调接线（附属物纪律）────────────────────────
        env = json.load(open(r"D:\Project\zhiguanAI\_analysis_tmp\_c2_env.json",
                             encoding="utf-8"))
        cp.configure(root=env["congci_root"], zen_root=env["zen_root"],
                     auto_worker=False, brain_lock_timeout=2.0)
        spy = []
        cp.set_ui_callback(lambda p: spy.append(dict(p)))
        # 复喂已 committed 的 S99 → duplicate（回调应收到 duplicate）
        r = cp.enqueue(os.path.join(env["zen_root"], "02_raw", env["sk"],
                                    "eeg_raw.npz"),
                       session_type="training", participant="P001",
                       scene="test")
        assert r["status"] == "duplicate", f"S99 应 duplicate：{r}"
        assert any(s.get("status") == "duplicate" for s in spy), \
            f"duplicate 未回调：{spy}"
        # 直调 _emit_event 覆盖全 status（committed/failed/abstained/queued）
        fake = {"session_key": "ZEN-TEST", "unit_id": "u-x",
                "source_hash16": "0" * 16, "algo_version": cp._algo_version(),
                "lineage_id": cp.LINEAGE_ID, "brain_version": 7}
        npz_probe = os.path.join(env["zen_root"], "02_raw", env["sk"],
                                 "eeg_raw.npz")
        for st in ("queued", "committed", "failed", "abstained"):
            cp._emit_event(npz_probe, st, fake, "测试")
        got = {s.get("status") for s in spy}
        assert {"queued", "committed", "failed", "abstained",
                "duplicate"} <= got, f"回调未覆盖全态：{got}"
        # 回调抛错不影响管线（附属物纪律）
        def _boom(_p):
            raise RuntimeError("callback boom")
        cp.set_ui_callback(_boom)
        cp._emit_event(npz_probe, "committed", fake, "boom-test")  # 不得抛
        cp.set_ui_callback(None)
        ok("管线回调：全态接线＋异常静默（附属物）")

        print(f"[selftest OK] {PASS} checks passed（批 C3 声带轻量自测）")
        return 0
    finally:
        cp.set_ui_callback(None)
        cp.ALGO_VERSION = None


if __name__ == "__main__":
    sys.exit(main())
