# 我方设备剖面 v1（NeuraDock 七通道）

出具：2026-10-24 00:5x（本机 `Get-Date` 现取）｜窗：`DSH·24e5b510`｜性质：**取值唯一源**（非裁定）
为什么是 `.md` 而不是 `.json`：本仓 `.gitignore:77` 全仓忽略 `*.json`，而按 R-07 不许自行 `-f` 入库。故剖面写在 md 里的 json 块中——**人可读、库可跟、脚本可解析**（`验证_口径一致_v1.py` 会抽块校验）。
用途：给解析、特征、质检三处提供单一取值；与对方公开 profile 的差异**逐条显式**，不隐去。

## 一、剖面（机器读这一段）

```json
{
  "profile_version": "1.0",
  "issued_at": "2026-10-24 00:5x +0800",
  "device": "NeuraDock EEG Workstation（七通道头环，后头 CP5–O2）",
  "owner": "止观AI · W1 工程线（DSH·24e5b510 代笔）",
  "signal": {
    "sampling_rate_hz": 250,
    "channels": ["CP5", "CP6", "PO3", "PO4", "O1", "Oz", "O2"],
    "channel_count": 7,
    "amplitude_unit": "uV",
    "sample_axis": "未验（我方 buffer 收扁平数组，列序/样本序未在代码中声明；引用前须实测一次）",
    "source": "muse2-repo/muse2-master/neuradock_receiver.py:30-31"
  },
  "tcp": {
    "default_ip": "127.0.0.1",
    "default_port": 9600,
    "start_command": "无（我方不用 start 命令，须人工在官方软件点『打开数据服务』）",
    "source": "neuradock_receiver.py:13,:54"
  },
  "quality_gates_ours": {
    "thresholds_version": "20261013",
    "min_duration_s": 30.0,
    "max_packet_loss": 0.20,
    "min_clean_ratio": 0.60,
    "noise_bg_ratio": 0.65,
    "epoch_seconds": 10.0,
    "epoch_step": 5.0,
    "channel_rules": {"flat_std_uv": 0.5, "rail_uv": 1800.0, "mains_ratio_50hz": 0.35, "rms_bad_uv": 500.0, "min_samples": 64},
    "bands_hz": {"delta": [0.5, 4.0], "theta": [4.0, 8.0], "alpha": [8.0, 12.0], "beta": [12.0, 30.0], "gamma": [30.0, 45.0]},
    "iaf_search_hz": [7.0, 13.0],
    "iaf_min_contrast": 1.3,
    "source": "qc_pipeline.py:38,:45-67"
  },
  "diff_vs_reference": [
    {"item": "alpha 频带边界", "ours": "8–12 Hz（BANDS.alpha）", "reference": "8–13 Hz（result-fields.md）", "impact": "两侧 alpha 功率与峰频不可直接互引；引用须写明带宽", "source": "qc_pipeline.py:53 vs 参考仓库/…/context/result-fields.md:30,:43"},
    {"item": "质量判据口径", "ours": "clean_ratio＋三条闸门＋通道级 ok·warn·bad·unknown", "reference": "六项阈值＋retention_rate", "impact": "两侧『质量通过』不可互相翻译，只能并列报", "source": "qc_pipeline.py:45-61 vs configs/neuradock-v1.json:20-27"},
    {"item": "包结构与样本步长", "ours": "未验（只按解析出的 7 列处理）", "reference": "总包 8 通道只用 7；每蓝牙包 5 样本", "impact": "真机含第 8 列时我方按 7 列解析会错列，首连须实测列数与列宽", "source": "configs/neuradock-v1.json:16-18；我方无对应核验记录"},
    {"item": "工频", "ours": "链路未声明（带通 1–40 Hz 压制；通道判据 mains_ratio 0.35）", "reference": "line_frequency_hz 50", "impact": "换 60 Hz 环境设备须改判据；当前仅适用 50 Hz", "source": "qc_pipeline.py:59 vs configs/neuradock-v1.json:11"},
    {"item": "启动方式", "ours": "人工点『打开数据服务』", "reference": "tcp.start_command = start", "impact": "无自动化起点，无人值守场景起不来", "source": "neuradock_receiver.py:13 vs configs/neuradock-v1.json:15"}
  ]
}
```

## 二、读法三条

1. **只声明取值，不声明有效性**：凡带「未验」字样处，引用方必须实测后再引。
2. **差异节不得为空**，且每条必须有 `source`；缺 source 视为无效差异（脚本判 FAIL）。
3. **改硬件或改阈值** ⇒ 同步改本件并重跑 `验证_口径一致_v1.py`（ML-3 段会逐项核）。

## 三、不足

- 不足：② `sample_axis` 未验：我方 buffer 收扁平数组，未在代码里声明"按通道优先还是样本优先"。**这是解析错列风险的第二处**（第一处是总包 8/7）。
- 不足：⑥ 阈值只搬了 `qc_pipeline` 的常量，**未做实测标定**（rail 1800 µV、rms 500 µV 是既有值，来源未追）。
- 不足：⑨ 差异五条里两条（包结构、启动方式）我方标「未验」而非"我方不同"——真机实测一次才知是否真差。
