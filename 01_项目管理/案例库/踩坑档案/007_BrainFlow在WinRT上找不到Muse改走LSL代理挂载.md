# 坑 007：BrainFlow 在 WinRT 上找不到 Muse 头环——改走"既有采集层 → LSL"代理挂载

> 判决日期：2026-09-07 | 状态：已定 | 影响范围：采集层／第三方设备接入（看板 D2）

## 现象（用户视角）

法师授权做"采集层验证"：装 BrainFlow，用现有 Muse 头环跑通交叉核对，为将来 NeuraDock／OpenBCI 接入统一控制台定标准。

AI 侧观察到的错误分两层：

**第一层：设备发现失败**
```
[board_logger] [info] Use Muse preset p21
[board_logger] [info] Use timeout for discovery: 6
[board_logger] [info] found 1 BLE adapter(s)
[board_logger] [error] Failed to find Muse Device
BrainFlowError: BOARD_NOT_READY_ERROR:7 unable to prepare streaming session
```
而同一时刻 bleak 能正常扫到：`name='MuseS-E8D8' addr=00:55:DA:BB:E8:D8 rssi=-43`。

**第二层（把发现超时放宽到 30 秒后）：连上了但零数据**
```
[info] Found Muse device
[info] Connected to Muse Device
[info] found control characteristic
（此后 45–75 秒 get_board_data_count() 恒为 0）
[error] failed to send command h to device
BrainFlowError: BOARD_WRITE_ERROR:4 unable to stop streaming session
```

## 根因（三个独立问题，逐个查明的过程比结论更值钱）

### 问题一：BrainFlow 的 WinRT 实现拿不到设备名（决定性）

开 trace 级文件日志（`BoardShim.set_log_file` + `set_log_level(LogLevels.LEVEL_TRACE)`）后拿到关键证据：BrainFlow 扫到 21 个设备地址，但**每一条的 `identifier` 字段都是空的**：

```
[trace] address 27:4f:8b:ae:da:89
[trace] identifier            ← 空
[trace] address 2d:e5:14:09:05:8f
[trace] identifier            ← 空
（21 条全部如此）
[error] Failed to find Muse Device
```

BrainFlow 靠**设备名**匹配 Muse，而本机 WinRT 蓝牙栈没把名字交给它。bleak 能拿到名字，BrainFlow 拿不到——这是 BrainFlow 的 WinRT 实现与本机蓝牙栈的兼容性问题，不是脚本缺陷，也不是头环故障。

### 问题二：preset 不同，p21 与 p1041 不是一回事

BrainFlow 默认给 Muse 用 `p21`（4 通道 EEG + IMU）；而本项目既有采集层用 **`p1041`**，且 09-06、09-07 两次真机采集成功的 npz 都是 p1041 出来的（`channels: ['TP9','AF7','AF8','TP10']`、`sfreq: 256.0`）。这一层即使发现问题一也未必能救回来，但它是"连上却无数据"的另一个可疑点，必须记录。

### 问题三：本项目早已修过同类症状（V1.3）

`ble_receiver.py:392-398` 的修复注释写着：对 Muse 控制特征一律用"写命令"（`wait_for_response=False`），否则"握手第一条指令即超时、**连接建立后无数据流**"——与 BrainFlow 的 `failed to send command h to device` 是同一症状。既有实现是靠 OpenMuse + bleak（内置蓝牙）或 pygatt + BLED112（外置适配器）绕过去的，两条路都已真机验证（D18 定为基线）。BrainFlow 走的是第三条路（WinRT 原生），在本机不通。

## 解法：不要让 BrainFlow 去驱动蓝牙，让它只做算法

换路子：**复用已真机验证过的既有采集层，只把它的数据出口标准化为 LSL**。

### 关键技巧：代理挂载，基线一行不改

既有层通过 `buffer.add_eeg(flat)` 投递数据（`ble_receiver.py:319`；`muse_local_server.py:310` 定义，flat list 每 5 个一组 = 1 样本 ×(4 EEG + 1 占位)）。于是用一个代理类包住 `DataBuffer`，在 `add_eeg` 里同时推 LSL：

```python
class LslBufferProxy:
    def __init__(self, inner, outlet):
        self._inner = inner; self._outlet = outlet
    def add_eeg(self, samples: list):
        self._inner.add_eeg(samples)                    # 原路：界面/保存
        ns = len(samples) // 5
        arr = np.asarray(samples[:ns*5], np.float32).reshape(ns, 5)
        eeg4 = np.ascontiguousarray(arr[:, :4])         # 丢第 5 列占位
        self._outlet.push_chunk(eeg4, ts_batch)         # 新增：LSL 出口
    def __getattr__(self, name):                        # 其余成员转发
        return getattr(self._inner, name)
```

`ble_receiver.py` / `muse_local_server.py` / `console_server.py` **一行未改**，守住 D18「连接层不再改动」与「新能力并入现有模块、不建平行入口」。

模拟器与真机采集层调用的是**同一个** `add_eeg` 接口，所以这个挂载点对两者都成立——可以先用模拟器干跑验证管道，再上真机。

### 消费者必须是独立进程

用 `multiprocessing.get_context("spawn")`（Windows 下必须 spawn）起独立子进程，由它自己 `resolve_streams()` 发现流、自己 `pull_chunk()`。同进程内存传递证明不了任何事；跨进程才证明这是"标准总线"，将来 MNE、LabRecorder、Unity、NeuraDock 工具链都能各取所需。

## 验证结果（三轮，逐轮收敛）

| 轮次 | 内容 | 结果 |
|------|------|------|
| 回环自检 | LSL 本机建流→发现→批量收发（合成数据） | 768 样本零丢失，误差 **0.000e+00** μV，间隔 3.9062 ms |
| 模拟干跑 | 既有接口 → LSL → 独立进程 | 推 15192／收 14808，推送零失败，峰值 9.99 Hz |
| 真机 22:44 | 头环 BLE → LSL → 独立进程 | 7 项通过，**时间戳非严格单调未过** |
| 真机 23:14 | 同上（修复后，法师自行运行） | **10 项全通过** |

23:14 那轮的硬指标：既有 buffer 17614 = LSL 推送 17614，推送失败 0 次，消费者实测 **256.0 Hz**（精确），时间戳中位数与最大值同为 **3.9062 ms**（=1000/256，零抖动），`ts_nonmonotonic_steps = 0`，BrainFlow 与 MNE 的 band power **逐位完全相同**。

**最有价值的一点**：真机蓝牙线程与 LSL 推送线程同时工作，零推送失败、零资源争用——这是模拟干跑无法等价证明的。

## 连带查明的三个坑（都在自己代码里，不在 BrainFlow）

### 坑 A：LSL 时间戳必须自己算，不能让 liblsl 打

`push_chunk(eeg4)` 不传时间戳时，liblsl 按**收到时刻**打戳。BLE 每包 4 样本、包间隔有抖动，于是时间戳非严格单调（22:44 真机轮暴露）。修法：Muse 是固定 256 Hz，由 `local_clock()` 起基准，之后每批严格 `+= ns/SFREQ`：

```python
step = 1.0 / SFREQ
ts_batch = np.asarray([self._next_ts + i*step for i in range(ns)], np.float64)
self._next_ts += ns * step
self._outlet.push_chunk(eeg4, ts_batch)
```

修复后真机轮 `ts_step_ms_median == ts_step_ms_max == 3.9062`，抖动彻底消除。

### 坑 B：测试编排的时序错位会被误读成"管道丢包"

消费者从 `open_stream` 起计 60 秒，而生产者要 20 秒（23:14 那轮 36.6 秒）才连上头环开始推数据 → 消费者前段空拉，60 秒到期时只覆盖到数据的前 43 秒。表面看"推 15582 收 11014"像丢了 29%。

**证伪方法**：看消费者自己窗口内的指标——`n/dur = 11014/43.19 = 255.01 Hz`、丢包 0.386%。窗口内零丢失，说明缺的是**连接期的空窗**，不是传输丢包。缺口 4568 样本 = 17.84 秒 ≈ 连接耗时 20 秒，量级吻合。

修法：消费者改为**按实际收到的数据量计窗**（收满 `duration × SFREQ` 为止），生产者多推 `ACQ_MARGIN_SEC` 秒余量。

### 坑 C：BrainFlow 的 band power 缺窗归一化，会系统性偏低 2.5 倍

（阶段 0 离线核对时查明，与采集无关但同源，一并记录。）

`DataFilter.get_psd_welch` 返回的 PSD **未做 Hann 窗功率归一化**，缺 `sum(w²)/N = 3/8` 这个因子；`get_band_power` 又用矩形求和而非梯形积分。表现：各频段比值 0.3707～0.3750，与理论值 **3/8 = 0.375** 精确吻合，而相关性高达 r≈0.9999——**"高相关 + 恒定比值"就是纯归一化常数差异的指纹**，不是算法或数据问题。

修法：乘 `8/3` 并改用梯形积分。校正后 theta／alpha／beta／gamma 比值**精确等于 1.000000**；唯 delta 残差 −1.117%，因 0.5 Hz 下边界与 0 频直流分量处理方式不同（已如实记录，未粉饰）。

将来写 NeuraDock 适配器时这个 `8/3` 必须带上，否则指标整体偏低一档，HUD 阈值与三态判定全跟着错。

### 坑 D：`stop_stream()` 抛异常会跳过 `release_session()`，头环被残留占用

初版把三步串在 `finally` 里：`stop_stream(); get_board_data(); release_session()`。真机轮 `stop_stream()` 抛 `BOARD_WRITE_ERROR`，后两步**从未执行**——会话残留占用头环，导致下一轮三种连接策略全败、头环反复"消失"。修法：三步各自 try，确保 `release_session()` 一定被执行。

## 排障顺序（可复用）

第三方采集库连不上 BLE 设备时：

1. **先分清是哪一层断的**：用 bleak 独立扫一遍。bleak 能扫到而库扫不到 → 库的蓝牙实现问题，不是设备或适配器问题。
2. **开 trace 级文件日志看它到底看见什么**。本坑的决定性证据（`identifier` 全空）只有 trace 级才打出来，info 级只会给一句 `Failed to find Muse Device`。
3. **对照本项目已验证成功的配置**：preset、采样率、通道名。既有层用 p1041 成功过，BrainFlow 默认 p21——差异本身就是线索。
4. **"连上但零数据"优先怀疑握手/preset，不是带宽**。本项目 V1.3 修过同一症状（控制特征写响应语义）。
5. **失败路径必须保证资源释放**。`stop → get_data → release` 三步各自 try，否则残留占用会污染后续所有轮次，表现为"设备神秘消失"。
6. **判断丢包先看窗口内指标，别拿总量直接比**。生产者总量含消费者的连接期空窗，直接比会误判。
7. **换路子的判据**：若库的"驱动硬件"环节在本机不通，而本项目已有一条真机验证过的采集路径，就让库只做算法层（离线/流式计算），采集交给既有层——本坑解法即此。

## 教训

1. **库的"支持某设备"不等于"在你这台机器上支持"**。BrainFlow 官方文档列了 Muse 全系 BoardId（Muse2=38、MuseS=39、MuseAthena=67），口径还与本项目逐字一致（256 Hz、TP9/AF7/AF8/TP10），但在本机 WinRT 栈上就是发现不了。文档正确 ≠ 本机可用，必须实测。
2. **接口口径一致是天赐的便利，要主动去核**。BrainFlow 对 Muse 的通道名与既有实现完全相同，意味着将来接入连通道映射都不用写。这类"对得上"的事实要在动手前就查清，能省掉一整层胶水代码。
3. **标准总线的价值在于"多消费者各取所需"**。LSL 一旦跑通，MNE／LabRecorder／Unity／第三方设备都能以同一方式接入，不必为每种设备单独造轮子——这正是"轮子不该自己造、方向盘只能自己造"的工程落点。
4. **代理挂载是守住基线的正解**。既有连接层已被 D18 定为不可改动的基线，新增出口就走代理包住投递接口，而不是去改基线代码。
5. **测试编排的时序缺陷会伪装成系统缺陷**。消费者比生产者早起表 20 秒，看起来像丢包 29%。写并发验证时，计时起点必须对齐"数据真正开始流动"的时刻，或者干脆按数据量计窗。
6. **信号质量必须进验收门槛**。23:14 真机轮管道 10 项全绿，但数据本身是垃圾：幅值 ±1651 μV、std 209 μV、频谱峰值 **2.05 Hz**（不是 8–12 Hz alpha）、theta 功率 8944–15406 μV²（正常约 43 μV²），比 09-06 baseline 大**两三个数量级**——典型电极未接触头皮／饱和／大幅运动伪迹。传输管道的判据（样本数、采样率、时间戳、算法一致性）与信号质量无关，所以"管道全绿"和"数据可用"是两件事。既有层的 `contact_quality` 字段（09-06 那份记为 `good`）正是为此而设，将来 NeuraDock 适配器要同样接上质检闸门。**垃圾进，垃圾出。**

## 关联

- 看板 ZG-020（D2 NeuraDock 接入既有采集层）——本坑给出工程范式
- 看板 ZG-013（B6 蓝牙连接稳定性排查）
- 判语 004（OpenBCI 唯一全开源契合）——NeuraDock 开源状态已于 2026-09-07 更新：软件 MIT 已可验证、硬件仅接口级、制造文件不公开
- 项目记忆《脑电实验系统统一架构约定》（D17/D18/D19、唯一入口、单一硬件层）
- 相关文件：
  - `muse2-repo/muse2-master/crosscheck_brainflow.py`（阶段 0 离线三口径核对）
  - `muse2-repo/muse2-master/crosscheck_live_stage1.py`（阶段 1 BrainFlow 直驱，**失败**，留作证据）
  - `muse2-repo/muse2-master/crosscheck_live_stage2.py`（阶段 2 LSL 代理挂载，**通过**，含 `--sim` 干跑开关）
  - `muse2-repo/muse2-master/brainflow_dev.log`（trace 日志，`identifier` 全空的原始证据）
  - `muse2-repo/muse2-master/report/crosscheck_*.json`（各轮结果；均为指标，无 npz）
- 坑 003（蓝牙数据流静默断连）、坑 004（本机无 N 卡的算力误判）

## 隐私边界（本次执行确认）

三轮验证**未产生任何 npz**，未写入 Zen-EEG 数据工厂：代理里覆盖了 `save_on_disconnect` 为空操作（拦截已生效），消费者只落指标 JSON、不落原始波形。全程本机，未联网、未上传。

---

## English Summary

**Symptom:** BrainFlow (v5.22.2) could not drive a Muse S headband on this Windows machine. First `BOARD_NOT_READY_ERROR:7` with `Failed to find Muse Device` while bleak saw it fine (`MuseS-E8D8`, rssi −43). After raising discovery timeout 6s→30s it connected (7.41s / 2.79s, `found control characteristic`) but produced **zero samples** in 45–75s, then `failed to send command h to device` / `BOARD_WRITE_ERROR:4`.

**Root cause (three stacked):** (1) *Decisive*—trace-level file logging showed BrainFlow enumerated 21 BLE addresses but **every `identifier` field was empty**; it matches Muse by device *name*, and the local WinRT stack never handed names to it. bleak gets names, BrainFlow doesn't. (2) Preset mismatch: BrainFlow defaults to `p21`, while this project's verified working path uses **`p1041`** (both real-machine sessions on 09-06/09-07). (3) The project had already fixed this exact symptom class in V1.3 (`ble_receiver.py:392-398`): Muse control characteristics must be written with `wait_for_response=False`, else "connection established but no data stream". The working paths are OpenMuse+bleak (built-in BT) or pygatt+BLED112 (external dongle); BrainFlow uses a third path (native WinRT) that doesn't work here.

**Solution: don't let BrainFlow drive Bluetooth—let it do math only.** Reuse the already-verified acquisition layer and standardize its *output* as LSL. Key trick: a **proxy over `DataBuffer`** whose `add_eeg()` forwards to the real buffer *and* pushes to a `StreamOutlet`. `ble_receiver.py`/`muse_local_server.py`/`console_server.py` remain **completely untouched** (D18 baseline: "connection layer no longer changes"; no parallel entry points). Simulator and real receiver share the same `add_eeg` interface, so the hook works for both—validate with `--sim` first, then real hardware. Consumer must be a **separate process** (`spawn` on Windows) doing its own `resolve_streams()`/`pull_chunk()`; in-process memory passing proves nothing.

**Results (four runs, converging):** LSL loopback self-check—768 samples zero loss, error **0.000e+00** μV, interval 3.9062 ms. Sim dry run—pushed 15192 / received 14808, zero push failures, spectral peak 9.99 Hz. Real machine 22:44—7 checks passed, **strict timestamp monotonicity failed**. Real machine 23:14 (rerun by the user after fixes)—**all 10 passed**: existing buffer 17614 = LSL pushed 17614, 0 push errors, consumer measured **256.0 Hz** exactly, timestamp median == max == **3.9062 ms** (zero jitter), `ts_nonmonotonic_steps = 0`, BrainFlow and MNE band powers **bit-identical**. Most valuable: real BLE thread and LSL push thread ran concurrently with zero contention—something the sim run cannot prove.

**Four collateral bugs found in our own code:** (A) **LSL timestamps must be computed, not left to liblsl**—`push_chunk(data)` stamps at *receive* time; BLE delivers 4 samples/packet with jitter → non-monotonic timestamps. Fix: `local_clock()` baseline, then strict `+= ns/SFREQ`. (B) **Test-orchestration skew masquerades as packet loss**—consumer timed from `open_stream` while the producer needed 20s (36.6s in the last run) to connect, so "pushed 15582 / got 11014" looked like 29% loss. Disproof: inside the consumer's own window, `11014/43.19 = 255.01 Hz`, 0.386% loss; the 4568-sample gap = 17.84s ≈ the 20s connect time. Fix: count the window by *actual data volume*, and give the producer an `ACQ_MARGIN_SEC` surplus. (C) **BrainFlow band power is systematically ~2.5× low**—`get_psd_welch` omits Hann window power normalization (`sum(w²)/N = 3/8`) and `get_band_power` uses rectangular summation. Fingerprints: per-band ratios 0.3707–0.3750 matching **3/8 = 0.375** exactly, with r≈0.9999—"high correlation + constant ratio" is the signature of a pure normalization constant. Fix: multiply by `8/3` and use trapezoid; theta/alpha/beta/gamma then equal **1.000000** exactly (delta residual −1.117% from the 0.5 Hz lower bound and DC-bin handling, recorded honestly). Future NeuraDock adapters must carry this `8/3`, else HUD thresholds and state classification all shift. (D) **`stop_stream()` throwing skipped `release_session()`**, leaving the session holding the headband—this is why the next round failed on all three strategies and the device "mysteriously vanished". Fix: guard each of `stop → get_data → release` separately.

**Reusable triage order:** third-party lib can't see a BLE device → (1) scan independently with bleak: if bleak sees it, it's the lib's BT implementation, not the device/adapter; (2) turn on **trace-level file logging**—the decisive evidence (`identifier` all empty) never appears at info level; (3) compare against this project's *verified* config (preset/sfreq/channel names); (4) "connected but zero data" → suspect handshake/preset first, not bandwidth; (5) failure paths must guarantee resource release or residual sessions poison every later round; (6) judge packet loss from *in-window* metrics, never raw totals; (7) pivot rule: if a library's "drive the hardware" step fails locally but a verified acquisition path already exists, let the library do the **algorithm layer only**.

**Lessons:** (1) A library "supporting" a device in its docs ≠ working on your machine—BrainFlow lists all Muse BoardIds with specs matching ours verbatim (256 Hz, TP9/AF7/AF8/TP10) yet fails on WinRT here; docs being right doesn't mean the machine works, always measure. (2) Matching interfaces are a gift—identical channel names meant zero mapping glue; check such facts before writing code. (3) A standard bus pays off by letting many consumers pull independently (MNE/LabRecorder/Unity/third-party devices)—"don't build wheels you can borrow, but the steering wheel must be yours". (4) Proxy-mounting is how you add an outlet without touching a frozen baseline. (5) Concurrency test harnesses must align their clock to when data actually starts flowing. (6) **Signal quality must be an acceptance gate**: the 23:14 run was 10/10 green on transport yet the data was garbage—±1651 μV, std 209 μV, spectral peak **2.05 Hz** (not 8–12 Hz alpha), theta 8944–15406 μV² vs ~43 μV² in the 09-06 baseline, i.e. two-to-three orders of magnitude off: classic electrode-contact failure/saturation/motion artifact. Transport criteria are orthogonal to signal quality, so "pipeline green" ≠ "data usable". The existing `contact_quality` field (recorded `good` on 09-06) exists for exactly this; the NeuraDock adapter must wire into the same QC gate. **Garbage in, garbage out.**

**Privacy boundary (confirmed):** all three runs produced **no npz** and wrote nothing to the Zen-EEG data factory—the proxy overrides `save_on_disconnect` to a no-op (interception verified firing) and the consumer persists metrics JSON only, never raw waveforms. Entirely local; no network, no upload.
