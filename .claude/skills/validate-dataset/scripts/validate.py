#!/usr/bin/env python3
"""japanese-personal-name-dataset の CSV フォーマット検証スクリプト。

使い方:
    python3 .claude/skills/validate-dataset/scripts/validate.py [dataset_dir]

dataset_dir を省略した場合はリポジトリ内の
japanese_personal_name_dataset/dataset/ を検証する。

終了コード: 0 = エラーなし（警告のみ含む）, 1 = エラーあり
"""
import csv
import os
import re
import sys
from typing import List

HIRAGANA_RE = re.compile(r"^[ぁ-ゖー]+$")
ROMAJI_RE = re.compile(r"^[a-z\-']+$")
# 漢字列への混入検出: 英数字（半角・全角）と長音記号。
# かな（木の実・慎ノ介・五郎右エ門など）は実在する表記のため許容する。
KANJI_CONTAMINATION_RE = re.compile(r"[a-zA-Z0-9０-９ａ-ｚＡ-Ｚー]")

FIRST_NAME_FILES = [
    "first_name_man_org.csv",
    "first_name_man_opti.csv",
    "first_name_woman_org.csv",
    "first_name_woman_opti.csv",
]
LAST_NAME_FILES = ["last_name_org.csv"]


def validate_first_name_file(path: str, errors: List[str], warnings: List[str]) -> int:
    """名 CSV（ひらがな,ローマ字,漢字...）を検証し、行数を返す。"""
    name = os.path.basename(path)
    seen = {}
    rows = 0
    with open(path, encoding="utf-8", newline="") as f:
        for lineno, row in enumerate(csv.reader(f), start=1):
            if not row:
                warnings.append(f"{name}:{lineno}: 空行")
                continue
            rows += 1
            if len(row) < 2:
                errors.append(f"{name}:{lineno}: 列数不足（ひらがな,ローマ字 が必須）: {row}")
                continue
            hira, romaji = row[0], row[1]
            kanji_list = row[2:]
            if not HIRAGANA_RE.match(hira):
                errors.append(f"{name}:{lineno}: ひらがな列に不正な文字: {hira!r}")
            if not ROMAJI_RE.match(romaji):
                errors.append(f"{name}:{lineno}: ローマ字列に不正な文字: {romaji!r}")
            if not kanji_list:
                warnings.append(f"{name}:{lineno}: 漢字バリエーションなし: {hira}")
            for k in kanji_list:
                if not k or k != k.strip():
                    errors.append(f"{name}:{lineno}: 漢字列が空または前後空白あり: {k!r}")
                elif KANJI_CONTAMINATION_RE.search(k):
                    errors.append(f"{name}:{lineno}: 漢字列に英数字・長音記号の混入: {k!r}")
            if len(set(kanji_list)) != len(kanji_list):
                warnings.append(f"{name}:{lineno}: 行内に重複した漢字: {hira}")
            if hira in seen:
                # core.py はひらがなをキーに辞書化するため、重複行は先行行を上書きする
                warnings.append(
                    f"{name}:{lineno}: 重複した読み {hira!r}（{seen[hira]}行目と重複・後勝ちで上書き）"
                )
            else:
                seen[hira] = lineno
    return rows


def validate_last_name_file(path: str, errors: List[str], warnings: List[str]) -> int:
    """姓 CSV（漢字,推定人数,ひらがな,ローマ字）を検証し、行数を返す。"""
    name = os.path.basename(path)
    seen = {}
    rows = 0
    with open(path, encoding="utf-8", newline="") as f:
        for lineno, row in enumerate(csv.reader(f), start=1):
            if not row:
                warnings.append(f"{name}:{lineno}: 空行")
                continue
            rows += 1
            if len(row) != 4:
                errors.append(f"{name}:{lineno}: 列数が4でない: {row}")
                continue
            kanji, population, hira, romaji = row
            if not kanji or kanji != kanji.strip():
                errors.append(f"{name}:{lineno}: 漢字列が空または前後空白あり: {kanji!r}")
            elif KANJI_CONTAMINATION_RE.search(kanji):
                errors.append(f"{name}:{lineno}: 漢字列に英数字・長音記号の混入: {kanji!r}")
            if not population.isdigit():
                errors.append(f"{name}:{lineno}: 推定人数が整数でない: {population!r}")
            if not HIRAGANA_RE.match(hira):
                errors.append(f"{name}:{lineno}: ひらがな列に不正な文字: {hira!r}")
            if not ROMAJI_RE.match(romaji):
                errors.append(f"{name}:{lineno}: ローマ字列に不正な文字: {romaji!r}")
            if kanji in seen:
                warnings.append(
                    f"{name}:{lineno}: 重複した姓 {kanji!r}（{seen[kanji]}行目と重複）"
                )
            else:
                seen[kanji] = lineno
    return rows


def main() -> int:
    if len(sys.argv) > 1:
        dataset_dir = sys.argv[1]
    else:
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), *[os.pardir] * 4)
        )
        dataset_dir = os.path.join(repo_root, "japanese_personal_name_dataset", "dataset")

    if not os.path.isdir(dataset_dir):
        print(f"エラー: dataset ディレクトリが見つかりません: {dataset_dir}")
        return 1

    errors: List[str] = []
    warnings: List[str] = []

    for filename in FIRST_NAME_FILES + LAST_NAME_FILES:
        path = os.path.join(dataset_dir, filename)
        if not os.path.isfile(path):
            errors.append(f"{filename}: ファイルが存在しません")
            continue
        if filename in LAST_NAME_FILES:
            rows = validate_last_name_file(path, errors, warnings)
        else:
            rows = validate_first_name_file(path, errors, warnings)
        print(f"{filename}: {rows} 行")

    print()
    for message in errors:
        print(f"ERROR   {message}")
    for message in warnings:
        print(f"WARNING {message}")
    print(f"\n結果: エラー {len(errors)} 件 / 警告 {len(warnings)} 件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
