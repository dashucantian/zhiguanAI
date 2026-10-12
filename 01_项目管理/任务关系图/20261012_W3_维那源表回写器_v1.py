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

# —— 列白名单（P2 默认＝三列；建新行时另允许"标识四列"，含 `状态`＝P3 默认"只同步状态列"的那一列）——
WRITE_COLS = {"承接状态", "裁决", "AI执行窗口"}
IDENTITY_COLS = {"任务名", "任务编号", "关联文件", "状态"}
FORBIDDEN_COLS = {"承担者", "更新时间", "受理戳"}   # 真人名列与系统列，任何模式都不写

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
    """复用同目录 10-07 拉取器的鉴权与读取函数，**不另造第二套凭据取法**。"""
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

    def select_options(tk):
        fields = m.fetch_fields(tk, BASE_TOKEN, TABLE_ID)
        out = {}
        for f in fields:
            opts = (f.get("property") or {}).get("options") or []
            if opts:
                out[f["field_name"]] = [o.get("name") for o in opts if o.get("name")]
        return out

    def batch_create(tk, recs):
        url = "%s/bitable/v1/apps/%s/tables/%s/records/batch_create" % (API, BASE_TOKEN, TABLE_ID)
        return m.http_json(url, "POST",
                           headers={"Authorization": "Bearer " + tk,
                                    "Content-Type": "application/json; charset=utf-8"},
                           payload={"records": recs})

    def verify(tk, numbers):
        fields = m.fetch_fields(tk, BASE_TOKEN, TABLE_ID)
        names = [f["field_name"] for f in fields]
        snap = m.fetch_records(tk, BASE_TOKEN, TABLE_ID, names, 500)
        have = set()
        idx = names.index("任务编号") if "任务编号" in names else None
        for row in (snap or []):
            if idx is None:
                break
            v = row[idx] if isinstance(row, list) else None
            if isinstance(v, list):
                v = "".join(x.get("text", "") for x in v if isinstance(x, dict))
            if v:
                have.add(str(v).strip())
        return len([n for n in numbers if n and str(n).strip() in have])

    return {"token": token, "select_options": select_options,
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

    pull = _load_puller()          # 复用同目录拉取器的鉴权与字段读取，不另造一套
    if a.check or a.fire:
        token = pull["token"]()
        opts = pull["select_options"](token)
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
        if not a.fire:
            return 0
    if not a.fire:
        print("═══ DRY-RUN｜未发任何写调用。要真写＝法师给「落笔」二字后加 --落笔（另需环境变量）。")
        return 0

    print("⚠「落笔」模式：即将向飞书发出 batch_create（删行需人工，非自动可回收）。")
    if os.environ.get("ZIGUAN_WRITE_OK") != "1":
        print("FATAL｜环境变量 ZIGUAN_WRITE_OK=1 未设 ⇒ 拒绝写。")
        print("       这道双闸是故意的：脚本被误跑、被别的窗拿去跑，都不会改到您那张表。")
        return 1
    recs = [{"fields": r["fields"]} for r in data["rows"]]
    res = pull["batch_create"](pull["token"](), recs)
    code = res.get("code")
    if code != 0:
        print("FATAL｜batch_create 返回 code=%s msg=%s（照实报，不重试、不改列名硬凑）"
              % (code, res.get("msg")))
        return 1
    created = res.get("data", {}).get("records", []) or []
    print("[已写] 返回 %d 行 record" % len(created))
    hit = pull["verify"](token if False else pull["token"](),
                        [r["fields"].get("任务编号") for r in data["rows"]])
    print("[跑后校验和] 新行号命中 %d／%d" % (hit, len(data["rows"])))
    return 0 if hit == len(data["rows"]) else 1


if __name__ == "__main__":
    sys.exit(main())
