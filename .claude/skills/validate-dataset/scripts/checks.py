"""dataset CSV の決定的チェック関数群。

validate.py（CLI）と Phase 2 の更新パイプラインの両方から import して使う。
各関数は純関数で、Finding のリストを返す。
"""
import csv
import re
from dataclasses import dataclass
from typing import Dict, List

import romaji as romaji_mod

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


def _reading_romaji(row, kind):
    # type: (List[str], str) -> tuple
    """行から (読み, ローマ字) を取り出す。取り出せない行は (None, None)。"""
    if kind == "first" and len(row) >= 2:
        return row[0], row[1]
    if kind == "last" and len(row) == 4:
        return row[2], row[3]
    return None, None


def check_romaji_reading(filename, rows, kind):
    # type: (str, List[List[str]], str) -> List[Finding]
    """読みとローマ字の対応を候補集合で照合する。"""
    findings = []  # type: List[Finding]
    for lineno, row in enumerate(rows, start=1):
        hira, romaji_str = _reading_romaji(row, kind)
        if hira is None or not HIRAGANA_RE.match(hira) or not ROMAJI_RE.match(romaji_str):
            continue  # 形式エラーは check_*_rows が報告済み
        try:
            candidates = romaji_mod.romaji_candidates(hira)
        except ValueError as e:
            findings.append(Finding(
                filename, lineno, CHECK_ROMAJI, "error",
                "読みをモーラ分割できません: %s" % e))
            continue
        if romaji_str not in candidates:
            findings.append(Finding(
                filename, lineno, CHECK_ROMAJI, "error",
                "ローマ字 %r が読み %r のどの許容表記とも一致しません" % (romaji_str, hira)))
    return findings


def check_opti_subset(opti_filename, opti_rows, org_rows):
    # type: (str, List[List[str]], List[List[str]]) -> List[Finding]
    """opti 版が org 版の部分集合であることを確認する。"""
    org_index = {}  # type: Dict[str, List[str]]
    org_romaji = {}  # type: Dict[str, str]
    for row in org_rows:
        if len(row) >= 2:
            org_index[row[0]] = row[2:]
            org_romaji[row[0]] = row[1]
    findings = []  # type: List[Finding]
    for lineno, row in enumerate(opti_rows, start=1):
        if len(row) < 2:
            continue
        hira, romaji_str = row[0], row[1]
        if hira not in org_index:
            findings.append(Finding(
                opti_filename, lineno, CHECK_CROSS_FILE, "error",
                "読み %r が org 版に存在しません" % hira))
            continue
        if romaji_str != org_romaji[hira]:
            findings.append(Finding(
                opti_filename, lineno, CHECK_CROSS_FILE, "error",
                "ローマ字 %r が org 版の %r と一致しません" % (romaji_str, org_romaji[hira])))
        extra = [k for k in row[2:] if k not in org_index[hira]]
        if extra:
            findings.append(Finding(
                opti_filename, lineno, CHECK_CROSS_FILE, "warning",
                "org 版にない漢字: %s（読み %s）" % ("・".join(extra), hira)))
    return findings


def check_gender_overlap(man_rows, woman_rows):
    # type: (List[List[str]], List[List[str]]) -> List[Finding]
    """男女ファイル間の同一読みエントリを情報として報告する。"""
    man_romaji = {row[0]: row[1] for row in man_rows if len(row) >= 2}
    findings = []  # type: List[Finding]
    shared = 0
    for lineno, row in enumerate(woman_rows, start=1):
        if len(row) < 2 or row[0] not in man_romaji:
            continue
        shared += 1
        if row[1] != man_romaji[row[0]]:
            findings.append(Finding(
                "first_name_woman_org.csv", lineno, CHECK_CROSS_FILE, "warning",
                "読み %r のローマ字が男性名ファイルと食い違う: %r vs %r"
                % (row[0], row[1], man_romaji[row[0]])))
    findings.append(Finding(
        "", 0, CHECK_CROSS_FILE, "info",
        "男女両ファイルに存在する読み: %d 件（正当なケースを含む）" % shared))
    return findings


def romaji_style_stats(rows, kind):
    # type: (List[List[str]], str) -> Dict[str, int]
    """ローマ字表記方式の分布を集計する（Phase 3 の入力データ）。"""
    stats = {"neutral": 0, "wapuro": 0, "shortened": 0, "mixed": 0, "unknown": 0}
    for row in rows:
        hira, romaji_str = _reading_romaji(row, kind)
        if hira is None:
            continue
        stats[romaji_mod.classify_style(hira, romaji_str)] += 1
    return stats
