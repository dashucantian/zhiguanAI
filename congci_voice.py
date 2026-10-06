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
    """能说则说；不能说，就如实落为文字。

    后端顺序〔2026-10-06 真机一听验收实测修订〕：默认 **首选 SAPI/PowerShell**、
    pyttsx3 降为备选、末位打印。缘起：本机实测 pyttsx3 复用同一引擎时**仅首句
    真播出**（4.0s→0.2s→0.1s，后续 runAndWait 立即返回＝静默；每句新引擎更差，
    全 0.1s）；而 PowerShell SAPI 逐句可靠（3.9s/6.5s/5.5s，逐句完整播出）。
    换机器/换版本可能相反，故两条后端都保留（`prefer="pyttsx3"` 可切回）。"""

    def __init__(self, enabled: bool = True, rate: int = 170, prefer: str = "sapi"):
        self.backend = "print"
        self.engine = None
        self._err = None
        self.rate = rate
        self.voice_name = None
        self._tts_busy = threading.Event()   # 批 C3：单飞标记（忙时丢弃）
        if enabled:
            if prefer == "sapi":
                # 首选 SAPI（PowerShell）：零依赖、逐句可靠（真机实测）
                self.backend = "powershell"
                self._err = "prefer=sapi；pyttsx3 作备选（真机实测其复用引擎仅首句有效）"
            else:
                if self._ensure_pyttsx3():
                    self.backend = "pyttsx3"
                else:
                    self.backend = "powershell"
                    self._err = self._err or "pyttsx3 初始化失败，转 SAPI"

    def _ensure_pyttsx3(self) -> bool:
        """惰性初始化 pyttsx3（备选后端；失败不抛，返回 False）。"""
        if self.engine is not None:
            return True
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty("rate", self.rate)
            self.voice_name = self._select_zh_pyttsx3(self.engine)
            return True
        except Exception as e:
            self._err = repr(e)
            self.engine = None
            return False

    @staticmethod
    def _select_zh_pyttsx3(engine):
        """优先选中文音色（真机一听验收 2026-10-06：不显式选可能落到英文声，
        中文句会被读成怪音；本机实测默认即 Huihui zh-CN，但不可依赖默认）。
        找不到中文音色则留默认，返回 None。"""
        try:
            for v in engine.getProperty("voices") or []:
                blob = " ".join([str(getattr(v, "id", "")),
                                 str(getattr(v, "name", "")),
                                 " ".join(str(x) for x in
                                          (getattr(v, "languages", None) or []))])
                if any(k in blob.lower() for k in
                       ("zh", "chinese", "huihui", "kangkang", "yaoyao")):
                    engine.setProperty("voice", v.id)
                    return getattr(v, "name", None) or str(v.id)
        except Exception:
            pass
        return None

    def _order(self):
        """弃权链尝试顺序（据当前后端）：SAPI 首选则 powershell→pyttsx3→print；
        pyttsx3 首选则反之；已落打印则只打印。降级后顺序黏住（不回升）。"""
        if self.backend == "powershell":
            return ["powershell", "pyttsx3", "print"]
        if self.backend == "pyttsx3":
            return ["pyttsx3", "powershell", "print"]
        return ["print"]

    def speak(self, text: str) -> str:
        for ch in self._order():
            if ch == "powershell":
                try:
                    self._speak_powershell(text)
                    self.backend = "powershell"
                    return "powershell"
                except Exception as e:
                    self._err = repr(e)
                    continue
            if ch == "pyttsx3":
                if not self._ensure_pyttsx3():
                    continue
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                    self.backend = "pyttsx3"
                    return "pyttsx3"
                except Exception as e:
                    self._err = repr(e)
                    self.engine = None
                    continue
            if ch == "print":
                print("[从此] " + text)
                self.backend = "print"
                return "print"
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
        """SAPI5 兜底：**显式选中文音色**（本机实测已装 `Microsoft Huihui
        Desktop` zh-CN；不选则可能落英文声）。无中文音色时用默认声，
        仍然发声（不静默失败）。"""
        script = ("Add-Type -AssemblyName System.Speech;"
                  "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                  "$zh = $s.GetInstalledVoices() | Where-Object { "
                  "$_.Enabled -and $_.VoiceInfo.Culture.Name -like 'zh*' } "
                  "| Select-Object -First 1;"
                  "if ($zh) { $s.SelectVoice($zh.VoiceInfo.Name) };"
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
    # 管线 status（queued/committed/failed/duplicate/abstained，方案稿 v2 §2.4）
    # → 声带五态名（brain_*，§四）的**单一映射点**。2026-10-06 端到端自验实捉：
    # 两套词汇未接合时声带对每个管线事件都回「未知事件」——映射收在此处。
    STATUS_ALIASES = {"queued": "brain_queued", "committed": "brain_committed",
                      "failed": "brain_failed", "duplicate": "brain_duplicate",
                      "abstained": "brain_abstained"}

    @staticmethod
    def voice_state_of(status: str) -> str:
        """管线 status → 声带五态名（data_saved 原样透传）。"""
        s = str(status or "")
        return CongciVoice.STATUS_ALIASES.get(s, s)

    @staticmethod
    def _voice_tag(session_key: str) -> str:
        """句末会话标注〔2026-10-06 真机一听三次修订定稿〕：**只在会话号是可读
        Zen-ID 时念出**（如 ZEN-20261006-P001-S99，能指认是哪一坐）；内容 hash
        （64 位十六进制）与暂存名（local_*）**一律不念**——实测原样念需 7–10 秒
        且全是同音字符/无义串，听感差；完整 key 仍随 SSE 上屏、事件流与档案。"""
        sk = str(session_key or "").strip()
        if sk.startswith("ZEN-"):
            return "（%s）" % sk
        return ""

    @staticmethod
    def voice_cue(event: dict) -> str:
        """声带五态句式（判语011：同输入同句）。
        event.status ∈ {data_saved, brain_queued, brain_committed,
        brain_failed, brain_duplicate, brain_abstained}；亦接受管线原名
        queued/committed/failed/duplicate/abstained（经 voice_state_of 映射）。
        session_key 可选项附于句末（**仅可读 Zen-ID 念出**，见 _voice_tag；空则省略）。"""
        ev = event or {}
        st = CongciVoice.voice_state_of(ev.get("status") or ev.get("type")
                                        or "unknown")
        tag = CongciVoice._voice_tag(ev.get("session_key"))
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
        zen = "ZEN-20261006-P001-S99"
        for st in five:
            a = CongciVoice.voice_cue({"status": st, "session_key": zen})
            b = CongciVoice.voice_cue({"status": st, "session_key": zen})
            assert a == b, f"五态句式不确定：{st}"
            assert zen in a, f"Zen-ID 应念出：{st}"
        assert CongciVoice.voice_cue({"status": "brain_queued"}) != \
            CongciVoice.voice_cue({"status": "brain_committed"}), "句式混淆"
        assert "未入脑" in CongciVoice.voice_cue({"status": "brain_abstained"})
        assert "未知事件" in CongciVoice.voice_cue({"status": "weird"})
        # ── 批 C3 真机一听修订：hash/暂存名不念、Zen-ID 念、默认 SAPI 首选 ──
        h64 = "c6ed561d" + "b" * 56
        s_hash = CongciVoice.voice_cue({"status": "brain_committed",
                                        "session_key": h64})
        assert h64[:8] not in s_hash and "（" not in s_hash, \
            "hash 不应念出（真机一听：原样念需 ~10 秒且无义）"
        s_local = CongciVoice.voice_cue({"status": "data_saved",
                                         "session_key": "local_20261006_034637"})
        assert s_local == "这一坐的数据已存好。", f"暂存名不应念：{s_local}"
        assert zen in CongciVoice.voice_cue({"status": "brain_committed",
                                             "session_key": zen}), "Zen-ID 应念"
        assert CongciVoice(enabled=True).backend == "powershell", \
            "默认应首选 SAPI（真机实测 pyttsx3 复用引擎仅首句有效）"
        # ── 批 C3：单飞通道（print 后端）──
        vp = CongciVoice(enabled=False)          # 强制 print 后端
        assert vp.backend == "print"
        assert vp.say_async("测试") == "print"
        assert CongciVoice.voice_cue({"status": "data_saved"}) == "这一坐的数据已存好。"
        print("[voice selftest OK] deterministic=True five-state=OK single-flight=OK "
              "sapi-first=OK tag-zenid-only=OK")
        sys.exit(0)
    sys.exit(0)
