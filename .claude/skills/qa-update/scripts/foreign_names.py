"""承認済みの追加候補から「外国人名の音読み」の疑いがあるものを決定的に検出する。

NDL 典拠には中国・朝鮮などの人名が日本語の音読みで入っている（例: 張 憲文 → ちょう けんぶん）。
fetch_ndl.py の作業ディレクトリ（prefix-*.jsonl）は 1 人につき surname 行・given 行が続けて入っているので、
(名の表記, 読み) ごとにその名を持つ人物の姓を数えられる。姓が中国・朝鮮系の 1 字姓の音読み（CJK_SURNAMES、
かつ last_name_org.csv に同じ読みの姓がない）の人物を除き、残る人数が min_support 未満で Wikidata の
裏付けもない表記を不採用とする。

  python3 foreign_names.py --findings qa/findings/<run-id>.jsonl --ndl-work qa/sources/ndl-work-<date> \\
    --index qa/sources/index.json --dataset-dir japanese_personal_name_dataset/dataset [--list] [--apply]

--apply なしでは台帳を変更しない。--apply で add_kanji / 全表記が該当する add_row を rejected にし、
一部の表記だけが該当する add_row は該当表記を entry から外す。
"""
import argparse
import collections
import csv
import glob
import json
import os
import sys
from typing import Dict, Iterable, List, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "validate-dataset", "scripts")))

import findings_io  # noqa: E402
import sources_common as sc  # noqa: E402

MIN_SUPPORT = 2
REASON = "rule: 外国人名の音読みの疑い"

# 中国・朝鮮系の 1 字姓と、その日本語での音読み。日本の姓としても同じ読みで使われるもの
# （田/でん・千/せん・宗/そう・頼/らい・尚/しょう・紀/き・菅/かん・伴/ばん など）は入れない。
_CJK = (
    "王:おう 李:り 張:ちょう 劉:りゅう 陳:ちん 楊:よう 黄:こう 趙:ちょう 呉:ご 周:しゅう 徐:じょ 孫:そん 馬:ば 朱:しゅ "
    "胡:こ 郭:かく 何:か 高:こう 林:りん 羅:ら 鄭:てい 梁:りょう 謝:しゃ 宋:そう 唐:とう 許:きょ 韓:かん 馮:ふう,ひょう "
    "鄧:とう 曹:そう 彭:ほう 曽:そう 曾:そう 蕭:しょう 肖:しょう 董:とう 袁:えん 潘:はん 于:う 蒋:しょう 蔣:しょう 蔡:さい "
    "余:よ 杜:と 葉:よう,しょう 程:てい 蘇:そ 魏:ぎ 呂:りょ,ろ 丁:てい 任:じん,にん 沈:しん,ちん 姚:よう 盧:ろ 姜:きょう "
    "崔:さい 鍾:しょう 譚:たん 陸:りく 汪:おう 范:はん 石:せき 廖:りょう 賈:か 夏:か 韋:い 傅:ふ 方:ほう 白:はく 鄒:すう "
    "孟:もう 熊:ゆう 秦:しん 邱:きゅう 江:こう 尹:いん 薛:せつ 閻:えん 段:だん 雷:らい 侯:こう 龍:りゅう 竜:りゅう 史:し "
    "陶:とう 黎:れい 賀:が 顧:こ 毛:もう 郝:かく 龔:きょう 邵:しょう 万:ばん,まん 萬:ばん,まん 銭:せん 錢:せん 厳:げん 嚴:げん "
    "武:ぶ 戴:たい 莫:ばく 孔:こう 向:こう 湯:とう 朴:ぼく,ぱく 金:きん 申:しん 権:けん 權:けん 安:あん 柳:りゅう 洪:こう "
    "全:ぜん 文:ぶん 裵:はい 裴:はい 南:なん 河:か 兪:ゆ 成:せい 車:しゃ 具:ぐ 禹:う 辛:しん 閔:びん 池:ち 元:げん 玄:げん "
    "咸:かん 魯:ろ 卞:べん 奉:ほう 慎:しん 廉:れん 殷:いん 楚:そ 屈:くつ 柴:さい 岳:がく 喬:きょう 祝:しゅく 左:さ 包:ほう "
    "童:どう 顔:がん 甘:かん 易:えき 常:じょう 康:こう 牛:ぎゅう 斉:せい 齊:せい 倪:げい 欧:おう 費:ひ 聞:ぶん 鮑:ほう 華:か "
    "翁:おう 関:かん 關:かん 路:ろ 凌:りょう 穆:ぼく 連:れん 霍:かく 寧:ねい 柯:か 阮:げん 荘:そう 莊:そう 温:おん 藍:らん "
    "簡:かん 游:ゆう 施:し 樊:はん 管:かん 耿:こう 宮:きゅう 梅:ばい 邢:けい 衛:えい 焦:しょう 郎:ろう 卓:たく 項:こう "
    "景:けい 伍:ご 柏:はく 都:と 楽:がく 樂:がく 尤:ゆう 畢:ひつ 解:かい 丘:きゅう 房:ぼう 干:かん 応:おう 應:おう 桂:けい "
    "麦:ばく 班:はん 匡:きょう 時:じ 鞠:きく 竇:とう 蒙:もう 仇:きゅう 寇:こう 靳:きん 褚:ちょ 聶:じょう 巫:ふ 翟:てき")
CJK_SURNAMES = {}  # type: Dict[str, Tuple[str, ...]]
for _tok in _CJK.split():
    _k, _rs = _tok.split(":")
    CJK_SURNAMES[_k] = tuple(_rs.split(","))


def load_bearers(ndl_work):
    # type: (str) -> Dict[Tuple[str, str], collections.Counter]
    """(名の表記, 読み) → Counter({(姓, 姓の読み): 人数})。"""
    out = collections.defaultdict(collections.Counter)  # type: Dict[Tuple[str, str], collections.Counter]
    for path in sorted(glob.glob(os.path.join(ndl_work, "prefix-*.jsonl"))):
        prev = None
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                if r["kind"] == "surname":
                    prev = r
                elif r["kind"] == "given" and prev is not None:
                    out[(r["kanji"], r["reading"])][(prev["kanji"], prev["reading"])] += 1
                    prev = None
    return out


def load_jp_surnames(dataset_dir):
    # type: (str) -> Set[Tuple[str, str]]
    with open(os.path.join(dataset_dir, "last_name_org.csv"), encoding="utf-8") as f:
        return {(r[0], r[2]) for r in csv.reader(f) if len(r) == 4}


def foreign_like(surname, reading, jp_surnames):
    # type: (str, str, Set[Tuple[str, str]]) -> bool
    return reading in CJK_SURNAMES.get(surname, ()) and (surname, reading) not in jp_surnames


def check(findings, bearers, pairs, jp_surnames, min_support=MIN_SUPPORT):
    # type: (Iterable[dict], Dict, Dict[str, dict], Set[Tuple[str, str]], int) -> List[Tuple[dict, List[str], str]]
    """承認済みの add_kanji / add_row のうち該当するもの → [(finding, 不採用の表記, 注記)]。"""
    out = []
    for f in findings:
        if f.get("status") != "approved":
            continue
        action = f["proposed_fix"]["action"]
        if action not in ("add_kanji", "add_row"):
            continue
        cols = f["entry"].split(",")
        reading = cols[0]
        targets = [f["proposed_fix"]["value"]] if action == "add_kanji" else cols[2:]
        bad, notes = [], []
        for k in targets:
            wd = pairs.get("given|%s|%s" % (k, reading), {}).get("wikidata", 0)
            people = bearers.get((k, reading), {})
            total = sum(people.values())
            foreign = sum(n for (s, sr), n in people.items() if foreign_like(s, sr, jp_surnames))
            if wd == 0 and foreign > 0 and total - foreign < min_support:
                bad.append(k)
                notes.append("%s（NDL %d 人中 %d 人が中国・朝鮮系の 1 字姓）" % (k, total, foreign))
        if bad:
            out.append((f, bad, "・".join(notes)))
    return out


def apply(hits):
    # type: (List[Tuple[dict, List[str], str]]) -> Dict[str, int]
    counts = {"rejected": 0, "narrowed": 0}
    for f, bad, note in hits:
        cols = f["entry"].split(",")
        if f["proposed_fix"]["action"] == "add_kanji" or len(bad) == len(cols[2:]):
            f["status"] = "rejected"
            f["evidence"] += "（却下: %s。%s）" % (REASON, note)
            counts["rejected"] += 1
        else:
            f["entry"] = ",".join(cols[:2] + [k for k in cols[2:] if k not in bad])
            f["evidence"] += "（レビューで表記を絞り込み: 除外 %s。%s。%s）" % ("・".join(bad), REASON, note)
            counts["narrowed"] += 1
    return counts


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--ndl-work", required=True, help="fetch_ndl.py の --work（人物単位の prefix-*.jsonl）")
    parser.add_argument("--index", default=os.path.join("qa", "sources", "index.json"))
    parser.add_argument("--dataset-dir", default=os.path.join("japanese_personal_name_dataset", "dataset"))
    parser.add_argument("--min-support", type=int, default=MIN_SUPPORT)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    findings = findings_io.load_findings(args.findings)
    with open(args.index, encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]
    hits = check(findings, load_bearers(args.ndl_work), pairs, load_jp_surnames(args.dataset_dir), args.min_support)
    n_kanji = sum(1 for f, _, _ in hits if f["proposed_fix"]["action"] == "add_kanji")
    print("外国人名の音読みの疑い: add_kanji %d 件 / add_row %d 件" % (n_kanji, len(hits) - n_kanji))
    if args.list:
        for f, _bad, note in hits:
            print("  %s %s — %s" % (f["proposed_fix"]["action"], f["entry"][:40], note))
    if args.apply:
        counts = apply(hits)
        for f in findings:
            problems = findings_io.validate_finding(f)
            if problems:
                raise SystemExit("不正な finding %s: %s" % (f["id"], "; ".join(problems)))
        findings_io.save_findings(args.findings, findings)
        print("台帳を更新: 却下 %d 件 / 表記の絞り込み %d 件" % (counts["rejected"], counts["narrowed"]))
    return 0


if __name__ == "__main__":
    sc.force_utf8_output()
    sys.exit(main())
