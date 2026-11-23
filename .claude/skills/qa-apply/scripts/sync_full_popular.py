"""完全版（*_org.csv）と最適化版（*_opti.csv）で、表記・行を外す判断を揃える finding を台帳に追加する。

レビューは完全版と最適化版の行を別々に判定するので、同じ表記が片方でだけ外される（opti ⊆ org が崩れ、
validate が「org 版にない漢字」を警告する）。承認済みの remove_kanji / remove_row を両ファイルの
和集合として扱い、片方にだけ付いた判断をもう片方にも cross_file_inconsistency の finding（approved）として足す。
apply_findings.py の前に実行する。再実行しても同じ結果になる（このスクリプトが足した finding は作り直す）。

  python3 sync_full_popular.py --findings qa/findings/<run-id>.jsonl \\
    --dataset-dir japanese_personal_name_dataset/dataset
"""
import argparse
import csv
import datetime
import os
import re
import sys
from typing import Dict, List, Optional, Set

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "validate-dataset", "scripts")))

import findings_io  # noqa: E402

DETECTED_BY = "qa-apply/sync_full_popular v1"
PAIRS = [("first_name_man_org.csv", "first_name_man_opti.csv"),
         ("first_name_woman_org.csv", "first_name_woman_opti.csv")]
_SEP = re.compile(r"[,、]")


def _rows(path):
    # type: (str) -> Dict[str, List[str]]
    with open(path, encoding="utf-8") as f:
        return {r[0]: r for r in csv.reader(f) if r}


def _finding(dst, row, src, action, value, need, today):
    # type: (str, List[str], str, str, str, List[str], str) -> dict
    if need:
        evidence = "%s で同じ表記を外す判断（承認済み）に揃える: %s" % (src, "・".join(need))
    else:
        evidence = "%s で行を削除する判断（承認済み）に揃える" % src
    return {
        "id": "%s:%s:cross_file_inconsistency" % (dst, row[0]), "file": dst, "entry": ",".join(row),
        "check": "cross_file_inconsistency", "severity": "warning", "confidence": "medium",
        "evidence": evidence,
        "proposed_fix": {"action": action, "value": value}, "status": "approved",
        "detected_at": today, "detected_by": DETECTED_BY,
    }


def sync(findings, dataset_dir, today=None):
    # type: (List[dict], str, Optional[str]) -> List[dict]
    """同期用の finding を除いた findings と、新しく作った同期用 finding を合わせて返す。"""
    today = today or datetime.date.today().isoformat()
    base = [f for f in findings if f.get("detected_by") != DETECTED_BY]
    added = []  # type: List[dict]
    for org, opti in PAIRS:
        data = {fn: _rows(os.path.join(dataset_dir, fn)) for fn in (org, opti)}
        kan = {org: {}, opti: {}}  # type: Dict[str, Dict[str, Set[str]]]
        rowrm = {org: set(), opti: set()}  # type: Dict[str, Set[str]]
        for f in base:
            if f.get("status") != "approved" or f["file"] not in kan:
                continue
            reading = f["entry"].split(",")[0]
            action = f["proposed_fix"]["action"]
            if action == "remove_kanji":
                for k in _SEP.split(f["proposed_fix"].get("value", "")):
                    if k.strip():
                        kan[f["file"]].setdefault(reading, set()).add(k.strip())
            elif action == "remove_row":
                rowrm[f["file"]].add(reading)
        for src, dst in ((org, opti), (opti, org)):
            done = set()  # type: Set[str]
            for reading in sorted(rowrm[src]):
                row = data[dst].get(reading)
                if row is not None and reading not in rowrm[dst]:
                    added.append(_finding(dst, row, src, "remove_row", "", [], today))
                    done.add(reading)
            for reading, ks in sorted(kan[src].items()):
                row = data[dst].get(reading)
                if row is None or reading in rowrm[dst] or reading in done:
                    continue
                need = [k for k in row[2:] if k in ks and k not in kan[dst].get(reading, set())]
                if not need:
                    continue
                remaining = [k for k in row[2:] if k not in ks and k not in kan[dst].get(reading, set())]
                if remaining:
                    added.append(_finding(dst, row, src, "remove_kanji", "、".join(need), need, today))
                else:
                    added.append(_finding(dst, row, src, "remove_row", "", need, today))
    ids = [f["id"] for f in added]
    if len(ids) != len(set(ids)):
        raise ValueError("同期用 finding の id が重複しています")
    return base + added


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--dataset-dir", default=os.path.join("japanese_personal_name_dataset", "dataset"))
    args = parser.parse_args()
    findings = sync(findings_io.load_findings(args.findings), args.dataset_dir)
    for f in findings:
        problems = findings_io.validate_finding(f)
        if problems:
            raise SystemExit("不正な finding %s: %s" % (f["id"], "; ".join(problems)))
    findings_io.save_findings(args.findings, findings)
    added = [f for f in findings if f.get("detected_by") == DETECTED_BY]
    by = {}  # type: Dict[str, int]
    for f in added:
        key = "%s %s" % (f["file"], f["proposed_fix"]["action"])
        by[key] = by.get(key, 0) + 1
    print("同期用 finding %d 件" % len(added))
    for k, n in sorted(by.items()):
        print("  %s: %d" % (k, n))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure") and (_s.encoding or "").lower() not in ("utf-8", "utf8"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
