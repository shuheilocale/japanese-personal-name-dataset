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
_VALUE_SEP_RE = re.compile(r"[,、]")


def _split_values(value):
    # type: (str) -> list
    """remove_kanji の value を `,` / `、` で分割し strip・空要素除去する。

    triage_server.split_values と同じ規則（"克真, 克麻, 勝真" → 3漢字）。
    """
    return [v.strip() for v in _VALUE_SEP_RE.split(value or "") if v.strip()]


def _read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def _write_lines(path, lines):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


_LAST_NAME_FILE = "last_name_org.csv"


def _find_duplicate_row(lines, reading, exclude_idx=None):
    # type: (list, str, int) -> object
    """`reading`（col0）と同じ読みを持つ行の index を返す（exclude_idx は除外）。

    無ければ None。
    """
    for i, ln in enumerate(lines):
        if i == exclude_idx:
            continue
        if ln.split(",", 1)[0] == reading:
            return i
    return None


def _merge_kanji_cols(existing_cols, new_kanji):
    # type: (list, list) -> list
    """既存行（読み,ローマ字,漢字...）に無い漢字だけを末尾追加する。

    読み・ローマ字は既存行のものを維持する。
    """
    merged = list(existing_cols[2:])
    for k in new_kanji:
        if k not in merged:
            merged.append(k)
    return existing_cols[:2] + merged


def _propagate_merge(evolution, fname, old_line, new_line):
    # type: (dict, str, str, str) -> None
    """マージ先の既存行が変化したことを evolution マップへ反映する。

    マージ先行が既に他の finding の適用対象として追跡されている場合は
    その進化系列を更新する。まだ追跡されていない場合でも、後続の finding が
    マージ前のテキストを entry として参照できるようキーを追加しておく。
    """
    for k, v in list(evolution.items()):
        if k[0] == fname and v == old_line:
            evolution[k] = new_line
    evolution[(fname, old_line)] = new_line


def _apply_one(lines, finding, current_entry):
    # type: (list, dict, str) -> tuple
    """1件適用し (新lines, 移動行 or None, 成功か, 適用後の行 or None,
    失敗理由 or None, マージ更新情報 or None) を返す。

    current_entry は元の finding["entry"] そのもの、または同一行に対する
    それより前の承認済み finding 適用後の行（進化形）。remove_row /
    move_to_file 適用後、および fix_reading が既存行へマージされた場合は
    行が消えるため呼び出し側は None を渡す。

    マージ更新情報は (マージ先の適用前の行, マージ後の行) のタプルで、
    呼び出し側が evolution マップへ反映するために使う。

    名CSV（ひらがな,ローマ字,漢字...）と姓CSV（last_name_org.csv:
    漢字,推定人数,ひらがな,ローマ字）とでは列レイアウトが異なるため、
    fix_romaji / fix_reading で書き換える列インデックスを file で切り替える。
    remove_kanji は姓CSVでは概念が存在しないため常にスキップする。
    fix_reading のマージ統合は名CSVのみ（姓CSVは同じ読みの別の姓が
    正当なため従来どおり単純書き換え）。
    """
    action = finding["proposed_fix"]["action"]
    value = finding["proposed_fix"].get("value", "")
    is_last_name = finding["file"] == _LAST_NAME_FILE
    if action == "remove_kanji" and is_last_name:
        return lines, None, False, current_entry, "remove_kanji は姓CSVでは非対応です", None
    if current_entry is None or current_entry not in lines:
        return lines, None, False, current_entry, "行が見つかりません", None
    idx = lines.index(current_entry)
    if action == "remove_row":
        return lines[:idx] + lines[idx + 1:], None, True, None, None, None
    if action == "move_to_file":
        return lines[:idx] + lines[idx + 1:], current_entry, True, None, None, None
    cols = current_entry.split(",")
    if action == "remove_kanji":
        targets = set(_split_values(value))
        cols = [cols[0], cols[1]] + [k for k in cols[2:] if k not in targets]
    elif action == "fix_romaji":
        cols[3 if is_last_name else 1] = value
    elif action == "add_kanji":
        existing = cols[2:]
        for k in _split_values(value):
            if k not in existing:
                existing.append(k)
        cols = cols[:2] + existing
    elif action == "fix_reading":
        if not is_last_name:
            dup_idx = _find_duplicate_row(lines, value, exclude_idx=idx)
            if dup_idx is not None:
                old_target_line = lines[dup_idx]
                merged_entry = ",".join(_merge_kanji_cols(
                    old_target_line.split(","), cols[2:]))
                lines[dup_idx] = merged_entry
                del lines[idx]
                return (lines, None, True, None, None,
                        (old_target_line, merged_entry))
        cols[2 if is_last_name else 0] = value
    elif action == "none":
        return lines, None, True, current_entry, None, None
    new_entry = ",".join(cols)
    lines[idx] = new_entry
    return lines, None, True, new_entry, None, None


def _preview_merge_note(file_lines, action, value, fname, current_entry, dataset_dir):
    # type: (dict, str, str, str, str, str) -> str
    """dry-run 表示用に、この適用が既存行へのマージになる場合の付記を返す。

    fix_reading（名CSVのみ）は変更後の読み、move_to_file は移動元の読みで
    移動先ファイルの既存行を探す。マージにならない場合は空文字列。
    """
    lines = file_lines.get(fname, [])
    if current_entry is None or current_entry not in lines:
        return ""
    if action == "fix_reading" and fname != _LAST_NAME_FILE:
        idx = lines.index(current_entry)
        if _find_duplicate_row(lines, value, exclude_idx=idx) is not None:
            return "（既存行 %s に統合）" % value
    elif action == "move_to_file":
        target = value
        if target not in file_lines:
            file_lines[target] = _read_lines(os.path.join(dataset_dir, target))
        reading = current_entry.split(",")[0]
        if _find_duplicate_row(file_lines[target], reading) is not None:
            return "（既存行 %s に統合）" % reading
    return ""


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
        if fname not in file_lines:
            file_lines[fname] = _read_lines(os.path.join(dataset_dir, fname))
        if d["proposed_fix"]["action"] == "add_row":
            new_cols = d["entry"].split(",")
            reading = new_cols[0]
            lines = file_lines[fname]
            dup_idx = _find_duplicate_row(lines, reading)
            if dup_idx is not None:
                merged = _merge_kanji_cols(lines[dup_idx].split(","), new_cols[2:])
                old_line = lines[dup_idx]
                lines[dup_idx] = ",".join(merged)
                _propagate_merge(evolution, fname, old_line, lines[dup_idx])
                print("適用: %s（既存行 %s に統合）" % (d["id"], reading))
            else:
                keys = [ln.split(",")[0] for ln in lines]
                lines.insert(bisect.bisect_left(keys, reading), d["entry"])
                print("適用: %s（行を追加）" % d["id"])
            d["status"] = "applied"
            applied += 1
            continue
        key = (fname, d["entry"])
        current_entry = evolution.get(key, d["entry"])
        merge_note = _preview_merge_note(file_lines, action, value,
                                          fname, current_entry, dataset_dir)
        print("適用予定: id=%s action=%s value=%s file=%s%s"
              % (d["id"], action, value or "(なし)", fname, merge_note))
        new_lines, moved, ok, new_entry, reason, merge_update = _apply_one(
            file_lines[fname], d, current_entry)
        if not ok:
            skipped.append(d["id"])
            print("スキップ（%s）: %s" % (reason or "行が見つかりません", d["id"]))
            continue
        file_lines[fname] = new_lines
        evolution[key] = new_entry
        if merge_update is not None:
            _propagate_merge(evolution, fname, merge_update[0], merge_update[1])
        if moved is not None:
            moves.append((d["proposed_fix"]["value"], moved))
        d["status"] = "applied"
        applied += 1
    for target, raw in moves:
        if target not in file_lines:
            file_lines[target] = _read_lines(os.path.join(dataset_dir, target))
        reading = raw.split(",")[0]
        dup_idx = _find_duplicate_row(file_lines[target], reading)
        if dup_idx is not None:
            old_target_line = file_lines[target][dup_idx]
            merged_entry = ",".join(_merge_kanji_cols(
                old_target_line.split(","), raw.split(",")[2:]))
            file_lines[target][dup_idx] = merged_entry
            _propagate_merge(evolution, target, old_target_line, merged_entry)
        else:
            keys = [ln.split(",")[0] for ln in file_lines[target]]
            pos = bisect.bisect_left(keys, reading)
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


def _force_utf8_output():
    # type: () -> None
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    _force_utf8_output()
    sys.exit(main())
