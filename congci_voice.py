#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
congci_voice.py — 从此的声带：语义反馈层 v0
=============================================

裁定（2026-10-05，项目所有者）：从此现在就是一个机器人（模型＋反馈已成）；
本机即其身体终端；加声音＋语义层——反馈从条件反馈升级为语义反馈：
不只对脑波形成环境性反馈，还能语义反馈。

纪律：
  · 语义只组织观察量（动作/节拍/音量/残差/步数/命中率），不评判人（镜子非训练器）；
  · 句式为纯函数：同输入同句（判语011）；
  · 声带缺席 → 逐级弃权（pyttsx3 → SAPI/PowerShell → 打印），弃权是一等值。

批 C3（2026-10-06·金口#3 语音开启/#4 声带上屏，方案稿 v2 §四）：
  · `voice_cue(event)` 服务端单点五态句式（纯函数）：data_saved／brain_queued／
    brain_committed／brain_failed／brain_duplicate（＋brain_abstained），
    与 L1 四态对齐——开始成功与保存成功不再混称「学习成功」；
  · TTS 独立单飞线程：忙时丢弃（不排队堆积），失败沿弃权链降级；
    打印层＝开发默认（语音验收须法师在场，金口#3）；
  · 上屏＝SSE 事件由 console_server 发布（本模块只产句子与发声，不碰 SSE）。

自测：python congci_voice.py --selftest
"""

from __future__ import annotations

import base64
import subprocess
import threading


class CongciVoice:
    """能说则说；不能说，就如实落为文字。"""

    def __init__(self, enabled: bool = True, rate: int = 170):
        self.backend = "print"
        self.engine = None
        self._err = None
        self._tts_busy = threading.Event()   # 批 C3：单飞标记（忙时丢弃）
        if enabled:
            try:
                import pyttsx3
                self.engine = pyttsx3.init()
                self.engine.setProperty("rate", rate)
                self.backend = "pyttsx3"
            except Exception as e:
                self._err = repr(e)
                self.backend = "powershell"    # SAPI 零依赖兜底

    def speak(self, text: str) -> str:
        if self.backend == "pyttsx3" and self.engine is not None:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
                return "pyttsx3"
            except Exception:
                self.engine = None
                self.backend = "powershell"
        if self.backend == "powershell":
            try:
                self._speak_powershell(text)
                return "powershell"
            except Exception:
                self.backend = "print"
        print("[从此] " + text)
        return "print"

    def say_async(self, text: str) -> str:
        """批 C3 单飞：音频可用且不忙 → 独立线程发声（忙时丢弃不堆积）；
        否则落打印层（开发默认，金口#3）。返回实际通道：tts-async/
        dropped-print／print。句子确定性由 voice_cue 保证，此处只涉通道。"""
        if self.backend != "print" and not self._tts_busy.is_set():
            self._tts_busy.set()

            def _run():
                try:
                    self.speak(text)          # 内部弃权链；失败自然降级
                finally:
                    self._tts_busy.clear()
            threading.Thread(target=_run, daemon=True,
                             name="congci-voice").start()
            return "tts-async"
        print("[从此] " + text)               # 忙时丢弃音频或后端即打印 → 落打印
        return "dropped-print" if self.backend != "print" else "print"

    @staticmethod
    def _speak_powershell(text: str) -> None:
        script = ("Add-Type -AssemblyName System.Speech;"
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                  "$s.Speak('%s')" % text.replace("'", "''"))
        b64 = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        subprocess.run(["powershell", "-NoProfile", "-EncodedCommand", b64],
                       check=True)

    # ── 确定性句式（纯函数）────────────────────────────────────────
    @staticmethod
    def narrate_action(action: int, beat: float, volume: float) -> str:
        v = {0: "降拍，向θ沉一档", 1: "持守", 2: "升拍，向α提一档", 3: "撤一档支持"}
        return "%s，节拍%.1f赫兹，音量%.2f。" % (v[int(action) % 4], beat, volume)

    @staticmethod
    def narrate_settlement(residual: float, steps: int) -> str:
        return "沉降%d步，残差%.1e。" % (steps, residual)

    @staticmethod
    def narrate_dream(before: float, after: float) -> str:
        return "复讲完毕。未学句式命中率，从%.0f%%到%.0f%%。" % (before * 100, after * 100)

    # ── 批 C3：服务端单点五态句式（纯函数）────────────────────────
    @staticmethod
    def voice_cue(event: dict) -> str:
        """声带五态句式（判语011：同输入同句）。
        event.status ∈ {data_saved, brain_queued, brain_committed,
        brain_failed, brain_duplicate, brain_abstained}；session_key 可选项
        附于句末（无则省略）。"""
        ev = event or {}
        st = str(ev.get("status") or ev.get("type") or "unknown")
        sk = str(ev.get("session_key") or "").strip()
        tag = "（%s）" % sk if sk else ""
        table = {
            "data_saved": "这一坐的数据已存好%s。" % tag,
            "brain_queued": "从此已收到这一坐，正在排队收口入脑%s。" % tag,
            "brain_committed": "这一坐已收口入脑，从此脑长一格%s。" % tag,
            "brain_failed": "这一坐收口失败，已如实记录，可重试%s。" % tag,
            "brain_duplicate": "这一坐此前已入脑，不重复学习%s。" % tag,
            "brain_abstained": "这一坐弃权，未入脑%s。" % tag,
        }
        return table.get(st, "（从此声带：未知事件 %s%s）" % (st, tag))


# ── 批 C3：懒单例（首次发声才初始化 TTS，不拖慢 console_server 导入）────
_VOICE = None
_VOICE_LOCK = threading.Lock()


def get_voice(enabled: bool = True) -> CongciVoice:
    """进程级单例。首次调用才 pyttsx3.init()（金口#3：默认可开；
    失败沿弃权链降级，不抛）。"""
    global _VOICE
    if _VOICE is None:
        with _VOICE_LOCK:
            if _VOICE is None:
                _VOICE = CongciVoice(enabled=enabled)
    return _VOICE


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        v1 = CongciVoice.narrate_action(2, 9.5, 0.25)
        v2 = CongciVoice.narrate_action(2, 9.5, 0.25)
        assert v1 == v2, "句式不確定"
        assert "升拍" in v1 and "9.5" in v1
        d = CongciVoice.narrate_dream(0.300, 0.975)
        assert d == "复讲完毕。未学句式命中率，从30%到98%。", d
        s = CongciVoice.narrate_settlement(1.9e-6, 32)
        assert "32步" in s
        # ── 批 C3：五态句式确定性 ──
        five = {"data_saved", "brain_queued", "brain_committed",
                "brain_failed", "brain_duplicate", "brain_abstained"}
        for st in five:
            a = CongciVoice.voice_cue({"status": st, "session_key": "SK"})
            b = CongciVoice.voice_cue({"status": st, "session_key": "SK"})
            assert a == b, f"五态句式不确定：{st}"
            assert "SK" in a, f"句末缺会话标注：{st}"
        assert CongciVoice.voice_cue({"status": "brain_queued"}) != \
            CongciVoice.voice_cue({"status": "brain_committed"}), "句式混淆"
        assert "未入脑" in CongciVoice.voice_cue({"status": "brain_abstained"})
        assert "未知事件" in CongciVoice.voice_cue({"status": "weird"})
        # ── 批 C3：单飞通道（print 后端）──
        vp = CongciVoice(enabled=False)          # 强制 print 后端
        assert vp.backend == "print"
        assert vp.say_async("测试") == "print"
        assert CongciVoice.voice_cue({"status": "data_saved"}) == "这一坐的数据已存好。"
        print("[voice selftest OK] deterministic=True five-state=OK single-flight=OK")
        sys.exit(0)
    sys.exit(0)
