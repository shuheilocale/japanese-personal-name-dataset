#!/usr/bin/env python3
"""japanese-personal-name-dataset の CSV フォーマット検証スクリプト。

使い方:
    python3 .claude/skills/validate-dataset/scripts/validate.py [dataset_dir]

dataset_dir を省略した場合はリポジトリ内の
japanese_personal_name_dataset/dataset/ を検証する。

終了コード: 0 = エラーなし（警告のみ含む）, 1 = エラーあり
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks  # noqa: E402

FIRST_NAME_FILES = [
    "first_name_man_org.csv",
    "first_name_man_opti.csv",
    "first_name_woman_org.csv",
    "first_name_woman_opti.csv",
]
LAST_NAME_FILES = ["last_name_org.csv"]


def main():
    # type: () -> int
    if len(sys.argv) > 1:
        dataset_dir = sys.argv[1]
    else:
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), *[os.pardir] * 4)
        )
        dataset_dir = os.path.join(repo_root, "japanese_personal_name_dataset", "dataset")

    if not os.path.isdir(dataset_dir):
        print("エラー: dataset ディレクトリが見つかりません: %s" % dataset_dir)
        return 1

    findings = []
    all_rows = {}
    for filename in FIRST_NAME_FILES + LAST_NAME_FILES:
        path = os.path.join(dataset_dir, filename)
        if not os.path.isfile(path):
            findings.append(checks.Finding(
                filename, 0, checks.CHECK_FORMAT, "error", "ファイルが存在しません"))
            continue
        rows = checks.load_rows(path)
        all_rows[filename] = rows
        kind = "last" if filename in LAST_NAME_FILES else "first"
        if filename in LAST_NAME_FILES:
            findings.extend(checks.check_last_name_rows(filename, rows))
        else:
            findings.extend(checks.check_first_name_rows(filename, rows))
        findings.extend(checks.check_romaji_reading(filename, rows, kind))
        print("%s: %d 行" % (filename, sum(1 for r in rows if r)))

    for opti, org in [
        ("first_name_man_opti.csv", "first_name_man_org.csv"),
        ("first_name_woman_opti.csv", "first_name_woman_org.csv"),
    ]:
        if opti in all_rows and org in all_rows:
            findings.extend(checks.check_opti_subset(opti, all_rows[opti], all_rows[org]))
    if "first_name_man_org.csv" in all_rows and "first_name_woman_org.csv" in all_rows:
        findings.extend(checks.check_gender_overlap(
            all_rows["first_name_man_org.csv"], all_rows["first_name_woman_org.csv"]))

    print("\nローマ字表記方式の分布:")
    for filename in FIRST_NAME_FILES + LAST_NAME_FILES:
        if filename not in all_rows:
            continue
        kind = "last" if filename in LAST_NAME_FILES else "first"
        stats = checks.romaji_style_stats(all_rows[filename], kind)
        print("  %s: %s" % (filename, " ".join("%s=%d" % kv for kv in sorted(stats.items()))))

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    infos = [f for f in findings if f.severity == "info"]
    print()
    for f in errors:
        if f.line == 0:
            print("ERROR   %s: %s" % (f.file, f.message))
        else:
            print("ERROR   %s:%d: %s" % (f.file, f.line, f.message))
    for f in warnings:
        if f.line == 0:
            print("WARNING %s: %s" % (f.file, f.message))
        else:
            print("WARNING %s:%d: %s" % (f.file, f.line, f.message))
    for f in infos:
        if f.line == 0:
            print("INFO    %s: %s" % (f.file, f.message))
        else:
            print("INFO    %s:%d: %s" % (f.file, f.line, f.message))
    print("\n結果: エラー %d 件 / 警告 %d 件 / 情報 %d 件" % (len(errors), len(warnings), len(infos)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
