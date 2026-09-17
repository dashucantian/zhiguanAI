/* 曼荼罗场域 · 构图几何静态复算（AI-005，2026-09-17）
 *
 * 为什么需要它：沙箱内无头 Edge 不可用（受限模式下 Edge 的 mojo 命名管道被拒，
 * 六种启动参数组合实测全失败），拿不到渲染像素判据。但"三层纵深"这件事的
 * 关键量——层间角半径比、各层雾透过率——是**纯几何量**，可由注册表直接算出。
 *
 * 做法：从 vr_mandala.html 里取出 PALETTE / VARIANTS 数据与页面上那份
 * depthMetrics 函数源码，在同一份注册表上复算——即**跑的是页面自己的函数**，
 * 只是不经浏览器。产物是数字，供 S2 规格与验收判据使用。
 *
 * 用法：node mandala_metrics_check.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const HTML = join(here, '..', 'vr_mandala.html')
const src = readFileSync(HTML, 'utf8')

function grab(re, name) {
  const m = src.match(re)
  if (!m) throw new Error(`未能从 vr_mandala.html 取到 ${name}`)
  return m[0]
}

/* 取数据与函数源码（不改写、不转译，原样求值） */
const paletteSrc = grab(/const PALETTE = \{[\s\S]*?\n\};/, 'PALETTE')
const variantsSrc = grab(/const VARIANTS = \{[\s\S]*?\n\};/, 'VARIANTS')
const petalsSrc = grab(/const petalsOf = [^\n]*\n/, 'petalsOf')
const depthSrc = grab(/function depthMetrics\(cfg\)\{[\s\S]*?\n\}/, 'depthMetrics')

const sandbox = {}
const build = new Function(`
  ${paletteSrc}
  ${variantsSrc}
  ${petalsSrc}
  let spec = null
  ${depthSrc}
  return {
    PALETTE, VARIANTS, petalsOf,
    setSpec: v => { spec = v },
    depthMetrics,
  }
`)
const M = build()

const DOC_EXPECT = { inner: 8, middle: 16, ground: 8 }   // Case-M01 §二 ＋ verify_mandala_s1.py:133 判据

console.log('='.repeat(78))
console.log('曼荼罗场域 · 构图几何静态复算（同一份 depthMetrics 源码，不经浏览器）')
console.log('='.repeat(78))

let mismatches = []
for (const [key, spec] of Object.entries(M.VARIANTS)) {
  M.setSpec(spec)
  console.log(`\n───── ${key}  ${spec.label} ─────`)
  console.log(`  相机 [${spec.cam}] · 雾密度 ${spec.fog}`)
  console.log('  层      花瓣数  距离m  最外半径m  角半径°  仰角°   雾透过率')
  const petals = { inner: M.petalsOf(spec.inner), middle: M.petalsOf(spec.middle), ground: M.petalsOf(spec.ground) }
  for (const layer of ['inner', 'middle', 'ground']) {
    const d = M.depthMetrics(spec[layer])
    if (!d) { console.log(`  ${layer.padEnd(7)}  —（未建）`); continue }
    console.log(`  ${layer.padEnd(7)} ${String(petals[layer]).padStart(5)}  ${String(d.dist).padStart(6)}`
      + `  ${String(d.rOut).padStart(8)}  ${String(d.angRadiusDeg).padStart(7)}`
      + `  ${String(d.elevDeg).padStart(6)}  ${String(d.fogTransmittance).padStart(8)}`)
  }
  /* 层间分离度：角半径比 与 雾透过率差 —— "三层纵深"到底立没立起来，看这两个数 */
  const di = M.depthMetrics(spec.inner), dm = M.depthMetrics(spec.middle), dg = M.depthMetrics(spec.ground)
  if (di && dm) {
    console.log(`  ↳ 内/中 角半径比 ${(di.angRadiusDeg / dm.angRadiusDeg).toFixed(2)}`
      + ` · 圆心角距 ${Math.abs(di.elevDeg - dm.elevDeg).toFixed(1)}°`
      + ` · 雾透过率 ${di.fogTransmittance} vs ${dm.fogTransmittance}`
      + `（差 ${(Math.abs(di.fogTransmittance - dm.fogTransmittance) * 100).toFixed(1)} 个百分点）`)
  }
  if (key === 's1') {
    for (const layer of ['inner', 'middle', 'ground']) {
      if (petals[layer] !== DOC_EXPECT[layer]) {
        mismatches.push(`${layer}: 实际 ${petals[layer]} 瓣 ≠ 文档/判据 ${DOC_EXPECT[layer]} 瓣`)
      }
    }
  }
}

console.log('\n' + '='.repeat(78))
console.log('验收逻辑等价性检查：verify_mandala_*.py 的"独立复算"是否与本页 depthMetrics 同解')
console.log('（同解 ⇒ 诚实钩子通过、失实钩子被判失败；这正是 S1 那次事故的防复发点）')
const TOL = { dist: 0.01, ang: 0.15, fog: 0.002 }
let equivBad = 0, equivN = 0
for (const [key, spec] of Object.entries(M.VARIANTS)) {
  M.setSpec(spec)
  for (const layer of ['inner', 'middle', 'ground']) {
    const d = M.depthMetrics(spec[layer]); if (!d) continue
    equivN++
    const dist2 = Math.hypot(spec.cam[0] - d.pos[0], spec.cam[1] - d.pos[1], spec.cam[2] - d.pos[2])
    const ang2 = Math.atan2(d.rOut, dist2 || 1e-9) * 180 / Math.PI
    const fog2 = Math.exp(-Math.pow(spec.fog * dist2, 2))
    const bad = []
    if (Math.abs(dist2 - d.dist) > TOL.dist) bad.push(`距离 ${d.dist} vs ${dist2.toFixed(3)}`)
    if (Math.abs(ang2 - d.angRadiusDeg) > TOL.ang) bad.push(`角半径 ${d.angRadiusDeg} vs ${ang2.toFixed(2)}`)
    if (Math.abs(fog2 - d.fogTransmittance) > TOL.fog) bad.push(`雾 ${d.fogTransmittance} vs ${fog2.toFixed(4)}`)
    if (bad.length) { equivBad++; console.log(`  ❌ ${key}/${layer}: ` + bad.join('；')) }
  }
}
console.log(equivBad === 0
  ? `  ✅ ${equivN} 个层全部同解（容差 距离${TOL.dist}m／角${TOL.ang}°／雾${TOL.fog}）`
  : `  ❌ ${equivBad}/${equivN} 个层不同解——验收脚本会误判，须先修`)

/* 反例检验：把钩子改成"失实"，验收逻辑必须能抓住 */
{
  const spec = M.VARIANTS.s1
  M.setSpec(spec)
  const d = { ...M.depthMetrics(spec.ground) }
  const truth = Math.exp(-Math.pow(spec.fog * d.dist, 2))
  const lied = { ...d, dist: d.dist + 1.0, fogTransmittance: truth + 0.05 }  // 谎报距离与雾
  const dist2 = Math.hypot(spec.cam[0] - lied.pos[0], spec.cam[1] - lied.pos[1], spec.cam[2] - lied.pos[2])
  const fog2 = Math.exp(-Math.pow(spec.fog * dist2, 2))
  const caught = Math.abs(dist2 - lied.dist) > TOL.dist && Math.abs(fog2 - lied.fogTransmittance) > TOL.fog
  console.log(caught
    ? '  ✅ 反例检验：把 ground 的距离谎报 +1.0m、雾谎报 +0.05，验收逻辑两项均能抓住'
    : '  ❌ 反例检验失败：失实钩子未被抓住')
}

console.log('\n' + '='.repeat(78))
console.log('s1 基准对文档与判据的一致性核对（Case-M01 §二 与 verify_mandala_s1.py:133）')
if (mismatches.length === 0) {
  console.log('  ✅ 三层花瓣数 8/16/8 与文档一致')
} else {
  console.log('  ❌ 不一致：')
  for (const m of mismatches) console.log('     - ' + m)
  console.log('  → 这是**实算结果**：几何以注册表为准，说明是文档/判据与几何对不上，')
  console.log('    而不是渲染或测量误差。取值方向（改几何 vs 改文档）须法师裁定。')
}
console.log('\n注：角半径为"该层最外圈在层深度上的等效张角"，对正对相机的立层成立；')
console.log('    大地层是平铺的，其"距离"取层原点距离，角半径仅供层间比较。')
console.log('    雾透过率＝FogExp2 的 exp(-(ρ·d)²)，1.0 表示完全不被雾衰减。')
