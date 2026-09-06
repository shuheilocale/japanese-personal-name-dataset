"""NDL にしか無い新規読みの性別をサブエージェントに判定させるためのバッチ準備・結果マージ。

判定以外（分割・スキーマ検証・findings 生成）は決定的に行う。判定結果は
results/gbatch_NNN.json = {"batch_id": ..., "decisions": {"読み": "male|female|unisex|unknown"}}。
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "validate-dataset", "scripts")))

import findings_io  # noqa: E402
import generate_candidates as gc  # noqa: E402

DECISIONS = ("male", "female", "unisex", "unknown")
# generate_candidates の再実行で台帳から消されないよう、出自を generate と区別する
DETECTED_BY = "qa-update/gender_batch v1"


def prep(pending_path, out_dir, batch_size=100):
    # type: (str, str, int) -> dict
    with open(pending_path, encoding="utf-8") as f:
        pending = json.load(f)
    os.makedirs(out_dir, exist_ok=True)
    batch_ids = []
    for i in range(0, len(pending), batch_size):
        bid = "gbatch_%03d" % (len(batch_ids) + 1)
        batch_ids.append(bid)
        with open(os.path.join(out_dir, bid + ".json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump({"batch_id": bid, "entries": pending[i:i + batch_size]}, f, ensure_ascii=False, indent=1)
    manifest = {"batch_ids": batch_ids, "total": len(pending)}
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    return manifest


def merge(out_dir, findings_path, today=None):
    # type: (str, str, str) -> dict
    today = today or datetime.date.today().isoformat()
    with open(os.path.join(out_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    existing = findings_io.load_findings(findings_path) if os.path.exists(findings_path) else []
    known = {d["id"] for d in existing}
    added, missing, invalid = [], [], []
    for bid in manifest["batch_ids"]:
        with open(os.path.join(out_dir, bid + ".json"), encoding="utf-8") as f:
            entries = {e["reading"]: e for e in json.load(f)["entries"]}
        rpath = os.path.join(out_dir, "results", bid + ".json")
        if not os.path.exists(rpath):
            missing.append(bid)
            continue
        with open(rpath, encoding="utf-8") as f:
            result = json.load(f)
        decisions = result.get("decisions", {})
        if not isinstance(decisions, dict) or any(v not in DECISIONS for v in decisions.values()):
            invalid.append(bid)
            continue
        for reading, gender in decisions.items():
            e = entries.get(reading)
            if not e or gender not in gc.GENDER_FILES:
                continue
            entry = ",".join([reading, gc.romaji_for(reading)] + e["kanji"])
            for fn in gc.GENDER_FILES[gender]:
                d = gc._finding(fn, entry, "add_row", "", e["sources"], "pending", today,
                                extra_evidence="（性別: LLM 判定 %s）" % gender, detected_by=DETECTED_BY)
                if d["id"] not in known:
                    added.append(d)
                    known.add(d["id"])
    if added:
        findings_io.save_findings(findings_path, existing + added)
    summary = {"added": len(added), "missing_batches": missing, "invalid_batches": invalid}
    print("追加 %d 件 / 未処理 %s / 不正 %s" % (len(added), missing or "なし", invalid or "なし"))
    return summary


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prep")
    p.add_argument("--pending", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--batch-size", type=int, default=100)
    m = sub.add_parser("merge")
    m.add_argument("--out-dir", required=True)
    m.add_argument("--findings", required=True)
    args = parser.parse_args()
    if args.command == "prep":
        mf = prep(args.pending, args.out_dir, args.batch_size)
        print("バッチ %d 個 / 読み %d 件" % (len(mf["batch_ids"]), mf["total"]))
    else:
        merge(args.out_dir, args.findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
