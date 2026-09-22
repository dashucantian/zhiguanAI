r"""
转写录音.py —— 用 faster-whisper 把录音转成带时间戳的文本（完全离线，本机 CPU）

用法：
    python 转写录音.py "C:\路径\录音.mp3"
    python 转写录音.py "录音.mp3" --model medium --out "D:\输出目录"
    python 转写录音.py "录音.mp3" --test        # 只转前 60 秒，快速验证链路

模型档位（准确率和耗时权衡，本机无独显走 CPU）：
    tiny / base / small / medium / large-v3
    默认 medium：中文开示准确率与耗时较平衡，CPU 约 1~2 小时/90 分钟音频。

产物（写到 --out，默认 项目内 03_课程内容\开示转写）：
    <音频名>.md    带时间戳的 Markdown，便于校对
    <音频名>.txt   纯文本，便于直接取用
    <音频名>.srt   字幕，便于回听定位
"""
import argparse
import datetime
import os
import sys
import time

# 国内直连 huggingface 常失败，默认走镜像（已在环境变量设置则不覆盖）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(PROJECT_ROOT, "03_课程内容", "开示转写")

# 给模型的术语提示，提升专有名词（法义/丛林术语）准确率
PROMPT = (
    "以下是武陵禅寺宗国法师的开示，使用简体中文与佛教禅修术语，"
    "如：大圆满、前行、加行、止观、奢摩他、毗钵舍那、皈依、发心、忏悔、"
    "随喜、回向、上师、三宝、轮回、空性、慈悲、正念、觉知、呼吸、打坐、"
    "禅修、功课、经行、闭关、护持、道场、监院、维那、依止、结夏安居。"
)


def fmt_hms(sec):
    sec = max(0, int(sec))
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def fmt_srt_ts(sec):
    ms = int(round(sec * 1000))
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, (ms % 3600000) // 60000, (ms % 60000) // 1000, ms % 1000)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="faster-whisper 离线转写")
    ap.add_argument("audio", help="音频文件完整路径（建议用英文引号包住）")
    ap.add_argument("--model", default="medium",
                    help="tiny/base/small/medium/large-v3，默认 medium")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出目录")
    ap.add_argument("--language", default="zh", help="语言，默认 zh")
    ap.add_argument("--test", action="store_true", help="只转前 60 秒，验证链路")
    args = ap.parse_args()

    audio = os.path.abspath(args.audio)
    if not os.path.isfile(audio):
        print("[错误] 找不到音频文件：%s" % audio)
        print("请确认路径与文件名完全一致（注意不要多打空格）。")
        sys.exit(2)

    os.makedirs(args.out, exist_ok=True)
    base = os.path.splitext(os.path.basename(audio))[0]

    print("=" * 60)
    print("源文件   ：%s" % audio)
    print("模型     ：%s（首次运行会自动下载，走镜像 %s）" % (args.model, os.environ.get("HF_ENDPOINT")))
    print("输出目录 ：%s" % args.out)
    print("模式     ：%s" % ("测试（仅前 60 秒）" if args.test else "全量"))
    print("=" * 60)

    t_load0 = time.time()
    from faster_whisper import WhisperModel
    print("[%s] 正在加载模型（若需下载请耐心等待）……" % datetime.datetime.now().strftime("%H:%M:%S"))
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    print("[%s] 模型就绪，用时 %.1f 秒，开始转写……" % (
        datetime.datetime.now().strftime("%H:%M:%S"), time.time() - t_load0))

    kwargs = dict(language=args.language, beam_size=5, task="transcribe",
                  vad_filter=True, vad_parameters=dict(min_silence_duration_ms=500),
                  initial_prompt=PROMPT)
    if args.test:
        # 只转写第 5~6 分钟这段（避开开头静音），用于快速验证质量
        kwargs["clip_timestamps"] = "300,360"
    segments, info = model.transcribe(audio, **kwargs)
    total = info.duration or 0
    print("音频总时长约 %s，检测语言=%s(置信度 %.2f)" % (fmt_hms(total), info.language, info.language_probability))

    md_lines, txt_lines, srt_blocks = [], [], []
    idx = 0
    t0 = time.time()
    last_report = 0
    for seg in segments:
        idx += 1
        text = seg.text.strip()
        md_lines.append("- `[%s]` %s" % (fmt_hms(seg.start), text))
        txt_lines.append(text)
        srt_blocks.append("%d\n%s --> %s\n%s\n" % (
            idx, fmt_srt_ts(seg.start), fmt_srt_ts(seg.end), text))
        if idx - last_report >= 50:
            last_report = idx
            elapsed = time.time() - t0
            pct = (seg.end / total * 100) if total else 0
            print("  ...已转写 %d 段，进度约 %.1f%%（%s / %s），用时 %s" % (
                idx, pct, fmt_hms(seg.end), fmt_hms(total), fmt_hms(elapsed)))

    elapsed = time.time() - t0
    header = [
        "# %s（转写稿）" % base, "",
        "> 源录音：%s" % os.path.basename(audio),
        "> 转写模型：faster-whisper %s（本机离线）｜时长：%s｜段数：%d｜转写用时：%s" % (
            args.model, fmt_hms(total), idx, fmt_hms(elapsed)),
        "> 生成时间：%s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "> ⚠️ 机器转写，法义术语与数字须人工校对后方可引用。", "",
    ]
    md_path = os.path.join(args.out, base + ".md")
    txt_path = os.path.join(args.out, base + ".txt")
    srt_path = os.path.join(args.out, base + ".srt")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(header + md_lines) + "\n")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(txt_lines) + "\n")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_blocks))

    print("=" * 60)
    print("完成！共 %d 段，用时 %s" % (idx, fmt_hms(elapsed)))
    print("  Markdown：%s" % md_path)
    print("  纯文本  ：%s" % txt_path)
    print("  字幕    ：%s" % srt_path)


if __name__ == "__main__":
    main()
