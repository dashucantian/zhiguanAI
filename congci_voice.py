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

自测：python congci_voice.py --selftest
"""

from __future__ import annotations

import base64
import subprocess


class CongciVoice:
    """能说则说；不能说，就如实落为文字。"""

    def __init__(self, enabled: bool = True, rate: int = 170):
        self.backend = "print"
        self.engine = None
        self._err = None
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
        print("[voice selftest OK] deterministic=True")
        sys.exit(0)
    sys.exit(0)
