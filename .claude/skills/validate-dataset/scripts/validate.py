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
    for filename in FIRST_NAME_FILES + LAST_NAME_FILES:
        path = os.path.join(dataset_dir, filename)
        if not os.path.isfile(path):
            findings.append(checks.Finding(
                filename, 0, checks.CHECK_FORMAT, "error", "ファイルが存在しません"))
            continue
        rows = checks.load_rows(path)
        if filename in LAST_NAME_FILES:
            findings.extend(checks.check_last_name_rows(filename, rows))
        else:
            findings.extend(checks.check_first_name_rows(filename, rows))
        print("%s: %d 行" % (filename, sum(1 for r in rows if r)))

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    print()
    for f in errors:
        print("ERROR   %s:%d: %s" % (f.file, f.line, f.message))
    for f in warnings:
        print("WARNING %s:%d: %s" % (f.file, f.line, f.message))
    print("\n結果: エラー %d 件 / 警告 %d 件" % (len(errors), len(warnings)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
