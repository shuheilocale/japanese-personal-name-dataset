"""統一索引と現データの差分から findings（add_row / add_kanji / 姓の照合）を生成する。

ポリシーは docs/superpowers/specs/2026-09-05-update-pipeline-design.md §4 に従う。
"""
import argparse
import datetime
import json
import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_kanji_list as bk  # noqa: E402
import source_index as si  # noqa: E402
import sources_common as sc  # noqa: E402
import findings_io  # noqa: E402
import romaji  # noqa: E402
from checks import load_rows  # noqa: E402

MAN, WOMAN, LAST = "first_name_man_org.csv", "first_name_woman_org.csv", "last_name_org.csv"
GENDER_FILES = {"male": [MAN], "female": [WOMAN], "unisex": [MAN, WOMAN]}


def load_dataset(dataset_dir):
    # type: (str) -> dict
    ds = {"_romaji": {}, "_surname_rows": {}}
    for fn in (MAN, WOMAN):
        ds[fn] = {}
        for r in load_rows(os.path.join(dataset_dir, fn)):
            if len(r) >= 2:
                ds[fn][r[0]] = r[2:]
                ds["_romaji"][(fn, r[0])] = r[1]
    ds["surnames"] = {}
    for r in load_rows(os.path.join(dataset_dir, LAST)):
        if len(r) == 4:
            ds["surnames"][r[0]] = r[2]
            ds["_surname_rows"].setdefault(r[0], []).append(r)
    return ds


def romaji_for(reading):
    # type: (str) -> str
    cands = romaji._combine(romaji._alternatives(romaji.tokenize(reading), "keep"))
    pref = sorted(c for c in cands if "'" not in c) or sorted(cands)
    return pref[0]


def _evidence(sup):
    # type: (dict) -> str
    return "NDL %d人 / Wikidata %d人 / JMnedict %s" % (sup["ndl"], sup["wikidata"], "✓" if sup["jmnedict"] else "-")


def _finding(file, entry, action, value, sup, status, today, check="missing_entry", confidence="high",
             extra_evidence=""):
    # type: (...) -> dict
    # 名ファイルは entry の1列目が読み、姓ファイルは1列目が漢字。add_kanji は同一
    # (file, key) に複数候補があり得るため value（追加する漢字）を id に含めて一意化する。
    key = entry.split(",")[0]
    if action == "add_kanji":
        fid = "%s:%s:%s:%s:%s" % (file, key, check, action, value)
    else:
        fid = "%s:%s:%s:%s" % (file, key, check, action)
    return {
        "id": fid, "file": file, "entry": entry,
        "check": check, "severity": "warning", "confidence": confidence,
        "evidence": _evidence(sup) + extra_evidence,
        "proposed_fix": {"action": action, "value": value}, "status": status,
        "detected_at": today, "detected_by": "qa-update v1", "sources": dict(sup),
    }


def _qualifies(sup, min_ndl):
    # type: (dict, int) -> bool
    return sup["ndl"] >= min_ndl or sup["wikidata"] >= 1


def _auto(sup, auto_ndl):
    # type: (dict, int) -> bool
    return sup["ndl"] >= auto_ndl and sup["wikidata"] >= 1


def _gender_conflict(gender, file):
    # type: (Optional[str], str) -> bool
    return (gender == "male" and file == WOMAN) or (gender == "female" and file == MAN)


def generate(index, dataset, allowed, min_ndl=2, auto_ndl=5, max_candidates=2000, today=None):
    # type: (dict, dict, set, int, int, int, Optional[str]) -> Tuple[List[dict], List[dict]]
    today = today or datetime.date.today().isoformat()
    adds = []  # type: List[dict]
    new_readings = {}  # type: Dict[str, List[Tuple[str, dict]]]
    for key, slot in index["pairs"].items():
        kind, kanji, reading = key.split("|")
        if kind != "given":
            continue
        sup = {"ndl": slot["ndl"], "wikidata": slot["wikidata"], "jmnedict": slot["jmnedict"]}
        if not _qualifies(sup, min_ndl) or not bk.kanji_allowed(kanji, allowed):
            continue
        gender = si.gender_of(index, "given", reading)
        holders = [fn for fn in (MAN, WOMAN) if reading in dataset[fn]]
        if holders:
            for fn in holders:
                if kanji in dataset[fn][reading]:
                    continue
                status = "approved" if _auto(sup, auto_ndl) and not _gender_conflict(gender, fn) else "pending"
                note = "（索引の性別 %s と追加先が矛盾）" % gender if _gender_conflict(gender, fn) else ""
                entry = ",".join([reading, dataset_romaji(dataset, fn, reading)] + dataset[fn][reading])
                adds.append(_finding(fn, entry, "add_kanji", kanji, sup, status, today, extra_evidence=note))
        else:
            new_readings.setdefault(reading, []).append((kanji, sup))
    gender_pending = []  # type: List[dict]
    for reading, pairs in sorted(new_readings.items()):
        pairs.sort(key=lambda p: -(p[1]["ndl"] + p[1]["wikidata"]))
        total = {"ndl": sum(p[1]["ndl"] for p in pairs), "wikidata": sum(p[1]["wikidata"] for p in pairs),
                 "jmnedict": any(p[1]["jmnedict"] for p in pairs)}
        gender = si.gender_of(index, "given", reading)
        if gender not in GENDER_FILES:
            gender_pending.append({"reading": reading, "kanji": [p[0] for p in pairs], "sources": total})
            continue
        slot = index["readings"].get(si.reading_key("given", reading), {})
        from_wikidata = bool(slot.get("gender", {}).get("wikidata"))
        status = "approved" if from_wikidata and all(_auto(p[1], auto_ndl) for p in pairs) else "pending"
        entry = ",".join([reading, romaji_for(reading)] + [p[0] for p in pairs])
        for fn in GENDER_FILES[gender]:
            adds.append(_finding(fn, entry, "add_row", "", total, status, today))
    adds.sort(key=lambda f: -(f["sources"]["ndl"] + f["sources"]["wikidata"]))
    adds = adds[:max_candidates]
    surname_findings = []
    for kanji, reading in dataset["surnames"].items():
        prefix = si.pair_key("surname", kanji, "")
        alts = {k.split("|")[2]: v for k, v in index["pairs"].items() if k.startswith(prefix)}
        if not alts or reading in alts:
            continue
        best = max(alts.items(), key=lambda kv: kv[1]["ndl"])[0]
        sup = si.support(index, "surname", kanji, best)
        raw = next((",".join(r) for r in _surname_rows(dataset, kanji, reading)), None)
        if raw is None:
            continue
        surname_findings.append(_finding(
            LAST, raw, "fix_reading", best, sup, "pending", today,
            check="kanji_reading_mismatch", confidence="medium",
            extra_evidence="（索引の読み: %s。現データの読み %s は索引に無い）" % ("・".join(sorted(alts)), reading)))
    all_findings = adds + surname_findings
    dupes = sorted(i for i, n in Counter(f["id"] for f in all_findings).items() if n > 1)
    if dupes:
        raise ValueError("finding id が重複しています: %s" % ", ".join(dupes))
    return all_findings, gender_pending


def dataset_romaji(dataset, fn, reading):
    # type: (dict, str, str) -> str
    return dataset.get("_romaji", {}).get((fn, reading)) or romaji_for(reading)


def _surname_rows(dataset, kanji, reading):
    # type: (dict, str, str) -> List[List[str]]
    return [r for r in dataset.get("_surname_rows", {}).get(kanji, []) if r[2] == reading]


def carry_over(new, existing):
    # type: (List[dict], List[dict]) -> List[dict]
    prev = {d["id"]: d["status"] for d in existing}
    for d in new:
        if d["id"] in prev:
            d["status"] = prev[d["id"]]
    return new


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--gender-pending", required=True)
    parser.add_argument("--allowed", default=os.path.join("qa", "kanji", "jinmei.txt"))
    parser.add_argument("--min-ndl", type=int, default=2)
    parser.add_argument("--auto-ndl", type=int, default=5)
    parser.add_argument("--max-candidates", type=int, default=2000)
    args = parser.parse_args()
    index = si.load_index(args.index)
    dataset = load_dataset(args.dataset_dir)
    allowed = bk.load_allowed(args.allowed)
    fs, pending = generate(index, dataset, allowed, args.min_ndl, args.auto_ndl, args.max_candidates)
    if os.path.exists(args.out):
        fs = carry_over(fs, findings_io.load_findings(args.out))
    for d in fs:
        problems = findings_io.validate_finding(d)
        if problems:
            raise SystemExit("不正な finding %s: %s" % (d["id"], "; ".join(problems)))
    findings_io.save_findings(args.out, fs)
    os.makedirs(os.path.dirname(args.gender_pending) or ".", exist_ok=True)
    with open(args.gender_pending, "w", encoding="utf-8", newline="\n") as f:
        json.dump(pending, f, ensure_ascii=False, indent=1)
    by_status = {}
    for d in fs:
        by_status[d["status"]] = by_status.get(d["status"], 0) + 1
    print("findings %d 件 %s / 性別判定待ち %d 読み → %s" % (len(fs), by_status, len(pending), args.gender_pending))
    return 0


if __name__ == "__main__":
    sys.exit(main())
