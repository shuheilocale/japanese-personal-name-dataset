"""LLM 品質レビューのバッチ準備（prep）と結果マージ（merge）。

LLM の判定以外の全処理（対象選定・分割・スキーマ検証・台帳更新・レポート生成）
を決定的に行う。サブエージェントは batch_*.json を読んで results/ に書くだけ。
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "validate-dataset", "scripts")))

import checks  # noqa: E402
import findings_io  # noqa: E402

FIRST_NAME_FILES = [
    "first_name_man_org.csv",
    "first_name_man_opti.csv",
    "first_name_woman_org.csv",
    "first_name_woman_opti.csv",
]
LAST_NAME_FILES = ["last_name_org.csv"]


def _entries_for_file(filename, rows, kind):
    det = {f.line: f.message
           for f in checks.check_romaji_reading(filename, rows, kind)}
    entries = []
    for lineno, row in enumerate(rows, start=1):
        if not row or len(row) < 2:
            continue
        raw = ",".join(row)
        if kind == "first":
            reading, romaji_str, kanji = row[0], row[1], row[2:]
        else:
            if len(row) != 4:
                continue
            reading, romaji_str, kanji = row[2], row[3], [row[0]]
        entries.append({
            "file": filename, "line": lineno, "raw": raw,
            "reading": reading, "romaji": romaji_str, "kanji": kanji,
            "hash": findings_io.entry_hash(filename, raw),
            "deterministic_error": det.get(lineno),
        })
    return entries


def prep(dataset_dir, qa_dir, out_dir, batch_size=100):
    # type: (str, str, str, int) -> dict
    verified = findings_io.load_verified(os.path.join(qa_dir, "verified.json"))
    todo = []
    skipped = 0
    style_stats = {}
    for filename in FIRST_NAME_FILES + LAST_NAME_FILES:
        rows = checks.load_rows(os.path.join(dataset_dir, filename))
        kind = "last" if filename in LAST_NAME_FILES else "first"
        style_stats[filename] = checks.romaji_style_stats(rows, kind)
        for e in _entries_for_file(filename, rows, kind):
            if e["hash"] in verified:
                skipped += 1
            else:
                todo.append(e)
    os.makedirs(out_dir, exist_ok=True)
    batch_ids = []
    for i in range(0, len(todo), batch_size):
        batch_id = "batch_%03d" % (len(batch_ids) + 1)
        batch_ids.append(batch_id)
        with open(os.path.join(out_dir, batch_id + ".json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": batch_id, "entries": todo[i:i + batch_size]},
                      f, ensure_ascii=False, indent=1)
    manifest = {"batch_ids": batch_ids, "total_entries": len(todo),
                "skipped_verified": skipped, "style_stats": style_stats}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    return manifest


def merge(qa_dir, work_dir, run_id):
    # type: (str, str, str) -> dict
    manifest = json.load(open(os.path.join(work_dir, "manifest.json"),
                              encoding="utf-8"))
    results_dir = os.path.join(work_dir, "results")
    all_findings = []
    ok_hash_info = {}
    missing = []
    invalid = []
    hash_to_entry = {}
    for batch_id in manifest["batch_ids"]:
        batch = json.load(open(os.path.join(work_dir, batch_id + ".json"),
                               encoding="utf-8"))
        for e in batch["entries"]:
            hash_to_entry[e["hash"]] = e
        result_path = os.path.join(results_dir, batch_id + ".json")
        if not os.path.exists(result_path):
            missing.append(batch_id)
            continue
        result = json.load(open(result_path, encoding="utf-8"))
        problems = []
        for d in result.get("findings", []):
            problems.extend(findings_io.validate_finding(d))
        if problems:
            invalid.append(batch_id)
            continue
        all_findings.extend(result.get("findings", []))
        for h in result.get("ok_hashes", []):
            ok_hash_info[h] = hash_to_entry.get(h)
    flagged_hashes = set()
    for d in all_findings:
        flagged_hashes.add(findings_io.entry_hash(d["file"], d["entry"]))
    today = datetime.date.today().isoformat()
    verified_path = os.path.join(qa_dir, "verified.json")
    verified = findings_io.load_verified(verified_path)
    for h, e in ok_hash_info.items():
        if h in flagged_hashes or e is None:
            continue
        verified[h] = {"file": e["file"], "reading": e["reading"],
                       "verified_at": today}
    findings_io.save_verified(verified_path, verified)
    if all_findings:
        findings_io.append_findings(
            os.path.join(qa_dir, "findings", run_id + ".jsonl"), all_findings)
    summary = {"run_id": run_id, "findings": len(all_findings),
               "verified_added": len(ok_hash_info), "missing_batches": missing,
               "invalid_batches": invalid}
    _write_report(qa_dir, run_id, today, manifest, all_findings, summary)
    return summary


def _write_report(qa_dir, run_id, today, manifest, all_findings, summary):
    lines = [
        "# QA レビューレポート %s" % run_id,
        "",
        "- 実行日: %s" % today,
        "- レビュー対象: %d 件（検証済みスキップ %d 件）"
        % (manifest["total_entries"], manifest["skipped_verified"]),
        "- 疑義: %d 件 / OK: %d 件" % (len(all_findings), summary["verified_added"]),
        "",
        "## ローマ字表記方式の分布（全行対象）",
        "",
    ]
    for fname in sorted(manifest.get("style_stats", {})):
        st = manifest["style_stats"][fname]
        lines.append("- %s: %s" % (fname, " ".join("%s=%d" % kv for kv in sorted(st.items()))))
    lines += [
        "",
        "## 承認方法",
        "",
        "疑義を承認するには下のチェックボックスを `[x]` にして /qa-apply を実行"
        "（または findings JSONL の status を直接編集）。",
        "",
        "## 疑義一覧",
        "",
    ]
    for d in all_findings:
        lines.append("- [ ] `%s` **%s** (%s/%s): %s → 提案: %s %s"
                     % (d["id"], d["check"], d["severity"], d["confidence"],
                        d["evidence"], d["proposed_fix"]["action"],
                        d["proposed_fix"].get("value", "")))
    if summary["missing_batches"] or summary["invalid_batches"]:
        lines += ["", "## 未処理バッチ（再実行が必要）", ""]
        for b in summary["missing_batches"]:
            lines.append("- %s（結果ファイルなし）" % b)
        for b in summary["invalid_batches"]:
            lines.append("- %s（結果がスキーマ不正）" % b)
    reports_dir = os.path.join(qa_dir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    with open(os.path.join(reports_dir, run_id + ".md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--dataset-dir", required=True)
    p.add_argument("--qa-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--batch-size", type=int, default=100)
    m = sub.add_parser("merge")
    m.add_argument("--qa-dir", required=True)
    m.add_argument("--work-dir", required=True)
    m.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if args.command == "prep":
        manifest = prep(args.dataset_dir, args.qa_dir, args.out_dir,
                        args.batch_size)
        print("バッチ %d 個 / 対象 %d 件 / スキップ %d 件"
              % (len(manifest["batch_ids"]), manifest["total_entries"],
                 manifest["skipped_verified"]))
    else:
        summary = merge(args.qa_dir, args.work_dir, args.run_id)
        print("疑義 %d 件 / verified 追加 %d 件 / 未処理 %s / 不正 %s"
              % (summary["findings"], summary["verified_added"],
                 summary["missing_batches"] or "なし",
                 summary["invalid_batches"] or "なし"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
