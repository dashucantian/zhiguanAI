#!/bin/sh
# 提交件数核对钩子（commit-msg hook）｜**只警告、永不拦阻**（永远 exit 0）
#
# 授权链：宗国法师 2026-10-11 对"丙案（提交时的自动核对）内容"裁「**4、同意**」，同轮「**2、先运行看效果**」。
# 病根与判据出处：`01_项目管理/案例库/决策判语/017_自报数先跑量具再落笔_无检查点的规则不等于规则.md`
#   ——该规矩早已在必读（`AI-开工入口.md` §二.3 〔10-09 补条〕＋⑧）却复发 10 次（W3 七／W1 三）
#   ⇒ **无检查点的规则不等于规则**。对照组＝"跨日重取系统日期"挂了门6 之后未再复发。
#   本钩子就是给"自报数"这条规矩补的那个检查点，挂在**唯一还能挂的时刻＝提交那一刻**。
#
# ⚠为什么不改 `收口检查.ps1`：该脚本 2026-10-08 法师裁「不准修」，10-11 又裁「1、保持」⇒ 不加第 13 门。
# ⚠为什么只警告不拦阻：钩子出现在**四个窗口共用**的提交路径上（四窗共用一个 `.git`），
#   拦阻会把他窗的提交挡掉，那不是本窗能替法师决定的事。故 **一律 exit 0**。
#
# ⚠**装完第一轮反向验证即抓出一个真缺陷（已修，留此防复发）**：提示语原写
#   say "…＋`AI-开工入口.md` §二.3。" —— 双引号内的**反引号在 shell 里是命令替换**，
#   于是每次报缺尾注时都会去"执行"这个文件名，输出 `command not found` 并把该文件名从提示里吃掉。
#   ⇒ **规则：本文件所有会被执行的字符串里禁用反引号**，需要引号时改用「」或单引号；
#   注释行里的反引号无害（不执行）。教训同坑 024：**反向验证不做，这种缺陷会一直静默到某次真提交。**
#
# 安装（正本受版本管理，安装体在 `.git/hooks/` 内不入版本，两者须一致）：
#   cp 提交件数核对钩子.sh .git/hooks/commit-msg && chmod +x .git/hooks/commit-msg
# 卸载：rm .git/hooks/commit-msg
#
# 核对三项（全部只报不拦）：
#   ① 提交信息标题里自称的"N 件" vs 暂存区（staging area）实际文件数
#   ② 自称的"增 X／删 Y" vs `git diff --cached --numstat` 实算
#   ③ 六条署名尾注（trailer）在不在：Author-Role／Proposal-by／Approved-by／Model／Session／Window

MSG_FILE="$1"
[ -f "$MSG_FILE" ] || exit 0

# 取暂存区实数（量具原样输出，不手数）
STAGED_N=$(git diff --cached --name-only 2>/dev/null | grep -c .)
[ -z "$STAGED_N" ] && STAGED_N=0
NUMSTAT=$(git diff --cached --numstat 2>/dev/null | awk '$1 ~ /^[0-9]+$/ {a+=$1; d+=$2} END {printf "%d %d", a+0, d+0}')
ADD_N=$(echo "$NUMSTAT" | cut -d' ' -f1)
DEL_N=$(echo "$NUMSTAT" | cut -d' ' -f2)

WARN=0
say() { printf '%s\n' "$1"; }

# ---- ① 件数 ----
# 只认标题行（第一行）里的"N 件"，正文里的件数说法太多、会误报。
SUBJECT=$(head -1 "$MSG_FILE")
CLAIM_N=$(printf '%s' "$SUBJECT" | sed -n 's/.*[^0-9]\([0-9][0-9]*\)[ 　]*件.*/\1/p')
if [ -n "$CLAIM_N" ] && [ "$CLAIM_N" != "$STAGED_N" ]; then
  WARN=1
  say ""
  say "⚠【件数核对·只警告不拦阻】标题自称 ${CLAIM_N} 件，暂存区（staging area）实为 ${STAGED_N} 件。"
  say "   量具原样输出：git diff --cached --name-only | grep -c . = ${STAGED_N}"
  say "   判语 017：数须照量具输出誊，禁预估与记忆。若标题写法非指件数（如「三件候裁」），忽略本行即可。"
fi

# ---- ② 增删行数 ----
CLAIM_ADD=$(printf '%s' "$SUBJECT" | sed -n 's/.*增[ 　]*\([0-9][0-9,]*\).*/\1/p' | tr -d ',')
CLAIM_DEL=$(printf '%s' "$SUBJECT" | sed -n 's/.*删[ 　]*\([0-9][0-9,]*\).*/\1/p' | tr -d ',')
if [ -n "$CLAIM_ADD" ] && [ "$CLAIM_ADD" != "$ADD_N" ]; then
  WARN=1
  say ""
  say "⚠【增删核对·只警告不拦阻】标题自称增 ${CLAIM_ADD}，实算增 ${ADD_N}（git diff --cached --numstat 求和）。"
fi
if [ -n "$CLAIM_DEL" ] && [ "$CLAIM_DEL" != "$DEL_N" ]; then
  WARN=1
  say ""
  say "⚠【增删核对·只警告不拦阻】标题自称删 ${CLAIM_DEL}，实算删 ${DEL_N}（git diff --cached --numstat 求和）。"
fi

# ---- ③ 署名尾注（trailer）六字段 ----
MISSING=""
for K in Author-Role Proposal-by Approved-by Model Session Window; do
  grep -q "^${K}:" "$MSG_FILE" || MISSING="${MISSING} ${K}"
done
if [ -n "$MISSING" ]; then
  WARN=1
  say ""
  say "⚠【署名尾注核对·只警告不拦阻】缺：${MISSING# }"
  say "   依据《AI代理身份登记》§六模板＋「AI-开工入口.md」§二.3。"
  say "   ⚠本项在 shell 侧直读字节，不受「收口检查.ps1」门4 的编码假阴性影响（KZ-1007-W3e）。"
fi

if [ "$WARN" = "0" ]; then
  say "〔件数核对钩子〕三项全过：${STAGED_N} 件｜增 ${ADD_N}／删 ${DEL_N}｜署名尾注六字段齐。"
fi

# **永远放行**：本钩子只报不拦（法师 10-11「先运行看效果」＝观察期，观察期内不改任何窗的提交结果）
exit 0
