"""レビュアー（サブエージェント）が書いた判定ファイルから、qa_batch.py merge が読む結果ファイルを作る。

レビュアーは疑義だけを <work-dir>/decisions/<batch_id>.json に書く。行の書き写し（entry）と
「問題なし」の一覧（ok_hashes）はバッチファイルから機械的に埋めるので、書き写しの誤りや漏れで
バッチが不正・未完了になることがない。不正があれば理由を表示して終了コード 1 で終わる（結果ファイルは書かない）。

  python3 review_result.py --work-dir qa/work/<run-id> <batch_id>

判定ファイルの形:
  {"batch_id": "...", "findings": [
     {"hash": "<エントリの hash>", "check": "kanji_reading_mismatch | not_a_name | wrong_gender_file | romaji_reading_mismatch",
      "confidence": "high | medium | low", "evidence": "<日本語の根拠>",
      "action": "remove_kanji | remove_row | fix_romaji | fix_reading | move_to_file | none", "value": "<対象値>"}]}
"""
import argparse
import datetime
import json
import os
import re
import sys
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "validate-dataset", "scripts")))

import findings_io  # noqa: E402

CHECKS = {"kanji_reading_mismatch", "not_a_name", "wrong_gender_file", "romaji_reading_mismatch"}
ACTIONS = {"remove_row", "remove_kanji", "fix_romaji", "fix_reading", "move_to_file", "none"}
DETECTED_BY = "qa-review v1"
_SEP = re.compile(r"[,、]")
_SENT = re.compile(r"[^。]+")
_PAREN = re.compile(r"([^、。（）]*)（([^（）]*JMnedict[^（）]*)）")
_JM_READING = re.compile(r"JMnedict\s*(も|では|には|に|の|で)\s*[「『]?[ぁ-ゖー]{2,}")
_JM_PRESENCE = re.compile(r"JMnedict\s*(に|には|にも)\s*(収録|用例|裏付け|ある|あり|ない|なし|無)")
_JM_ALL = re.compile(r"JMnedict\s*の\s*(いずれ|どれ|どちら|すべて|全体)")


def jmnedict_leak(evidence):
    # type: (str) -> Optional[str]
    """JMnedict（照合専用・CC BY-SA）由来の表記・読みの組が書かれていそうな箇所を返す。無ければ None。

    許すのは「NDL・Wikidata・JMnedict のいずれにも用例がない」「JMnedict に収録あり」のような有無の記述だけ。
    検出は控えめな規則なので、最終的な確認は人が行う。
    """
    for m in _PAREN.finditer(evidence):
        if any(c in m.group(1) + m.group(2) for c in "=＝"):
            return m.group(0)[-40:]
    for m in _SENT.finditer(evidence):
        for clause in re.split(r"[、（）]", m.group(0)):
            if "JMnedict" in clause and any(c in clause for c in "=＝"):
                return clause[-40:]
            if _JM_READING.search(clause) and not _JM_PRESENCE.search(clause) and not _JM_ALL.search(clause):
                return clause[-40:]
    return None


def build_result(batch, decisions, today=None):
    # type: (dict, dict, Optional[str]) -> Tuple[Optional[dict], List[str]]
    """→ (結果ファイルの dict, エラー一覧)。エラーがあれば結果は None。"""
    today = today or datetime.date.today().isoformat()
    entries = batch["entries"]
    by_hash = {e["hash"]: e for e in entries}
    errors, findings, seen = [], [], set()
    for i, d in enumerate(decisions.get("findings", [])):
        where = "findings[%d]" % i
        e = by_hash.get(d.get("hash"))
        if e is None:
            errors.append("%s: hash がこのバッチに無い: %r" % (where, d.get("hash")))
            continue
        where += "（%s %s）" % (e["file"], e["reading"])
        check, action, value = d.get("check"), d.get("action"), d.get("value", "") or ""
        if check not in CHECKS:
            errors.append("%s: check が不正: %r" % (where, check))
            continue
        if action not in ACTIONS:
            errors.append("%s: action が不正: %r" % (where, action))
            continue
        if action == "remove_kanji":
            targets = [v.strip() for v in _SEP.split(value) if v.strip()]
            row_kanji = e.get("kanji") if isinstance(e.get("kanji"), list) else []
            unknown = [k for k in targets if k not in row_kanji]
            if not targets or unknown:
                errors.append("%s: remove_kanji の value がこの行の表記でない: %r" % (where, unknown or value))
                continue
            if len(set(targets)) == len(set(row_kanji)):
                errors.append("%s: 行の全表記を外すなら remove_row を使う" % where)
                continue
            value = "、".join(targets)
        fid = "%s:%s:%s" % (e["file"], e["reading"], check)
        if fid in seen:
            errors.append("%s: 同じ行・同じ check の finding が 2 つある（1 つにまとめ、remove_kanji の value は「、」で並べる）" % where)
            continue
        seen.add(fid)
        finding = {
            "id": fid, "file": e["file"], "entry": e["raw"], "check": check, "severity": "error",
            "confidence": d.get("confidence"), "evidence": str(d.get("evidence") or ""),
            "proposed_fix": {"action": action, "value": value}, "status": "pending",
            "detected_at": today, "detected_by": DETECTED_BY,
        }
        problems = findings_io.validate_finding(finding)
        if not finding["evidence"].strip():
            problems.append("evidence が空です")
        leak = jmnedict_leak(finding["evidence"])
        if leak:
            problems.append("evidence に JMnedict 由来の表記・読みが書かれている（「収録あり／なし」だけにする）: …%s…" % leak)
        if problems:
            errors.append("%s: %s" % (where, "; ".join(problems)))
            continue
        findings.append(finding)
    if errors:
        return None, errors
    flagged = {findings_io.entry_hash(f["file"], f["entry"]) for f in findings}
    ok = [e["hash"] for e in entries if e["hash"] not in flagged]
    return {"batch_id": batch["batch_id"], "findings": findings, "ok_hashes": ok}, []


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work-dir", required=True, help="qa_batch.py prep の --out-dir")
    parser.add_argument("batch_id")
    args = parser.parse_args()
    with open(os.path.join(args.work_dir, args.batch_id + ".json"), encoding="utf-8") as f:
        batch = json.load(f)
    with open(os.path.join(args.work_dir, "decisions", args.batch_id + ".json"), encoding="utf-8") as f:
        decisions = json.load(f)
    result, errors = build_result(batch, decisions)
    if errors:
        print("エラー %d 件（結果ファイルは書いていません）:" % len(errors))
        for s in errors:
            print("  " + s)
        return 1
    os.makedirs(os.path.join(args.work_dir, "results"), exist_ok=True)
    with open(os.path.join(args.work_dir, "results", args.batch_id + ".json"), "w",
              encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    n_rows = len({f["entry"] for f in result["findings"]})
    print("OK: %s 疑義 %d 件（%d 行） / 問題なし %d 行 / 全 %d 行" % (
        args.batch_id, len(result["findings"]), n_rows, len(result["ok_hashes"]), len(batch["entries"])))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure") and (_s.encoding or "").lower() not in ("utf-8", "utf8"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
