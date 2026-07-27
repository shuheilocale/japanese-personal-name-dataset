"""dataset CSV の決定的チェック関数群。

validate.py（CLI）と Phase 2 の更新パイプラインの両方から import して使う。
各関数は純関数で、Finding のリストを返す。
"""
import csv
import re
from dataclasses import dataclass
from typing import Dict, List

HIRAGANA_RE = re.compile(r"^[ぁ-ゖー]+$")
ROMAJI_RE = re.compile(r"^[a-z\-']+$")
# 漢字列への混入検出: 英数字（半角・全角）と長音記号。
# かな（木の実・慎ノ介・五郎右エ門など）は実在する表記のため許容する。
KANJI_CONTAMINATION_RE = re.compile(r"[a-zA-Z0-9０-９ａ-ｚＡ-Ｚー]")

CHECK_FORMAT = "format_error"
CHECK_DUPLICATE = "duplicate"
CHECK_ROMAJI = "romaji_reading_mismatch"
CHECK_CROSS_FILE = "cross_file_inconsistency"


@dataclass
class Finding:
    file: str
    line: int  # 1始まり。ファイル全体に関する指摘は 0
    check: str
    severity: str  # 'error' | 'warning' | 'info'
    message: str


def load_rows(path):
    # type: (str) -> List[List[str]]
    """CSV を行リストで読む。空行も [] として保持し、行番号を保存する。"""
    with open(path, encoding="utf-8", newline="") as f:
        return [row for row in csv.reader(f)]


def check_first_name_rows(filename, rows):
    # type: (str, List[List[str]]) -> List[Finding]
    """名 CSV（ひらがな,ローマ字,漢字...）の形式・重複チェック。"""
    findings = []  # type: List[Finding]
    seen = {}  # type: Dict[str, int]
    for lineno, row in enumerate(rows, start=1):
        if not row:
            findings.append(Finding(filename, lineno, CHECK_FORMAT, "warning", "空行"))
            continue
        if len(row) < 2:
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error",
                "列数不足（ひらがな,ローマ字 が必須）: %r" % (row,)))
            continue
        hira, romaji_str = row[0], row[1]
        kanji_list = row[2:]
        if not HIRAGANA_RE.match(hira):
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error",
                "ひらがな列に不正な文字: %r" % hira))
        if not ROMAJI_RE.match(romaji_str):
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error",
                "ローマ字列に不正な文字: %r" % romaji_str))
        if not kanji_list:
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "warning",
                "漢字バリエーションなし: %s" % hira))
        for k in kanji_list:
            if not k or k != k.strip():
                findings.append(Finding(
                    filename, lineno, CHECK_FORMAT, "error",
                    "漢字列が空または前後空白あり: %r" % k))
            elif KANJI_CONTAMINATION_RE.search(k):
                findings.append(Finding(
                    filename, lineno, CHECK_FORMAT, "error",
                    "漢字列に英数字・長音記号の混入: %r" % k))
        if len(set(kanji_list)) != len(kanji_list):
            findings.append(Finding(
                filename, lineno, CHECK_DUPLICATE, "warning",
                "行内に重複した漢字: %s" % hira))
        if hira in seen:
            # core.py はひらがなをキーに辞書化するため、重複行は先行行を上書きする
            findings.append(Finding(
                filename, lineno, CHECK_DUPLICATE, "warning",
                "重複した読み %r（%d行目と重複・後勝ちで上書き）" % (hira, seen[hira])))
        else:
            seen[hira] = lineno
    return findings


def check_last_name_rows(filename, rows):
    # type: (str, List[List[str]]) -> List[Finding]
    """姓 CSV（漢字,推定人数,ひらがな,ローマ字）の形式・重複チェック。"""
    findings = []  # type: List[Finding]
    seen = {}  # type: Dict[str, int]
    for lineno, row in enumerate(rows, start=1):
        if not row:
            findings.append(Finding(filename, lineno, CHECK_FORMAT, "warning", "空行"))
            continue
        if len(row) != 4:
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error", "列数が4でない: %r" % (row,)))
            continue
        kanji, population, hira, romaji_str = row
        if not kanji or kanji != kanji.strip():
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error",
                "漢字列が空または前後空白あり: %r" % kanji))
        elif KANJI_CONTAMINATION_RE.search(kanji):
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error",
                "漢字列に英数字・長音記号の混入: %r" % kanji))
        if not population.isdigit():
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error",
                "推定人数が整数でない: %r" % population))
        if not HIRAGANA_RE.match(hira):
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error",
                "ひらがな列に不正な文字: %r" % hira))
        if not ROMAJI_RE.match(romaji_str):
            findings.append(Finding(
                filename, lineno, CHECK_FORMAT, "error",
                "ローマ字列に不正な文字: %r" % romaji_str))
        if kanji in seen:
            findings.append(Finding(
                filename, lineno, CHECK_DUPLICATE, "warning",
                "重複した姓 %r（%d行目と重複）" % (kanji, seen[kanji])))
        else:
            seen[kanji] = lineno
    return findings
