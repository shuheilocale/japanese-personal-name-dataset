"""保留 findings の判断 UI（ローカル Web サーバ）。

findings JSONL と dataset CSV を読み、行単位の表示用アイテムと客観シグナルを
JSON API で返す。判断（approved/rejected/pending）は即座に JSONL へ原子的に書き戻す。
"""
import argparse
import json
import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "validate-dataset", "scripts")))

import checks  # noqa: E402
import findings_io  # noqa: E402

FIRST_NAME_FILES = [
    "first_name_man_org.csv", "first_name_man_opti.csv",
    "first_name_woman_org.csv", "first_name_woman_opti.csv",
]
LAST_NAME_FILE = "last_name_org.csv"
SUFFIX_RULES = {
    "郎": "ろう", "朗": "ろう", "彦": "ひこ", "子": "こ", "也": "や", "哉": "や",
    "夫": "お", "雄": "お", "男": "お", "美": "み", "江": "え", "恵": "え", "枝": "え",
}
DECIDABLE = ("pending", "approved", "rejected")


def load_dataset_index(dataset_dir):
    # type: (str) -> Dict[str, dict]
    """ファイルごとに 漢字→読み集合 と 読み集合 を作る。"""
    index = {}  # type: Dict[str, dict]
    for fn in FIRST_NAME_FILES:
        kanji_index = {}  # type: Dict[str, set]
        readings = set()
        for r in checks.load_rows(os.path.join(dataset_dir, fn)):
            if len(r) < 2:
                continue
            readings.add(r[0])
            for k in r[2:]:
                kanji_index.setdefault(k, set()).add(r[0])
        index[fn] = {"kanji_index": kanji_index, "readings": readings}
    readings = set()
    for r in checks.load_rows(os.path.join(dataset_dir, LAST_NAME_FILE)):
        if len(r) == 4:
            readings.add(r[2])
    index[LAST_NAME_FILE] = {"kanji_index": {}, "readings": readings}
    return index


def parse_row(file, entry):
    # type: (str, str) -> dict
    c = entry.split(",")
    if file == LAST_NAME_FILE and len(c) == 4:
        return {"reading": c[2], "romaji": c[3], "kanji": [c[0]], "population": c[1]}
    return {"reading": c[0], "romaji": c[1] if len(c) > 1 else "", "kanji": c[2:], "population": None}


def compute_signals(finding, index):
    # type: (dict, Dict[str, dict]) -> List[dict]
    signals = []  # type: List[dict]
    row = parse_row(finding["file"], finding["entry"])
    action = finding["proposed_fix"]["action"]
    value = finding["proposed_fix"].get("value", "")
    info = index.get(finding["file"], {"kanji_index": {}, "readings": set()})
    if action == "remove_kanji":
        others = sorted(info["kanji_index"].get(value, set()) - {row["reading"]})
        if others:
            signals.append({"type": "dup_elsewhere", "readings": others})
        for suffix, expected in SUFFIX_RULES.items():
            if value.endswith(suffix) and not row["reading"].endswith(expected):
                signals.append({"type": "suffix_rule", "suffix": suffix, "expected": expected})
                break
    if action == "fix_reading" and value in info["readings"]:
        signals.append({"type": "fix_reading_dup"})
    return signals


def build_items(findings, index):
    # type: (List[dict], Dict[str, dict]) -> List[dict]
    items = []
    for d in findings:
        row = parse_row(d["file"], d["entry"])
        action = d["proposed_fix"]["action"]
        value = d["proposed_fix"].get("value", "")
        targets = [value] if action == "remove_kanji" and value else []
        query = " ".join([t for t in targets] + [row["reading"], "名前"])
        item = dict(d)
        item.update({
            "row": row, "targets": targets,
            "signals": compute_signals(d, index),
            "search_url": "https://www.google.com/search?q=" + urllib.parse.quote(query),
        })
        items.append(item)
    return items


def count_statuses(findings):
    # type: (List[dict]) -> Dict[str, int]
    counts = {"pending": 0, "approved": 0, "rejected": 0, "applied": 0}
    for d in findings:
        counts[d["status"]] = counts.get(d["status"], 0) + 1
    return counts


def apply_decision(findings, ids, status):
    # type: (List[dict], List[str], str) -> int
    if status not in DECIDABLE:
        raise ValueError("不正な status: %r" % status)
    by_id = {d["id"]: d for d in findings}
    for i in ids:
        if i not in by_id:
            raise ValueError("未知の id: %r" % i)
        if by_id[i]["status"] not in DECIDABLE:
            raise ValueError("変更不可の status (%s): %r" % (by_id[i]["status"], i))
    for i in ids:
        by_id[i]["status"] = status
    return len(ids)


def save_atomic(path, findings):
    # type: (str, List[dict]) -> None
    tmp = path + ".tmp"
    findings_io.save_findings(tmp, findings)
    os.replace(tmp, path)
