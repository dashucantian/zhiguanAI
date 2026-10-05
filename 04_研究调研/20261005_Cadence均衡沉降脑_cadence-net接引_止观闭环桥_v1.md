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
