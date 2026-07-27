"""疑義台帳（findings JSONL）と検証済みキャッシュ（verified.json）の入出力。

スキーマは docs/superpowers/specs/2026-07-27-qa-foundation-design.md §5 に従う。
Phase 2 の更新パイプラインと共有する安定契約なので、変更時はスペックも更新する。
"""
import hashlib
import json
import os
from typing import Dict, List

CHECK_TYPES = {
    "format_error", "romaji_reading_mismatch", "kanji_reading_mismatch",
    "not_a_name", "wrong_gender_file", "duplicate", "cross_file_inconsistency",
}
ACTIONS = {"remove_row", "remove_kanji", "fix_romaji", "fix_reading", "move_to_file", "none"}
STATUSES = {"pending", "approved", "rejected", "applied"}
CONFIDENCES = {"high", "medium", "low"}
SEVERITIES = {"error", "warning"}

# dataset/ 配下に実在する5ファイルのみを許可する（パストラバーサル対策）。
DATASET_FILES = {
    "first_name_man_org.csv", "first_name_man_opti.csv",
    "first_name_woman_org.csv", "first_name_woman_opti.csv",
    "last_name_org.csv",
}
# move_to_file の移動先は男女の名ファイルのみ（姓ファイルへの移動は不可）。
MOVE_TARGET_FILES = {
    "first_name_man_org.csv", "first_name_man_opti.csv",
    "first_name_woman_org.csv", "first_name_woman_opti.csv",
}

_REQUIRED = [
    "id", "file", "entry", "check", "severity", "confidence",
    "evidence", "proposed_fix", "status", "detected_at", "detected_by",
]


def entry_hash(filename, raw_line):
    # type: (str, str) -> str
    """エントリ内容のハッシュ。行が1文字でも変われば別ハッシュになる。"""
    data = ("%s:%s" % (filename, raw_line)).encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def validate_finding(d):
    # type: (dict) -> List[str]
    """スキーマ違反のメッセージリストを返す。空なら正常。"""
    problems = []  # type: List[str]
    for key in _REQUIRED:
        if key not in d:
            problems.append("必須フィールドがありません: %s" % key)
    if problems:
        return problems
    if d["file"] not in DATASET_FILES:
        problems.append("未知の file（許可された5ファイル以外）: %r" % d["file"])
    if d["check"] not in CHECK_TYPES:
        problems.append("未知の check: %r" % d["check"])
    if d["severity"] not in SEVERITIES:
        problems.append("未知の severity: %r" % d["severity"])
    if d["confidence"] not in CONFIDENCES:
        problems.append("未知の confidence: %r" % d["confidence"])
    if d["status"] not in STATUSES:
        problems.append("未知の status: %r" % d["status"])
    fix = d["proposed_fix"]
    if not isinstance(fix, dict) or "action" not in fix:
        problems.append("proposed_fix は {action, value} の dict である必要があります")
    elif fix["action"] not in ACTIONS:
        problems.append("未知の action: %r" % fix["action"])
    elif fix["action"] == "move_to_file" and fix.get("value") not in MOVE_TARGET_FILES:
        problems.append(
            "move_to_file の移動先が不正です（名ファイルのみ許可）: %r" % fix.get("value"))
    return problems


def append_findings(path, findings):
    # type: (str, List[dict]) -> None
    for d in findings:
        problems = validate_finding(d)
        if problems:
            raise ValueError("不正な finding (%s): %s" % (d.get("id"), "; ".join(problems)))
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        for d in findings:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def load_findings(path):
    # type: (str) -> List[dict]
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_findings(path, findings):
    # type: (str, List[dict]) -> None
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for d in findings:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def load_verified(path):
    # type: (str) -> Dict[str, dict]
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_verified(path, verified):
    # type: (str, Dict[str, dict]) -> None
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(verified, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
