# Cadence均衡沉降脑（cadence-net）接引：与止观闭环直连 _v1

> 本稿只做"接"，不做"解"。来源由用户投喂公众号文，本窗当日即对一手源核验并落码。

## 一、来源与一手核验（2026-10-05）

| 件 | 位置 |
|---|---|
| 用户投喂文 | https://mp.weixin.qq.com/s/BMxzYd_MYRJh1nsTO3SdQg（图灵独白，2026-09-24） |
| 一手仓库 | https://github.com/muellerberndt/cadence（v0.74.0，本窗已 clone 至 `_research_src/cadence-net`） |
| 作者长文 | https://muellerberndt.medium.com/you-dont-need-attention-after-all-the-road-to-embodied-agi-with-cadence-8606a64e40df |
| 官网 | https://floatingpragma.io/cadence/ |
| 安装 | `pip install cadence-net==0.74.0`（依赖仅 numpy；本窗 Python 3.14.7 + numpy 2.5.3 装用通过） |

**⚠️ 许可证留证**：公众号文称 MIT；仓库 LICENSE 实为 **GPLv3**。以一手源为准。后续若与闭源组件链接分发需按 GPLv3 评估——请 W3/W4 记备。

## 二、映射：不解释，直接接

| 止观AI（我们） | Cadence 0.74（虫） | 桥内落点 |
|---|---|---|
| 止（等持） | equilibrium settling，沉降即答案 | `brain.step()` 的沉降本身 |
| 观（照） | `last_settlement` 读出（residual/steps/tolerance，无隐藏思考token——Connect Four"亲眼看它想"） | `settle_readout()` → trace，可直供 vr_mandala 可视化 |
| 修用无别（座上座下不二） | 训练=推理，无 train/inference 开关 | `step()` 即学即用 |
| 一念微调（不整盘推倒） | Equilibrium Propagation 局部轻推，无全局反传 | `observe_reward()` → 下拍 reward |
| 所缘结构（戒） | connectome 刚性掩码，接线不凭空长出 | `Brain.compose()` 固定结构 |
| 串习（快）／定中沉淀（慢） | record store 快记 + 慢权重"睡梦"整合（文中 8000 梦实验：81.5%→100%） | 待挂 hippocampus/consolidation |
| 跨会话续修（同一命） | `Brain.save/load` 全保真（含海马、工作记忆、pending action） | `save()`（注意：返回真实 `.npz` 路径） |
| 食／戳（多巴胺／ASH） | reward ±1 | 仅取观察量：入定维持/新入=食，失定伴躁=戳 |
| 内演（Amen"先内演后择和"） | `brain.imagine` | 后续挂音频生成 |
| Patch World 无全局适应度 | 无全局打分 | 与"观察＞引导；反馈＞干预"同构 |

## 三、已落代码：`zhiguan_cadence_bridge.py`（根目录，与 closedloop_* 平级）

- 观测 6 维：`z(α/θ)`、`z(−β/α)`、in_state、dwell、prev_residual、支持水平自感
  （特征口径与 `state_segmentation.py` BANDS/RATIOS 一致，仅取两比值，聚合方式由宿主定）
- 动作 4 维：降拍/持/升拍/撤一档音量 → 宿主 `IsoEngine.set_beat/set_volume`（本桥不碰音频设备）
- 纪律：固定种子、同输入逐字一致（判语011）；观测不可算→弃权 None（一等值）；
  reward 只来自观察量（镜子非训练器，判语009）
- 自测实录（300 拍合成会话）：
  `[selftest OK] ticks=300 deterministic=True bounds=OK abstain=OK continuation=OK final(action=1, beat=9.50, vol=0.130, residual=0.0000, steps=32)`

## 四、W1 接入点（未动 W1 文件，三行即接）

`closedloop_controller.update()` 内：
```python
obs = bridge.build_observation(z_at, z_ba, in_state, dwell/30.0, prev_residual)
out = bridge.step(obs, reward=bridge.observe_reward(in_prev, in_state, wandering))
iso.set_beat(out["beat"]); iso.set_volume(out["volume"])
```

## 五、论文自认三条红线（与本仓见地纪律同向，直接采）

1. 非生物脑、非意识 → AI 负责组织证据，人负责裁定结论；
2. **"睡梦"会忠实放大错误记忆** → 见地先行；邪见在定中被放大——判语009 的工程面；
3. 从线虫到类人脑的鸿沟未证 → 定位为"反馈参数策略脑"，非大模型替代。

## 六、复现

```
python -m pip install cadence-net==0.74.0
python zhiguan_cadence_bridge.py --selftest
```

## 七、未做与待裁定

- 未动 `closedloop_controller.py`（W1 领地，接入点见 §四）
- 未做真机 Muse 联测（需 W1 真机窗口）
- 眠梦整合（hippocampus 慢权重）与 imagine 内演挂接：二期
- 本窗未走正式身份登记；trailer 如实注明，完整模型版本号待人工补录

## 八、二期实录（同日续：睡梦＋内演＋真数据回放）

### 8.1 睡梦/串习 rehearse()——走 fit 正牌通道

- 0.74 **无独立 dream API**；沉淀机制＝`compose(consolidation=)`＋step 的 `salience`（缺省=|reward|，睡中无奖会归零→须显式给，本窗第一版踩过）
- 复讲正道＝`Brain.fit(observations, labels, epochs, batch)`（独立样本教学，逐轮返回 qualified 训练命中率）
- **实测**（4模式课程，200拍日＋40 held-out）：**held-out 0.300 → 0.975**（train 0.980）——文章"睡梦把碎片沉淀为规律"在桥上复现
- 两档语义：`teacher=None` 按当日实际所择复演（固化"已发生"）；`teacher=list` 以事后已知正确反馈复讲（改过复讲，不预测未来）
- 旋钮留证：`qualified=True`（不合格课拒收，RuntimeWarning 消失）；`free_steps/nudged_steps` 须 ≥4096/8192——**1024 会 `LearningPhaseError: opposite phase did not settle`（residual 1.5e-4 > tol 1e-4，两次复现）**
- 弯路留证：teacher 逐拍 step 复讲 1600 拍命中率纹丝不动（0.300→0.300，步长~1e-3）——逐拍复讲不是通道，fit 才是

### 8.2 内演择和 imagine_vote()

- `Brain.imagine(obs_sequence)`：私密沉降，**读而不写**（参数/随机源/pending 不动）；motor 读出＝`eq.state.activation[:, motor_index]`，须查 `eq.qualified`
- API 门面留证：**没有 `eq.activation`**（v2 初版踩过，AttributeError）；imagine 的 batch 须与活流一致（1行流→逐行内演）
- 自测断言：内演后紧接的实命贪心选择与未内演对照**逐字一致**（内演不污染实命）✓；同喂同票 ✓

### 8.3 真实 Muse npz 离线回放（`cadence_replay_experiment.py`）

- 数据：`muse2-repo/report/local_20260830_202946.npz`（62min，948362×4；**仅存 eeg 无 timestamps**→按 256Hz 假定，summary 里 `sfreq_source: assumed_muse256` 如实标注）
- 结果：**3704 拍，valid 91.0%，in_state(演示口径 z(α−θ)>0.8) 30.9%，沉降残差均值 1.9e-6**；末拍 beat 12.0 / vol 0.05
- 89s 小会话 `local_20260831_210138.npz`：in_state=0.0——**如实**：该段未检出 α 优势，桥全程弃权式温和持/降
- **行为留证（不悄悄调参）**：reward 口径对"维持"不加区分 → 动作漂向恒升拍顶界（12Hz，act2×2663）——reward shaping 留 **W4** 裁定
- 产物：`output/cadence_replay/`（trace json＋brain 存档；`output/` 为忽略目录，未入库，路径注明）

### 8.4 观之可视化 `cadence_mandala.html`

- 302 结点环（向线虫连接组致意）；残差→辉光、动作→着色、入静→呼吸；z(α−θ) 曲线＋阈值线；嵌入真坐片段（stride=8）＋可载全量 trace json
- 纯静态单文件，无外部依赖（`*.html` 受 .gitignore:76 忽略，循 console/demo/focus.html 先例显式入库）

### 8.5 自测终态（9 项）

```
[selftest OK] ticks=300 deterministic=True bounds=OK abstain=OK continuation=OK dream(before=0.300,after=0.975,replayed=1600) imagine(votes=[1, 1, 1],agreement=True,read_only=True) final(action=1, beat=9.50, vol=0.130, residual=0.0000, steps=32)
```

### 8.6 未做与归属

- reward shaping（区分"维持/新入/失定"）→ W4
- 真机实时联测 → W1
- `vr_mandala.html` 接入 settle_readout 实时流 → W1 领地（本窗只给独立件 cadence_mandala.html）

### 8.7 使用订正两则（用户反馈，当日即改）

1. **"一小时数据怎么只呈现几秒"**：v1 环动画步长为任意值（0.02/40ms），整座被压成 ~2 秒扫过，且无时间轴——设计缺陷，非数据丢失（3704 拍都在，只是呈现方式错）。v2 订正：
   - 真实时间轴（epoch=1s）：clock 显示"已坐 mm:ss / 61:44 · 第 N 拍 · 速度"；
   - 速度档 **实时 1×（默认，与真实打坐同速）** / 8× / 60× / 600×；
   - 按帧真实 dt 推进——留证：初版按 40ms 定步长，在 rAF≈16.7ms 下速度会虚标 2.4×，已改 dt 制；
   - "下一入静段"跳段按钮；**下方曲线＝整座全貌**——"一个小时"的正确呈现处（静观全局看曲线，动观过程走环）。
2. **"zhiguan_cadence_bridge.py 双击闪退"**：桥是引擎库、无界面，双击＝跑完即退（exit 0）——属预期但不可用。v2 订正：无参数双击＝自检（9 项）＋合成一坐逐拍演示（40 拍打印观之读出）＋停窗等回车；`--no-hold` 可关停窗；`--selftest` 行为不变（供管线）。
   - 验收：node --check 语法过；无头 Edge dump-dom 实测 `已坐 00:01 / 61:44 · 1×`、summary 含 `assumed_muse256`；`--no-hold` 退出码 0。
