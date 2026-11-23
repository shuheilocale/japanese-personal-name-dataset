"""過去の更新ラウンドの判断を新しい候補台帳に引き継ぎ、決定的に却下できるものを却下する。

レビュー（LLM・人）に回す前に実行する。却下するのは次の 3 種類で、どれも pending / approved のものだけが対象（冪等）:

1. 以前の台帳で rejected になったのと同じ id の候補
2. 以前の台帳で add_row を適用するときに表記を絞り込んで外した表記を、同じ読みへ add_kanji で再提案する候補
3. 表記の性別クラス（Wikidata）が追加先ファイルと矛盾する add_kanji（evidence に「矛盾」の注記があるもの）

  python3 prior_decisions.py --findings qa/findings/<run-id>.jsonl \\
    --previous qa/findings/2026-09-update.jsonl qa/findings/2026-11-update.jsonl
"""
import argparse
import os
import re
import sys
from typing import Iterable, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "validate-dataset", "scripts")))

import findings_io  # noqa: E402
import sources_common as sc  # noqa: E402

NARROW_RE = re.compile(r"レビューで表記を絞り込み: 除外 ([^。）]+)")
REASON_PREV_REJECTED = "rule: 以前の更新ラウンドで却下済み"
REASON_PREV_NARROWED = "rule: 以前の更新ラウンドで行追加から除外した表記"
REASON_GENDER_CONFLICT = "rule: 表記の性別クラスが追加先ファイルと矛盾"


def apply_rules(findings, previous):
    # type: (List[dict], Iterable[dict]) -> List[Tuple[str, str]]
    """findings をその場で更新し、(id, 理由) の一覧を返す。"""
    prev_rejected = set()
    excluded = set()
    for d in previous:
        if d.get("status") == "rejected":
            prev_rejected.add(d["id"])
        m = NARROW_RE.search(d.get("evidence") or "")
        if m and d.get("status") == "applied":
            reading = d["entry"].split(",")[0]
            for k in m.group(1).split("・"):
                excluded.add((d["file"], reading, k.strip()))
    log = []
    for f in findings:
        if f.get("status") not in ("pending", "approved"):
            continue
        action = f["proposed_fix"]["action"]
        reading = f["entry"].split(",")[0]
        reason = None
        if f["id"] in prev_rejected:
            reason = REASON_PREV_REJECTED
        elif action == "add_kanji" and (f["file"], reading, f["proposed_fix"]["value"]) in excluded:
            reason = REASON_PREV_NARROWED
        elif action == "add_kanji" and "矛盾" in (f.get("evidence") or ""):
            reason = REASON_GENDER_CONFLICT
        if reason:
            f["status"] = "rejected"
            f["evidence"] = (f.get("evidence") or "") + "（却下: %s）" % reason
            log.append((f["id"], reason))
    return log


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--findings", required=True, help="今回の候補台帳（上書きする）")
    parser.add_argument("--previous", nargs="*", default=[], help="以前の更新ラウンドの台帳")
    args = parser.parse_args()
    findings = findings_io.load_findings(args.findings)
    previous = []  # type: List[dict]
    for p in args.previous:
        if os.path.abspath(p) != os.path.abspath(args.findings):
            previous.extend(findings_io.load_findings(p))
    log = apply_rules(findings, previous)
    findings_io.save_findings(args.findings, findings)
    counts = {}  # type: dict
    for _, reason in log:
        counts[reason] = counts.get(reason, 0) + 1
    print("ルールで却下 %d 件" % len(log))
    for reason, n in sorted(counts.items()):
        print("  %s: %d" % (reason, n))
    return 0


if __name__ == "__main__":
    sc.force_utf8_output()
    sys.exit(main())
