# -*- coding: utf-8 -*-
"""维那身份·源表回写器（W3·2026-10-12 法师裁 N1「准」＋10-12 20:5x 前既已同意建脚本）

职责：把仓库里"已发生但源表没记"的两类事实写回飞书多维表格（任务真身）：
  ① **建新行**（N1 准）＝8 个只在文书里出现的 ZG 号（`ZG-063`／`ZG-074`～`ZG-080`）；
  ② **只同步状态列**（P2 默认面）＝`承接状态`／`裁决`／`AI执行窗口` 三列，**禁改表结构、禁删行、禁写 `承担者`**。

安全设计（四条，写进代码而不是写进承诺）：
  1. **默认 dry-run**：不带 `--落笔` 一律只打印 payload 并做本地校验，**一次网络调用都不发**；
  2. 列白名单硬编码：payload 里出现白名单外的键（尤其 `承担者`）⇒ 直接退出码 1，不降级继续；
  3. 跑前打印 diff（逐行逐列"旧值→新值"），跑后**重拉一次做校验和**：新行号命中即 PASS，未命中即 exit 1；
  4. 凭据只读本机配置（同 `20261007_W3_维那快照拉取_v1.py`），密钥驻内存、不回显、不落盘、不写日志。

用法：
  python 01_项目管理/任务关系图/20261012_W3_维那源表回写器_v1.py --dry-run
  python 01_项目管理/任务关系图/20261012_W3_维那源表回写器_v1.py --落笔 --what rows      # 法师给「落笔」后才允许
  python ... --落笔 --what fields --rows 01_项目管理/20261012_W3_源表候登8行_payload.json
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

API = "https://open.feishu.cn/open-apis"
BASE_TOKEN = "X4xXbTF57acOnZs1ZzZcF4P2nJg"
TABLE_ID = "tblLf45tgSgBoLue"

# —— 列白名单（P2 默认＝三列；建新行时另允许"标识三列"，含 `状态`＝P3 默认"只同步状态列"的那一列）——
# ⛔`任务编号` 已移出白名单（10-14 实测）：该列在表上是 **auto_number（自动编号）**，写进去不报错、
#   服务端直接换成流水号 ⇒ 号与文错位一行。详见 01_项目管理/案例库/踩坑档案/049_*。
WRITE_COLS = {"承接状态", "裁决", "AI执行窗口"}
IDENTITY_COLS = {"任务名", "关联文件", "状态"}
FORBIDDEN_COLS = {"承担者", "更新时间", "受理戳", "任务编号"}   # 真人名列＋系统列＋自动编号列，任何模式都不写
# 服务端持有的列类型（bitable v1 数字码）：22 自动编号／19 引用／20 公式／23 按钮／1001-1005 创建·修改时间与人员
SERVER_OWNED_TYPES = {22, 19, 20, 23, 1001, 1002, 1003, 1004, 1005}

ROWS_PATH = Path("01_项目管理/20261012_W3_源表候登8行_payload.json")


def load_payload(p):
    if not p.is_file():
        print("FATAL｜payload 文件不存在：%s（先跑 --dry-run 生成候登稿）" % p)
        return None
    data = json.loads(io.open(p, encoding="utf-8-sig").read())
    bad = []
    for r in data.get("rows", []):
        keys = set(r.get("fields", {}).keys())
        over = sorted(keys - WRITE_COLS - IDENTITY_COLS)
        if over:                      # 只在真越列时点名（空列表不算越，别把合规的行报成违规）
            bad.append("%s：越列 %s" % (r.get("ref"), over))
    if bad:
        print("FATAL｜列白名单被越（规约 §二.3／法师 P2 收窄面）：")
        for b in bad:
            print("   ", b)
        return None
    for r in data.get("rows", []):
        k = FORBIDDEN_COLS & set(r.get("fields", {}).keys())
        if k:
            print("FATAL｜禁写列出现在 payload：%s（%s）" % (sorted(k), r.get("ref")))
            return None
    return data


def show(data):
    print("候登行数＝%d｜表＝%s/%s" % (len(data["rows"]), BASE_TOKEN[:6] + "…", TABLE_ID))
    for r in data["rows"]:
        f = r["fields"]
        print("  %-8s｜%s" % (r["ref"], f.get("任务名", "（改行）")))
        print("           状态＝%s｜承接＝%s｜窗口＝%s｜出处＝%s"
              % (f.get("状态", "—"), f.get("承接状态", "—"), f.get("AI执行窗口", "—"),
                 f.get("关联文件", "—")))
    print("合计字符数（校验和用）＝%d" % len(json.dumps(data, ensure_ascii=False)))


def _load_puller():
    """复用同目录 10-07 拉取器的鉴权与 HTTP 面（不另造第二套凭据取法）。

    ⚠2026-10-13 00:1x「落笔」前自查抓出第一版三处错，先修后写（全是"我建的闸自己先错"同族）：
      ①拉取器 fetch_fields() 返回精简结构 [{name,id,type}]，property 已被剥掉
        ⇒ 旧写法 f.get("property") 永远取空 ⇒ 选项校验空跑一遍却报"通过"
        （正是门8 自检警告过的"本门可能恒空转"）。现改直读原始字段面，并加硬闸：
        读到的单选列数＝0 ⇒ FATAL，不判通过（读不到≠通过）。
      ②http_json() 返回 (status, body) 二元组 ⇒ 旧写法当 dict 用，写调用必崩。已解包判 code。
      ③fetch_records() 返回 (items, pages)，items 是原始 record（{record_id, fields:{…}}）
        ⇒ 旧写法按"等宽行下标"取值永远取不到 ⇒ 校验和会恒为 0。现按 fields["任务编号"] 取。
    """
    import importlib.util
    here = Path(__file__).resolve().parent
    src = here / "20261007_W3_维那快照拉取_v1.py"
    if not src.is_file():
        raise SystemExit("FATAL｜找不到拉取器：%s（鉴权面唯一真相源，缺它本脚本拒绝运行）" % src)
    spec = importlib.util.spec_from_file_location("weina_puller", str(src))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    home = m.dsh_home()

    def token():
        bots = m.load_bots(home / "integrations" / "dsh-feishu" / "config.json")
        bot = m.pick_bot(bots, "维那")
        secret = m.read_secret(home / ".credentials.yaml", bot["secretRef"])
        return m.tenant_token(bot["appId"], secret)

    def _call(url, method, tk, payload=None):
        head = {"Authorization": "Bearer " + tk}
        if payload is not None:
            head["Content-Type"] = "application/json; charset=utf-8"
        status, body = m.http_json(url, method, head, payload)
        if status != 200 or body.get("code") != 0:
            raise SystemExit("FATAL｜HTTP %s code=%s msg=%s"
                             % (status, body.get("code"), str(body.get("msg"))[:200]))
        return body.get("data") or {}

    def raw_fields(tk):
        url = "%s/bitable/v1/apps/%s/tables/%s/fields?page_size=200" % (API, BASE_TOKEN, TABLE_ID)
        items, seen, guard = [], set(), 0
        while url:
            guard += 1
            if guard > 20:
                raise SystemExit("FATAL｜字段分页超上限 20 页，拒绝出结论")
            data = _call(url, "GET", tk)
            for it in data.get("items") or []:
                nm = it.get("field_name")
                if nm and nm not in seen:
                    seen.add(nm)
                    items.append(it)
            nxt = data.get("page_token") if data.get("has_more") else None
            url = (url.split("&page_token=")[0] + "&page_token=" + nxt) if nxt else None
        if not items:
            raise SystemExit("FATAL｜字段面为空 ⇒ 本校验不可信（读不到不等于通过）")
        return items

    def select_options(tk):
        out = {}
        for it in raw_fields(tk):
            opts = ((it.get("property") or {}).get("options")) or []
            names = [o.get("name") for o in opts if o.get("name")]
            if names:
                out[it["field_name"]] = names
        if not out:
            raise SystemExit("FATAL｜读到的单选列＝0 ⇒ 选项校验无法执行，不判通过（防恒空转）")
        return out

    def batch_create(tk, recs):
        url = "%s/bitable/v1/apps/%s/tables/%s/records/batch_create" % (API, BASE_TOKEN, TABLE_ID)
        return _call(url, "POST", tk, {"records": recs})

    def verify(tk, numbers):
        """跑前与跑后都调它：全表分页读原始 record 的 fields["任务编号"]，命中才计数。"""
        url = "%s/bitable/v1/apps/%s/tables/%s/records/search?page_size=500" % (
            API, BASE_TOKEN, TABLE_ID)
        have, pages, seen_tokens = set(), 0, set()
        while url:
            pages += 1
            if pages > 50:
                raise SystemExit("FATAL｜记录分页超上限 50 页，拒绝出结论")
            data = _call(url, "POST", tk, {})
            for it in data.get("items") or []:
                v = (it.get("fields") or {}).get("任务编号")
                if isinstance(v, list):
                    v = "".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in v)
                if v:
                    have.add(str(v).strip())
            nxt = data.get("page_token") if data.get("has_more") else None
            if nxt and nxt in seen_tokens:
                raise SystemExit("FATAL｜分页 token 重复，拒绝出结论（防自循环）")
            seen_tokens.add(nxt)
            url = (url.split("&page_token=")[0] + "&page_token=" + nxt) if nxt else None
        hit = len([n for n in numbers if n and str(n).strip() in have])
        return hit, len(have)

    return {"token": token, "select_options": select_options, "raw_fields": raw_fields,
            "batch_create": batch_create, "verify": verify}



def main():
    ap = argparse.ArgumentParser(description="维那源表回写器（默认 dry-run，不发网络）")
    ap.add_argument("--dry-run", action="store_true", help="只本地校验并打印 payload（缺省行为）")
    ap.add_argument("--落笔", dest="fire", action="store_true", help="法师给字后才可用：真调 batch_create")
    ap.add_argument("--check-remote", dest="check", action="store_true",
                    help="只读联网：拉字段表校验每个单选值是否存在（不写）")
    ap.add_argument("--rows", type=Path, default=ROWS_PATH)
    a = ap.parse_args()

    data = load_payload(a.rows)
    if data is None:
        return 1
    show(data)

    if not (a.check or a.fire):
        print("═══ DRY-RUN｜未发任何网络调用。要真写＝法师给「落笔」后加 --落笔（另需环境变量）。")
        return 0

    pull = _load_puller()          # 复用同目录拉取器的鉴权与字段读取，不另造一套
    tk = pull["token"]()
    # 现读列类型 ⇒ 服务端持有的列（自动编号／引用／公式／系统时间…）一律拒发。
    # 为什么不能只靠上面的名字白名单：`任务编号` 曾被当普通文本列放进 IDENTITY_COLS，
    # 写下去不报错、值却被服务端换掉——名字层面看不出来，必须问类型。
    owned = {}
    for it in pull["raw_fields"](tk):
        if it.get("type") in SERVER_OWNED_TYPES:
            owned[it.get("field_name")] = it.get("ui_type") or it.get("type")
    if not owned:
        raise SystemExit("FATAL｜读到的服务端持有列＝0 ⇒ 本闸不可信（读不到不等于通过），拒绝继续")
    hit_owned = sorted({c for r in data["rows"] for c in r["fields"] if c in owned})
    if hit_owned:
        print("FATAL｜payload 往服务端持有列写了值：%s" % ["%s(%s)" % (c, owned[c]) for c in hit_owned])
        print("       ⇒ 这些列的值会被服务端改写或忽略，写了就是假账。请从 payload 删除这些键。")
        return 1
    print("[只读] 服务端持有列＝%d 个（%s）⇒ 本窗口不写这些列"
          % (len(owned), "／".join(sorted(owned))))
    opts = pull["select_options"](tk)
    print("[只读] 表内带选项的列＝%d 个：%s" % (len(opts), "／".join(sorted(opts))))
    miss = []
    for r in data["rows"]:
        for col, val in r["fields"].items():
            if col in opts and val not in opts[col]:
                miss.append("%s：%s＝%r 不在该列选项内（现有选项：%s）"
                            % (r["ref"], col, val, "／".join(opts[col])))
    if miss:
        print("FATAL｜单选值对不上表内选项，**不降级、不自动新建选项**：")
        for m in miss:
            print("   ", m)
        return 1
    print("[只读校验通过] 所有单选值均在表内选项之中")

    numbers = [r["fields"].get("任务编号") for r in data["rows"]]
    hit0, total0 = pull["verify"](tk, numbers)
    print("[写前基线] 表内带号记录 %d 条｜这 %d 个号当前已存在 %d 条（应为 0，否则＝重复登表）"
          % (total0, len(numbers), hit0))
    if hit0:
        print("FATAL｜候登号里有已在表上的 ⇒ 先查清是哪几条，**不重复建行**")
        return 1
    if not a.fire:
        print("═══ CHECK-REMOTE 通过（全程只读，未发写调用）。")
        return 0

    print("⚠「落笔」模式：即将向飞书发出 batch_create（删行需人工，非自动可回收）。")
    if os.environ.get("ZIGUAN_WRITE_OK") != "1":
        print("FATAL｜环境变量 ZIGUAN_WRITE_OK=1 未设 ⇒ 拒绝写。")
        print("       这道双闸是故意的：脚本被误跑、被别的窗拿去跑，都不会改到您那张表。")
        return 1
    res = pull["batch_create"](tk, [{"fields": r["fields"]} for r in data["rows"]])
    created = res.get("records") or []
    print("[已写] 接口返回 %d 条 record" % len(created))
    hit1, total1 = pull["verify"](pull["token"](), numbers)
    print("[跑后校验和] 表内带号记录 %d 条（写前 %d）｜候登 %d 号命中 **%d／%d**"
          % (total1, total0, len(numbers), hit1, len(numbers)))
    if hit1 != len(numbers):
        print("FATAL｜写后盘侧复核未全命中 ⇒ 立即上呈，**不静默、不重跑碰运气**")
        return 1
    print("═══ 落笔完成：8 行已进表；写前写后两次盘侧复核一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
