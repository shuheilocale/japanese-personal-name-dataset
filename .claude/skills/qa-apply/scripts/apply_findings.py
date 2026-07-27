"""承認済み findings を dataset CSV に一括適用する。

必ずユーザーの明示承認を得てから実行すること（CLAUDE.md のデータ保護方針）。
status==approved のみ適用し、適用後は applied に更新する。
rejected の finding はエントリを verified.json に登録し再検出を防ぐ。
"""
import argparse
import bisect
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "validate-dataset", "scripts")))

import findings_io  # noqa: E402

_REPORT_CHECKED_RE = re.compile(r"^- \[x\] `([^`]+)`", re.IGNORECASE)


def _read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def _write_lines(path, lines):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def _apply_one(lines, finding, current_entry):
    # type: (list, dict, str) -> tuple
    """1件適用し (新lines, 移動行 or None, 成功か, 適用後の行 or None) を返す。

    current_entry は元の finding["entry"] そのもの、または同一行に対する
    それより前の承認済み finding 適用後の行（進化形）。remove_row /
    move_to_file 適用後は行が消えるため呼び出し側は None を渡す。
    """
    action = finding["proposed_fix"]["action"]
    value = finding["proposed_fix"].get("value", "")
    if current_entry is None or current_entry not in lines:
        return lines, None, False, current_entry
    idx = lines.index(current_entry)
    if action == "remove_row":
        return lines[:idx] + lines[idx + 1:], None, True, None
    if action == "move_to_file":
        return lines[:idx] + lines[idx + 1:], current_entry, True, None
    cols = current_entry.split(",")
    if action == "remove_kanji":
        cols = [cols[0], cols[1]] + [k for k in cols[2:] if k != value]
    elif action == "fix_romaji":
        cols[1] = value
    elif action == "fix_reading":
        cols[0] = value
    elif action == "none":
        return lines, None, True, current_entry
    new_entry = ",".join(cols)
    lines[idx] = new_entry
    return lines, None, True, new_entry


def apply(findings_path, dataset_dir, qa_dir, report_path=None, dry_run=False):
    # type: (str, str, str, str, bool) -> dict
    findings = findings_io.load_findings(findings_path)
    if report_path:
        checked = set()
        for line in _read_lines(report_path):
            m = _REPORT_CHECKED_RE.match(line.strip())
            if m:
                checked.add(m.group(1))
        for d in findings:
            if d["id"] in checked and d["status"] == "pending":
                d["status"] = "approved"
    applied = 0
    skipped = []
    file_lines = {}  # type: dict
    # (file, 元entry) -> 現在の行（同一行への複数 findings 適用を追跡）。
    # remove_row / move_to_file 適用後は行が消えるため None を保持する。
    evolution = {}  # type: dict
    moves = []  # (target_file, raw_line)
    for d in findings:
        if d["status"] != "approved":
            continue
        fname = d["file"]
        action = d["proposed_fix"]["action"]
        value = d["proposed_fix"].get("value", "")
        print("適用予定: id=%s action=%s value=%s file=%s"
              % (d["id"], action, value or "(なし)", fname))
        if fname not in file_lines:
            file_lines[fname] = _read_lines(os.path.join(dataset_dir, fname))
        key = (fname, d["entry"])
        current_entry = evolution.get(key, d["entry"])
        new_lines, moved, ok, new_entry = _apply_one(
            file_lines[fname], d, current_entry)
        if not ok:
            skipped.append(d["id"])
            print("スキップ（行が見つかりません）: %s" % d["id"])
            continue
        file_lines[fname] = new_lines
        evolution[key] = new_entry
        if moved is not None:
            moves.append((d["proposed_fix"]["value"], moved))
        d["status"] = "applied"
        applied += 1
    for target, raw in moves:
        if target not in file_lines:
            file_lines[target] = _read_lines(os.path.join(dataset_dir, target))
        keys = [ln.split(",")[0] for ln in file_lines[target]]
        pos = bisect.bisect_left(keys, raw.split(",")[0])
        file_lines[target].insert(pos, raw)
    rejected = [d for d in findings if d["status"] == "rejected"]
    if not dry_run:
        for fname, lines in file_lines.items():
            _write_lines(os.path.join(dataset_dir, fname), lines)
        findings_io.save_findings(findings_path, findings)
        if rejected:
            verified_path = os.path.join(qa_dir, "verified.json")
            verified = findings_io.load_verified(verified_path)
            today = datetime.date.today().isoformat()
            for d in rejected:
                h = findings_io.entry_hash(d["file"], d["entry"])
                verified[h] = {"file": d["file"],
                               "reading": d["entry"].split(",")[0],
                               "verified_at": today}
            findings_io.save_verified(verified_path, verified)
    return {"applied": applied, "skipped": skipped,
            "rejected_verified": len(rejected)}


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--qa-dir", required=True)
    parser.add_argument("--from-report")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = apply(args.findings, args.dataset_dir, args.qa_dir,
                   report_path=args.from_report, dry_run=args.dry_run)
    mode = "（dry-run）" if args.dry_run else ""
    print("適用 %d 件%s / スキップ %d 件 / rejected→verified %d 件"
          % (result["applied"], mode, len(result["skipped"]),
             result["rejected_verified"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
