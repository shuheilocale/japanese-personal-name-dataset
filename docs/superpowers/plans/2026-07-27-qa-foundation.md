# QA基盤（Phase 1）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 約11,000件の姓名データを決定的チェック＋LLMチェックの二層で全件検証し、疑義台帳→承認→一括適用のフローでクリーニングできる品質保証基盤を構築する。

**Architecture:** 共有モジュール（`romaji.py`・`checks.py`・`findings_io.py`）を `.claude/skills/validate-dataset/scripts/` に置き、validate.py は CLI ラッパーに徹する。LLM チェックは `/qa-review` スキル（バッチ準備・結果マージは決定的スクリプト、判定のみサブエージェント）、適用は `/qa-apply` スキル＋適用スクリプト。検証済みキャッシュ（`qa/verified.json`）で増分検証を実現する。

**Tech Stack:** Python 標準ライブラリのみ（csv, dataclasses, hashlib, json, itertools, bisect）。テストは pytest。外部依存の追加はしない。

**Spec:** `docs/superpowers/specs/2026-07-27-qa-foundation-design.md`

## Global Constraints

- **Python 3.8 互換構文を全 .py で使う**: PostToolUse フックが編集された全 .py に vermin 3.8 チェックをかける。`typing.List/Dict/Set/Optional/Tuple` を使い、`X | Y` 型・`list[str]`・match 文は禁止。
- **dataset CSV は Edit/Write ツールで編集禁止**（PreToolUse フックでブロック）。適用は必ずユーザーの明示承認後に `apply_findings.py` を Bash で実行する。
- **公開 API（`japanese_personal_name_dataset` パッケージ）には一切触れない**。
- **クロスプラットフォーム**: tests/ は CI で Windows/macOS/Linux × Python 3.8-3.12 で走る。ファイル I/O は必ず `encoding="utf-8"`、CSV は `newline=""`、パスは `os.path` / `tmp_path` を使う。
- スクリプトのユーザー向けメッセージは日本語（既存 validate.py と統一）。
- テスト実行: `uv run pytest tests/ -v`。検証実行: `python3 .claude/skills/validate-dataset/scripts/validate.py`。
- コミットメッセージは英語命令形 + 末尾に `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- CSV フィールドにカンマ・引用符は存在しない前提（validate.py の文字種チェックが保証）。行の再構成は `",".join()` で行ってよい。

---

### Task 1: ローマ字候補生成モジュール `romaji.py`（モーラ分割と基本変換）

**Files:**
- Create: `.claude/skills/validate-dataset/scripts/romaji.py`
- Create: `tests/conftest.py`
- Test: `tests/test_qa_romaji.py`

**Interfaces:**
- Consumes: なし（最初のタスク）
- Produces:
  - `romaji.tokenize(hira: str) -> List[str]` — ひらがなをモーラ単位に分割。促音=`"Q"`、撥音=`"N"`、長音記号=`"H"` のマーカーで返す。未対応文字は `ValueError`。
  - `romaji.romaji_candidates(hira: str) -> Set[str]` — 許容されるローマ字表記の候補集合（Task 2 で長音バリアント追加。本タスクでは基本形のみ）。

- [ ] **Step 1: conftest.py でスクリプトディレクトリを import path に追加**

```python
# tests/conftest.py
"""QA ツール（.claude/skills/*/scripts/）を import できるようにする。"""
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
for _rel in (
    os.path.join(".claude", "skills", "validate-dataset", "scripts"),
    os.path.join(".claude", "skills", "qa-review", "scripts"),
    os.path.join(".claude", "skills", "qa-apply", "scripts"),
):
    _p = os.path.join(_REPO_ROOT, _rel)
    if _p not in sys.path:
        sys.path.insert(0, _p)
```

- [ ] **Step 2: 失敗するテストを書く**

```python
# tests/test_qa_romaji.py
"""romaji.py（ひらがな→ローマ字候補生成）のテスト。"""
import pytest

import romaji


class TestTokenize:
    def test_basic(self):
        assert romaji.tokenize("あい") == ["あ", "い"]

    def test_youon(self):
        assert romaji.tokenize("きょうこ") == ["きょ", "う", "こ"]

    def test_sokuon_hatsuon_chouon(self):
        assert romaji.tokenize("いっき") == ["い", "Q", "き"]
        assert romaji.tokenize("けんいち") == ["け", "N", "い", "ち"]
        assert romaji.tokenize("あーさ") == ["あ", "H", "さ"]

    def test_unknown_char_raises(self):
        with pytest.raises(ValueError):
            romaji.tokenize("あゃ")  # 拗音の小書きが単独で出現（不正データ）


class TestCandidatesBasic:
    def test_simple(self):
        assert "ai" in romaji.romaji_candidates("あい")

    def test_hepburn_specials(self):
        assert "shinji" in romaji.romaji_candidates("しんじ")
        assert "tsutomu" in romaji.romaji_candidates("つとむ")
        assert "fumio" in romaji.romaji_candidates("ふみお")

    def test_sokuon_doubles_consonant(self):
        assert "ikki" in romaji.romaji_candidates("いっき")
        # っち はヘボン式 tchi とワープロ式 cchi の両方を許容
        c = romaji.romaji_candidates("えっちゅう")
        assert "etchu" in c or "etchuu" in c
        assert "ecchu" in c or "ecchuu" in c

    def test_hatsuon_variants(self):
        # ん + b/m/p は n / m 両方許容
        c = romaji.romaji_candidates("じゅんぺい")
        assert "junpei" in c
        assert "jumpei" in c
        # ん + 母音 は n / n' 両方許容
        c = romaji.romaji_candidates("けんいち")
        assert "kenichi" in c
        assert "ken'ichi" in c
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_romaji.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'romaji'`）

- [ ] **Step 4: romaji.py を実装**

```python
# .claude/skills/validate-dataset/scripts/romaji.py
"""ひらがな→ローマ字候補生成（検証用）。

単一の正解を生成するのではなく、データセットで許容される複数方式
（ワープロ式・長音省略式・その混合）の候補集合を生成する。
実データで方式の混在が確認されているため（例: あいいちろう→aichirou、
いっしゅう→isshu）、どの候補にも一致しない行だけを疑義とする。
"""
import itertools
from typing import List, Optional, Set

BASIC = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "ゐ": "i", "ゑ": "e", "を": "o",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o",
    "ゔ": "vu",
}

YOUON = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo",
    "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho",
    "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo",
    "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo",
    "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo",
    "ぢゃ": "ja", "ぢゅ": "ju", "ぢょ": "jo",
    "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo",
}

_SMALL_YOUON = "ゃゅょ"
_VOWELS = "aiueo"
_LIMIT = 4096  # 候補集合の上限（人名の長さでは実質届かない安全弁）


def tokenize(hira):
    # type: (str) -> List[str]
    """ひらがなをモーラ単位に分割する。促音="Q"、撥音="N"、長音記号="H"。"""
    tokens = []  # type: List[str]
    i = 0
    while i < len(hira):
        ch = hira[i]
        if ch == "っ":
            tokens.append("Q")
            i += 1
        elif ch == "ん":
            tokens.append("N")
            i += 1
        elif ch == "ー":
            tokens.append("H")
            i += 1
        elif i + 1 < len(hira) and hira[i:i + 2] in YOUON:
            tokens.append(hira[i:i + 2])
            i += 2
        elif ch in _SMALL_YOUON or ch not in BASIC:
            raise ValueError("モーラ分割できないかな: %r（%r 内）" % (ch, hira))
        else:
            tokens.append(ch)
            i += 1
    return tokens


def _mora_romaji(token):
    # type: (str) -> str
    if token in YOUON:
        return YOUON[token]
    return BASIC[token]


def _prev_vowel(tokens, idx):
    # type: (List[str], int) -> Optional[str]
    """idx の直前の（マーカーでない）モーラの末尾母音を返す。"""
    j = idx - 1
    while j >= 0 and tokens[j] in ("Q", "H"):
        j -= 1
    if j < 0 or tokens[j] == "N":
        return None
    r = _mora_romaji(tokens[j])
    return r[-1] if r[-1] in _VOWELS else None


def _next_real(tokens, idx):
    # type: (List[str], int) -> Optional[str]
    """idx の直後の（マーカーでない）モーラを返す。"""
    j = idx + 1
    while j < len(tokens) and tokens[j] in ("Q", "H", "N"):
        j += 1
    return tokens[j] if j < len(tokens) else None


def _alternatives(tokens, long_mode):
    # type: (List[str], str) -> List[List[str]]
    """モーラごとのローマ字候補リストを返す。long_mode: 'keep' | 'drop' | 'both'"""
    alts = []  # type: List[List[str]]
    for idx, tok in enumerate(tokens):
        if tok == "Q":
            nxt = _next_real(tokens, idx)
            if nxt is None:
                alts.append([""])  # 語末の促音（不正に近いが落とさない）
            else:
                r = _mora_romaji(nxt)
                if r.startswith("ch"):
                    alts.append(["t", "c"])  # っち→tchi / cchi
                else:
                    alts.append([r[0]])
        elif tok == "N":
            nxt = tokens[idx + 1] if idx + 1 < len(tokens) else None
            options = ["n"]
            if nxt is not None and nxt not in ("Q", "H", "N"):
                r = _mora_romaji(nxt)
                if r[0] in "bmp":
                    options.append("m")
                if r[0] in _VOWELS or r[0] == "y":
                    options.append("n'")
            alts.append(options)
        elif tok == "H":
            pv = _prev_vowel(tokens, idx)
            alts.append(_long_options(pv if pv else "", long_mode))
        else:
            base = _mora_romaji(tok)
            pv = _prev_vowel(tokens, idx)
            is_long = (
                tok in ("あ", "い", "う", "え", "お")
                and pv is not None
                and (base == pv or (tok == "う" and pv == "o") or (tok == "い" and pv == "e"))
            )
            if is_long:
                alts.append(_long_options(base, long_mode))
            else:
                alts.append([base])
    return alts


def _long_options(vowel, long_mode):
    # type: (str, str) -> List[str]
    if long_mode == "keep":
        return [vowel] if vowel else [""]
    if long_mode == "drop":
        return [""]
    return [vowel, ""] if vowel else [""]


def _combine(alts):
    # type: (List[List[str]]) -> Set[str]
    out = set()  # type: Set[str]
    for combo in itertools.product(*alts):
        out.add("".join(combo))
        if len(out) >= _LIMIT:
            break
    return out


def romaji_candidates(hira):
    # type: (str) -> Set[str]
    """許容される全ローマ字候補（ワープロ式・長音省略式・混合）を返す。"""
    return _combine(_alternatives(tokenize(hira), "both"))
```

- [ ] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_romaji.py -v`
Expected: PASS（全件）

- [ ] **Step 6: コミット**

```bash
git add tests/conftest.py tests/test_qa_romaji.py .claude/skills/validate-dataset/scripts/romaji.py
git commit -m "Add hiragana-to-romaji candidate generator for QA validation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: 長音バリアントと表記方式の判定 `classify_style`

**Files:**
- Modify: `.claude/skills/validate-dataset/scripts/romaji.py`（末尾に追加）
- Test: `tests/test_qa_romaji.py`（クラス追加）

**Interfaces:**
- Consumes: Task 1 の `tokenize` / `_alternatives` / `_combine`
- Produces:
  - `romaji.classify_style(hira: str, romaji_str: str) -> str` — 戻り値は `"neutral"`（長音なし・一致）/ `"wapuro"`（かな通り表記）/ `"shortened"`（長音省略表記）/ `"mixed"`（混合だが許容内）/ `"unknown"`（どの候補とも不一致 or モーラ分割不能）

- [ ] **Step 1: 失敗するテストを追加**

```python
# tests/test_qa_romaji.py に追加
class TestLongVowelsAndStyle:
    def test_long_vowel_variants(self):
        c = romaji.romaji_candidates("さとう")
        assert "satou" in c and "sato" in c
        c = romaji.romaji_candidates("ああす")
        assert "aasu" in c and "asu" in c
        c = romaji.romaji_candidates("いっしゅう")
        assert "isshuu" in c and "isshu" in c

    def test_mixed_style_accepted(self):
        # 実データ: あいいちろう,aichirou（いい は省略、ろう は保持）
        assert "aichirou" in romaji.romaji_candidates("あいいちろう")

    def test_classify(self):
        assert romaji.classify_style("あい", "ai") == "neutral"
        assert romaji.classify_style("さとう", "satou") == "wapuro"
        assert romaji.classify_style("いっしゅう", "isshu") == "shortened"
        assert romaji.classify_style("あいいちろう", "aichirou") == "mixed"
        assert romaji.classify_style("さとう", "satoh") == "unknown"
        assert romaji.classify_style("あゃ", "aya") == "unknown"  # 分割不能
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_romaji.py::TestLongVowelsAndStyle -v`
Expected: FAIL（`classify_style` 未定義。`test_long_vowel_variants` は Task 1 実装で通る場合もある）

- [ ] **Step 3: classify_style を実装**

```python
# romaji.py 末尾に追加
def classify_style(hira, romaji_str):
    # type: (str, str) -> str
    """ローマ字表記が長音をどう扱っているかを判定する。"""
    try:
        tokens = tokenize(hira)
    except ValueError:
        return "unknown"
    keep = _combine(_alternatives(tokens, "keep"))
    drop = _combine(_alternatives(tokens, "drop"))
    if keep == drop:  # 長音を含まない
        return "neutral" if romaji_str in keep else "unknown"
    in_keep = romaji_str in keep
    in_drop = romaji_str in drop
    if in_keep and in_drop:
        return "neutral"
    if in_keep:
        return "wapuro"
    if in_drop:
        return "shortened"
    if romaji_str in _combine(_alternatives(tokens, "both")):
        return "mixed"
    return "unknown"
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_romaji.py -v`
Expected: PASS（全件）

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_romaji.py .claude/skills/validate-dataset/scripts/romaji.py
git commit -m "Add long-vowel variants and romaji style classification

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: チェック関数の分離 `checks.py`（既存チェックの純関数化）

**Files:**
- Create: `.claude/skills/validate-dataset/scripts/checks.py`
- Modify: `.claude/skills/validate-dataset/scripts/validate.py`（チェックロジックを checks.py へ委譲）
- Test: `tests/test_qa_checks.py`

**Interfaces:**
- Consumes: なし（romaji.py とは独立。romaji 連携は Task 4）
- Produces:
  - `checks.Finding` — dataclass: `file: str, line: int, check: str, severity: str, message: str`（severity は `"error"` / `"warning"` / `"info"`、check は `"format_error"` / `"duplicate"` / `"romaji_reading_mismatch"` / `"cross_file_inconsistency"`）
  - `checks.load_rows(path: str) -> List[List[str]]` — CSV を行リストで読む（空行は `[]` のまま保持し行番号を保존）
  - `checks.check_first_name_rows(filename: str, rows: List[List[str]]) -> List[Finding]`
  - `checks.check_last_name_rows(filename: str, rows: List[List[str]]) -> List[Finding]`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_checks.py
"""checks.py（決定的チェック関数）のテスト。"""
import checks


def _findings_by_check(findings, check):
    return [f for f in findings if f.check == check]


class TestFirstNameChecks:
    def test_clean_rows_no_findings(self):
        rows = [["あい", "ai", "藍"], ["かおる", "kaoru", "薫", "香"]]
        assert checks.check_first_name_rows("f.csv", rows) == []

    def test_bad_charset(self):
        rows = [["アイ", "ai", "藍"], ["あい", "AI!", "藍"]]
        fs = checks.check_first_name_rows("f.csv", rows)
        assert len(_findings_by_check(fs, "format_error")) == 2
        assert all(f.severity == "error" for f in fs)
        assert fs[0].file == "f.csv" and fs[0].line == 1

    def test_too_few_columns(self):
        fs = checks.check_first_name_rows("f.csv", [["あい"]])
        assert _findings_by_check(fs, "format_error")

    def test_kanji_contamination_and_blank(self):
        rows = [["あい", "ai", "藍1"], ["かい", "kai", " 快"]]
        fs = checks.check_first_name_rows("f.csv", rows)
        assert len(_findings_by_check(fs, "format_error")) == 2

    def test_duplicates(self):
        rows = [["あい", "ai", "藍", "藍"], ["あい", "ai", "愛"]]
        fs = checks.check_first_name_rows("f.csv", rows)
        dup = _findings_by_check(fs, "duplicate")
        # 行内漢字重複 + 読み重複
        assert len(dup) == 2
        assert all(f.severity == "warning" for f in dup)

    def test_empty_row_and_no_kanji_are_warnings(self):
        fs = checks.check_first_name_rows("f.csv", [[], ["あい", "ai"]])
        assert all(f.severity == "warning" for f in fs)
        assert len(fs) == 2


class TestLastNameChecks:
    def test_clean(self):
        rows = [["佐藤", "1887000", "さとう", "satou"]]
        assert checks.check_last_name_rows("l.csv", rows) == []

    def test_wrong_columns_and_population(self):
        fs = checks.check_last_name_rows(
            "l.csv", [["佐藤", "さとう", "satou"], ["鈴木", "多い", "すずき", "suzuki"]]
        )
        assert len(_findings_by_check(fs, "format_error")) == 2

    def test_duplicate_surname(self):
        rows = [["佐藤", "1", "さとう", "satou"], ["佐藤", "2", "さとう", "satou"]]
        fs = checks.check_last_name_rows("l.csv", rows)
        assert _findings_by_check(fs, "duplicate")


class TestLoadRows:
    def test_load(self, tmp_path):
        p = tmp_path / "x.csv"
        p.write_text("あい,ai,藍\n\nかい,kai,快\n", encoding="utf-8")
        rows = checks.load_rows(str(p))
        assert rows == [["あい", "ai", "藍"], [], ["かい", "kai", "快"]]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_checks.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'checks'`）

- [ ] **Step 3: checks.py を実装（既存 validate.py のロジックを移設）**

```python
# .claude/skills/validate-dataset/scripts/checks.py
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
```

- [ ] **Step 4: validate.py を CLI ラッパーに書き換え**

既存の `validate_first_name_file` / `validate_last_name_file` と正規表現定義を削除し、checks.py に委譲する。出力形式（`ERROR   file:line: message` 形式・行数表示・結果サマリ・終了コード）は現行と同一に保つ。

```python
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
```

- [ ] **Step 5: テストと実データ検証の両方を確認**

Run: `uv run pytest tests/test_qa_checks.py -v && python3 .claude/skills/validate-dataset/scripts/validate.py`
Expected: pytest PASS。validate.py は従来と同じ出力形式（行数・ERROR/WARNING・サマリ）で終了する（既存データに対する検出結果が変わらないこと）

- [ ] **Step 6: コミット**

```bash
git add tests/test_qa_checks.py .claude/skills/validate-dataset/scripts/checks.py .claude/skills/validate-dataset/scripts/validate.py
git commit -m "Extract deterministic checks into reusable checks module

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: 新チェック（ローマ字照合・クロスファイル整合性・方式統計）

**Files:**
- Modify: `.claude/skills/validate-dataset/scripts/checks.py`（関数追加）
- Modify: `.claude/skills/validate-dataset/scripts/validate.py`（新チェックの呼び出しと統計表示）
- Test: `tests/test_qa_checks.py`（クラス追加）

**Interfaces:**
- Consumes: Task 1-2 の `romaji.romaji_candidates` / `romaji.classify_style`、Task 3 の `Finding`
- Produces:
  - `checks.check_romaji_reading(filename: str, rows: List[List[str]], kind: str) -> List[Finding]` — kind は `"first"`（読み=列0, ローマ字=列1）または `"last"`（読み=列2, ローマ字=列3）。候補集合に一致しない行を `romaji_reading_mismatch` / error で返す。
  - `checks.check_opti_subset(opti_filename: str, opti_rows, org_rows) -> List[Finding]` — opti の読みが org に無い（error）、ローマ字が org と異なる（error）、漢字が org の部分集合でない（warning）。check は `cross_file_inconsistency`。
  - `checks.check_gender_overlap(man_rows, woman_rows) -> List[Finding]` — 男女両ファイルに同じ読みがあってローマ字が食い違う場合のみ warning。共通読みの件数は info 1件で報告。
  - `checks.romaji_style_stats(rows: List[List[str]], kind: str) -> Dict[str, int]` — `classify_style` の結果を集計（キー: neutral/wapuro/shortened/mixed/unknown）。

- [ ] **Step 1: 失敗するテストを追加**

```python
# tests/test_qa_checks.py に追加
class TestRomajiReadingCheck:
    def test_match_passes(self):
        rows = [["さとう", "satou", "佐藤"], ["いっしゅう", "isshu", "一秀"]]
        assert checks.check_romaji_reading("f.csv", rows, "first") == []

    def test_mismatch_flagged(self):
        fs = checks.check_romaji_reading("f.csv", [["さとう", "satoh", "佐藤"]], "first")
        assert len(fs) == 1
        assert fs[0].check == "romaji_reading_mismatch"
        assert fs[0].severity == "error"

    def test_last_name_columns(self):
        rows = [["佐藤", "1887000", "さとう", "satou"]]
        assert checks.check_romaji_reading("l.csv", rows, "last") == []
        rows = [["佐藤", "1887000", "さとう", "sazou"]]
        assert len(checks.check_romaji_reading("l.csv", rows, "last")) == 1

    def test_untokenizable_reading_flagged(self):
        fs = checks.check_romaji_reading("f.csv", [["あゃ", "aya", "彩"]], "first")
        assert len(fs) == 1

    def test_short_or_malformed_rows_skipped(self):
        # 列数不足は check_first_name_rows が報告するのでここでは黙ってスキップ
        assert checks.check_romaji_reading("f.csv", [[], ["あい"]], "first") == []


class TestCrossFileChecks:
    def test_opti_subset_ok(self):
        org = [["あい", "ai", "藍", "愛"]]
        opti = [["あい", "ai", "藍"]]
        assert checks.check_opti_subset("o.csv", opti, org) == []

    def test_opti_missing_reading(self):
        fs = checks.check_opti_subset("o.csv", [["かい", "kai", "快"]], [["あい", "ai", "藍"]])
        assert [f for f in fs if f.severity == "error"]

    def test_opti_extra_kanji_is_warning(self):
        org = [["あい", "ai", "藍"]]
        opti = [["あい", "ai", "藍", "愛"]]
        fs = checks.check_opti_subset("o.csv", opti, org)
        assert [f for f in fs if f.severity == "warning"]

    def test_gender_overlap(self):
        man = [["かおる", "kaoru", "薫"]]
        woman = [["かおる", "kaolu", "香"]]
        fs = checks.check_gender_overlap(man, woman)
        assert [f for f in fs if f.severity == "warning"]  # ローマ字食い違い
        assert [f for f in fs if f.severity == "info"]     # 共通読みサマリ


class TestStyleStats:
    def test_stats(self):
        rows = [["さとう", "satou", "佐"], ["いっしゅう", "isshu", "一"], ["あい", "ai", "藍"]]
        stats = checks.romaji_style_stats(rows, "first")
        assert stats["wapuro"] == 1
        assert stats["shortened"] == 1
        assert stats["neutral"] == 1
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_checks.py -v`
Expected: 新クラスのみ FAIL（AttributeError）、既存クラスは PASS

- [ ] **Step 3: checks.py に新チェックを実装**

```python
# checks.py 冒頭の import に追加
import romaji as romaji_mod

# checks.py 末尾に追加

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
```

- [ ] **Step 4: validate.py に新チェックを組み込む**

`main()` のループ後（`errors` 集計の前）に以下を追加。org 版の読み込み結果を再利用するため、ループ内で `all_rows[filename] = rows` と保持するよう変更する。

```python
    # ループの前に:
    all_rows = {}
    # ループ内 rows 取得直後に:
    #     all_rows[filename] = rows
    # ループ内の check 呼び出しに追加:
    #     kind = "last" if filename in LAST_NAME_FILES else "first"
    #     findings.extend(checks.check_romaji_reading(filename, rows, kind))

    # ループの後に:
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
```

info レベルの Finding はエラー/警告と別に `INFO` プレフィックス（8桁揃え）で出力に追加する（終了コードには影響しない）。

- [ ] **Step 5: テストと実データでの確認**

Run: `uv run pytest tests/test_qa_checks.py tests/test_qa_romaji.py -v && python3 .claude/skills/validate-dataset/scripts/validate.py; echo "exit=$?"`
Expected: pytest PASS。validate.py は実データの romaji_reading_mismatch 件数と方式分布を出力する（**この時点で既存データにエラーが出るのは想定内**。件数をメモし、Task 10 の初回クリーニングの入力にする）

- [ ] **Step 6: コミット**

```bash
git add tests/test_qa_checks.py .claude/skills/validate-dataset/scripts/checks.py .claude/skills/validate-dataset/scripts/validate.py
git commit -m "Add romaji-reading verification, cross-file checks and style stats

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: findings 台帳と検証済みキャッシュ `findings_io.py`

**Files:**
- Create: `.claude/skills/validate-dataset/scripts/findings_io.py`
- Test: `tests/test_qa_findings_io.py`

**Interfaces:**
- Consumes: なし（独立モジュール）
- Produces:
  - `findings_io.entry_hash(filename: str, raw_line: str) -> str` — sha256 先頭16桁hex
  - `findings_io.validate_finding(d: dict) -> List[str]` — スキーマ違反メッセージのリスト（空 = 正常）
  - `findings_io.append_findings(path: str, findings: List[dict]) -> None` — JSONL 追記（親ディレクトリ自動作成、追記前に全件 validate し、1件でも不正なら `ValueError`）
  - `findings_io.load_findings(path: str) -> List[dict]`
  - `findings_io.save_findings(path: str, findings: List[dict]) -> None` — 全置換（status 更新用）
  - `findings_io.load_verified(path: str) -> Dict[str, dict]` — 無ければ `{}`
  - `findings_io.save_verified(path: str, verified: Dict[str, dict]) -> None` — キーでソートし indent=1 で保存（diff を安定させる）
  - 定数: `CHECK_TYPES`, `ACTIONS`, `STATUSES`, `CONFIDENCES`, `SEVERITIES`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_findings_io.py
"""findings_io.py（疑義台帳・検証済みキャッシュ）のテスト。"""
import os

import pytest

import findings_io


def _valid_finding():
    return {
        "id": "fn-man-org:あいいちろう",
        "file": "first_name_man_org.csv",
        "entry": "あいいちろう,aichirou,愛一朗,愛一郎",
        "check": "kanji_reading_mismatch",
        "severity": "error",
        "confidence": "high",
        "evidence": "愛一朗を「あいいちろう」と読む用例が確認できない",
        "proposed_fix": {"action": "remove_kanji", "value": "愛一朗"},
        "status": "pending",
        "detected_at": "2026-07-27",
        "detected_by": "qa-review v1",
    }


class TestValidateFinding:
    def test_valid(self):
        assert findings_io.validate_finding(_valid_finding()) == []

    def test_missing_field(self):
        f = _valid_finding()
        del f["evidence"]
        assert findings_io.validate_finding(f)

    def test_bad_enum_values(self):
        for key, bad in [
            ("check", "spelling"), ("severity", "fatal"),
            ("confidence", "certain"), ("status", "done"),
        ]:
            f = _valid_finding()
            f[key] = bad
            assert findings_io.validate_finding(f), key

    def test_bad_action(self):
        f = _valid_finding()
        f["proposed_fix"] = {"action": "delete_everything", "value": ""}
        assert findings_io.validate_finding(f)


class TestJsonlRoundtrip:
    def test_append_and_load(self, tmp_path):
        p = str(tmp_path / "sub" / "f.jsonl")
        findings_io.append_findings(p, [_valid_finding()])
        findings_io.append_findings(p, [_valid_finding()])
        assert len(findings_io.load_findings(p)) == 2

    def test_append_rejects_invalid(self, tmp_path):
        p = str(tmp_path / "f.jsonl")
        bad = _valid_finding()
        bad["status"] = "???"
        with pytest.raises(ValueError):
            findings_io.append_findings(p, [bad])
        assert not os.path.exists(p)

    def test_save_replaces(self, tmp_path):
        p = str(tmp_path / "f.jsonl")
        f = _valid_finding()
        findings_io.append_findings(p, [f])
        f2 = dict(f)
        f2["status"] = "approved"
        findings_io.save_findings(p, [f2])
        assert findings_io.load_findings(p)[0]["status"] == "approved"


class TestVerifiedCache:
    def test_hash_is_stable_and_content_sensitive(self):
        h1 = findings_io.entry_hash("a.csv", "あい,ai,藍")
        assert h1 == findings_io.entry_hash("a.csv", "あい,ai,藍")
        assert h1 != findings_io.entry_hash("b.csv", "あい,ai,藍")
        assert h1 != findings_io.entry_hash("a.csv", "あい,ai,愛")
        assert len(h1) == 16

    def test_load_missing_returns_empty(self, tmp_path):
        assert findings_io.load_verified(str(tmp_path / "v.json")) == {}

    def test_roundtrip(self, tmp_path):
        p = str(tmp_path / "v.json")
        findings_io.save_verified(p, {"abc": {"file": "a.csv", "reading": "あい",
                                              "verified_at": "2026-07-27"}})
        assert "abc" in findings_io.load_verified(p)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_findings_io.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'findings_io'`）

- [ ] **Step 3: findings_io.py を実装**

```python
# .claude/skills/validate-dataset/scripts/findings_io.py
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
    with open(path, "a", encoding="utf-8") as f:
        for d in findings:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def load_findings(path):
    # type: (str) -> List[dict]
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def save_findings(path, findings):
    # type: (str, List[dict]) -> None
    with open(path, "w", encoding="utf-8") as f:
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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(verified, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_findings_io.py -v`
Expected: PASS（全件）

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_findings_io.py .claude/skills/validate-dataset/scripts/findings_io.py
git commit -m "Add findings ledger and verified-cache IO with schema validation

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: バッチ準備・結果マージ `qa_batch.py`

**Files:**
- Create: `.claude/skills/qa-review/scripts/qa_batch.py`
- Modify: `.gitignore`（`qa/work/` を追加）
- Test: `tests/test_qa_batch.py`

**Interfaces:**
- Consumes: Task 3-4 の `checks.load_rows` / `check_romaji_reading` / `romaji_style_stats`、Task 5 の `findings_io` 全API
- Produces（CLI）:
  - `python3 .claude/skills/qa-review/scripts/qa_batch.py prep --dataset-dir D --qa-dir Q --out-dir W [--batch-size 100]` — 未検証エントリをバッチ JSON に分割して W に書き出し、`manifest.json` を作る
  - `python3 .claude/skills/qa-review/scripts/qa_batch.py merge --qa-dir Q --work-dir W --run-id R` — `W/results/*.json` を検証してマージ
- Produces（ファイル形式）:
  - バッチ: `W/batch_001.json` = `{"batch_id": "batch_001", "entries": [{"file": ..., "line": n, "raw": "あい,ai,藍", "reading": "あい", "romaji": "ai", "kanji": ["藍"], "hash": "...", "deterministic_error": "..." または null}]}`
  - マニフェスト: `W/manifest.json` = `{"batch_ids": [...], "total_entries": n, "skipped_verified": m, "style_stats": {ファイル名: {neutral/wapuro/shortened/mixed/unknown: 件数}}}`（style_stats は全行対象。FR-5 の方式混在統計としてレポートに転記される）
  - 結果（サブエージェントが書く）: `W/results/batch_001.json` = `{"batch_id": "batch_001", "findings": [<スキーマ準拠 finding>...], "ok_hashes": ["..."]}`
  - マージ出力: `Q/findings/<run-id>.jsonl` 追記、`Q/verified.json` 更新、`Q/reports/<run-id>.md` 生成

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_batch.py
"""qa_batch.py（LLM レビューのバッチ準備・結果マージ）のテスト。"""
import json
import os

import findings_io
import qa_batch


def _write_dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text(
        "あい,ai,藍\nかおる,kaoru,薫\n", encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("あい,ai,藍\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
    return str(d)


def _finding_for(file, raw, reading):
    return {
        "id": "%s:%s" % (file, reading), "file": file, "entry": raw,
        "check": "not_a_name", "severity": "error", "confidence": "high",
        "evidence": "テスト用", "proposed_fix": {"action": "remove_row", "value": ""},
        "status": "pending", "detected_at": "2026-07-27", "detected_by": "qa-review v1",
    }


class TestPrep:
    def test_prep_writes_batches_and_manifest(self, tmp_path):
        ds = _write_dataset(tmp_path)
        work = str(tmp_path / "work")
        qa_batch.prep(ds, str(tmp_path / "qa"), work, batch_size=2)
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        # 全6エントリ（4ファイル5行 + 姓1行）が2件ずつのバッチに分かれる
        assert manifest["total_entries"] == 6
        assert len(manifest["batch_ids"]) == 3
        assert manifest["style_stats"]["first_name_man_org.csv"]["neutral"] == 2
        b1 = json.load(open(os.path.join(work, "batch_001.json"), encoding="utf-8"))
        e = b1["entries"][0]
        assert set(e) >= {"file", "line", "raw", "reading", "romaji", "kanji", "hash"}

    def test_prep_skips_verified(self, tmp_path):
        ds = _write_dataset(tmp_path)
        qa_dir = str(tmp_path / "qa")
        h = findings_io.entry_hash("first_name_man_org.csv", "あい,ai,藍")
        findings_io.save_verified(os.path.join(qa_dir, "verified.json"),
                                  {h: {"file": "first_name_man_org.csv",
                                       "reading": "あい", "verified_at": "2026-07-27"}})
        work = str(tmp_path / "work")
        qa_batch.prep(ds, qa_dir, work, batch_size=100)
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        assert manifest["total_entries"] == 5
        assert manifest["skipped_verified"] == 1


class TestMerge:
    def _prep(self, tmp_path):
        ds = _write_dataset(tmp_path)
        qa_dir = str(tmp_path / "qa")
        work = str(tmp_path / "work")
        qa_batch.prep(ds, qa_dir, work, batch_size=100)
        return ds, qa_dir, work

    def test_merge_appends_findings_and_verifies_ok(self, tmp_path):
        ds, qa_dir, work = self._prep(tmp_path)
        batch = json.load(open(os.path.join(work, "batch_001.json"), encoding="utf-8"))
        target = batch["entries"][0]
        ok_hashes = [e["hash"] for e in batch["entries"][1:]]
        os.makedirs(os.path.join(work, "results"))
        with open(os.path.join(work, "results", "batch_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": "batch_001",
                       "findings": [_finding_for(target["file"], target["raw"],
                                                 target["reading"])],
                       "ok_hashes": ok_hashes}, f, ensure_ascii=False)
        summary = qa_batch.merge(qa_dir, work, "test-run")
        fs = findings_io.load_findings(
            os.path.join(qa_dir, "findings", "test-run.jsonl"))
        assert len(fs) == 1
        verified = findings_io.load_verified(os.path.join(qa_dir, "verified.json"))
        assert len(verified) == len(ok_hashes)
        assert target["hash"] not in verified  # 疑義ありは verified に入らない
        assert summary["missing_batches"] == []
        report = open(os.path.join(qa_dir, "reports", "test-run.md"),
                      encoding="utf-8").read()
        assert "test-run" in report and target["reading"] in report

    def test_merge_reports_missing_batches(self, tmp_path):
        ds, qa_dir, work = self._prep(tmp_path)
        os.makedirs(os.path.join(work, "results"))  # 結果ファイルなし
        summary = qa_batch.merge(qa_dir, work, "test-run2")
        assert summary["missing_batches"] == ["batch_001"]
        report = open(os.path.join(qa_dir, "reports", "test-run2.md"),
                      encoding="utf-8").read()
        assert "batch_001" in report

    def test_merge_rejects_invalid_finding(self, tmp_path):
        ds, qa_dir, work = self._prep(tmp_path)
        os.makedirs(os.path.join(work, "results"))
        with open(os.path.join(work, "results", "batch_001.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"batch_id": "batch_001",
                       "findings": [{"id": "broken"}], "ok_hashes": []}, f)
        summary = qa_batch.merge(qa_dir, work, "test-run3")
        # 不正な結果ファイルは取り込まず、未処理扱いにする
        assert summary["invalid_batches"] == ["batch_001"]
        assert not os.path.exists(os.path.join(qa_dir, "findings", "test-run3.jsonl"))
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_batch.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'qa_batch'`）

- [ ] **Step 3: qa_batch.py を実装**

```python
# .claude/skills/qa-review/scripts/qa_batch.py
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
```

- [ ] **Step 4: .gitignore に作業ディレクトリを追加**

`.gitignore` の末尾に追加:

```text
# QA レビューの一時作業ファイル（バッチ・サブエージェント結果）
qa/work/
```

- [ ] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_batch.py -v`
Expected: PASS（全件）

- [ ] **Step 6: コミット**

```bash
git add tests/test_qa_batch.py .claude/skills/qa-review/scripts/qa_batch.py .gitignore
git commit -m "Add batch prep and result merge tooling for LLM QA review

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: `/qa-review` スキル文書

**Files:**
- Create: `.claude/skills/qa-review/SKILL.md`

**Interfaces:**
- Consumes: Task 6 の qa_batch.py CLI とファイル形式
- Produces: Claude Code が `/qa-review` で実行する手順書（サブエージェントプロンプト込み）

- [ ] **Step 1: SKILL.md を書く**

````markdown
---
name: qa-review
description: Use when dataset CSV の LLM 品質レビューを実行するとき（漢字と読みの対応・人名らしさ・男女ファイル配置の検証）、または「QAレビュー」「品質チェック」「疑義検出」を求められたとき。決定的チェックは /validate-dataset を使う。
---

# dataset LLM 品質レビュー

エントリごとに (a) 漢字と読みの対応妥当性 (b) 日本人名としての実在性
(c) 収録ファイルの妥当性を判定し、疑義を qa/findings/ に記録する。
判定以外はすべて qa_batch.py が決定的に処理する。

## 手順

1. `git status` がクリーンであることを確認（差分があればユーザーに確認）。
2. run-id を決める: `YYYY-MM-<対象>` 形式（例: `2026-07-full`）。
3. バッチ準備:
   ```bash
   python3 .claude/skills/qa-review/scripts/qa_batch.py prep \
     --dataset-dir japanese_personal_name_dataset/dataset \
     --qa-dir qa --out-dir qa/work/<run-id> --batch-size 100
   ```
4. `qa/work/<run-id>/manifest.json` の batch_ids ごとに、下のプロンプトで
   サブエージェント（general-purpose）を起動する。同時実行は 4 つまで。
   全バッチの結果ファイルが揃うまで繰り返す。
5. マージ:
   ```bash
   python3 .claude/skills/qa-review/scripts/qa_batch.py merge \
     --qa-dir qa --work-dir qa/work/<run-id> --run-id <run-id>
   ```
6. 未処理/不正バッチが報告されたら、そのバッチだけ手順4をやり直して再マージ。
7. `qa/reports/<run-id>.md` をユーザーに提示し、`qa/findings/<run-id>.jsonl`
   と `qa/verified.json` をコミットする（dataset CSV は変更しない）。

## サブエージェントプロンプト（テンプレート）

```
あなたは日本人の姓名データセットの品質監査員です。
<batch-file の絶対パス> を読み、entries の各エントリを判定してください。

判定観点:
(a) kanji の各表記は reading の読みで実在の日本人名として妥当か
(b) reading/kanji は人名か（地名・一般名詞・スクレイピング残骸ではないか）
(c) file の配置は妥当か（例: 明らかに女性名が first_name_man_org.csv にある）
- deterministic_error が付いているエントリは読みとローマ字の不一致が機械検出
  済み。どちらの列が誤りかを判断し fix_romaji / fix_reading を提案すること。
- 判断に迷う場合は「疑義あり・confidence: low」とする（OK にしない）。
- 珍しいだけの名前（キラキラネーム含む）は OK とする。確実に誤りと言える
  根拠があるものだけを疑義とする。

出力: <work-dir>/results/<batch_id>.json に以下の JSON を書く。
{
  "batch_id": "<batch_id>",
  "findings": [
    {"id": "<file>:<reading>", "file": "<file>", "entry": "<raw をそのまま>",
     "check": "kanji_reading_mismatch | not_a_name | wrong_gender_file | romaji_reading_mismatch",
     "severity": "error", "confidence": "high | medium | low",
     "evidence": "<日本語で根拠>",
     "proposed_fix": {"action": "remove_row | remove_kanji | fix_romaji | fix_reading | move_to_file | none", "value": "<対象値>"},
     "status": "pending", "detected_at": "<今日の日付 YYYY-MM-DD>",
     "detected_by": "qa-review v1"}
  ],
  "ok_hashes": ["<問題なしと判定した全エントリの hash>"]
}
findings に入れたエントリの hash は ok_hashes に入れないこと。
全エントリが findings か ok_hashes のどちらかに必ず入ること。
```

## 注意

- このスキルは dataset CSV を一切変更しない。修正の適用は /qa-apply。
- qa/work/ は .gitignore 済みの一時領域。コミットするのは qa/findings/・
  qa/verified.json・qa/reports/ のみ。
````

- [ ] **Step 2: 小規模サンプルでドライラン検証**

1. `python3 .claude/skills/qa-review/scripts/qa_batch.py prep --dataset-dir japanese_personal_name_dataset/dataset --qa-dir /tmp/qa-dry --out-dir /tmp/qa-dry/work --batch-size 100` を実行し、バッチが生成されることを確認（`--qa-dir` を一時領域にして本番の qa/ を汚さない）。
2. `batch_001.json` の先頭 5 エントリだけを手動で判定するサブエージェントを 1 回起動し、結果 JSON がスキーマを通ることを `merge` の実行で確認。
3. `/tmp/qa-dry` を削除。

Expected: prep→サブエージェント→merge の一連が通り、レポートが生成される

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/qa-review/SKILL.md
git commit -m "Add qa-review skill for LLM-based dataset quality review

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: 修正適用 `apply_findings.py` と `/qa-apply` スキル

**Files:**
- Create: `.claude/skills/qa-apply/scripts/apply_findings.py`
- Create: `.claude/skills/qa-apply/SKILL.md`
- Test: `tests/test_qa_apply.py`

**Interfaces:**
- Consumes: Task 5 の `findings_io` 全API
- Produces（CLI）:
  - `python3 .claude/skills/qa-apply/scripts/apply_findings.py --findings F.jsonl --dataset-dir D --qa-dir Q [--from-report R.md] [--dry-run]`
  - `--from-report`: レポート内でチェック済みの行（`- [x]` に続くバッククォート内の finding id）を読んで該当 finding を approved に昇格してから適用
  - 動作: status==approved のみ適用（remove_row / remove_kanji / fix_romaji / fix_reading / move_to_file）。適用成功→`applied`、行が見つからない→スキップして報告。rejected の finding はエントリを verified.json に登録（誤検出の再発防止）。`--dry-run` はファイルを書かず予定を表示。
- Produces（Python 関数、テスト用）: `apply_findings.apply(findings_path, dataset_dir, qa_dir, report_path=None, dry_run=False) -> dict`（`{"applied": n, "skipped": [...], "rejected_verified": m}`）

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_apply.py
"""apply_findings.py（承認済み修正の一括適用）のテスト。"""
import os

import apply_findings
import findings_io


def _write_dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text(
        "ああす,asu,亜明日\nあい,ai,藍,愛\nかおる,kaoru,薫\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    return str(d)


def _finding(file, entry, action, value, status="approved", check="not_a_name"):
    return {
        "id": "%s:%s" % (file, entry.split(",")[0]), "file": file, "entry": entry,
        "check": check, "severity": "error", "confidence": "high",
        "evidence": "テスト用", "proposed_fix": {"action": action, "value": value},
        "status": status, "detected_at": "2026-07-27", "detected_by": "qa-review v1",
    }


class TestApply:
    def test_remove_row_and_remove_kanji(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", ""),
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "愛",
                     check="kanji_reading_mismatch"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 2
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "ああす" not in content
        assert "あい,ai,藍\n" in content
        # 適用済み finding は applied になる
        statuses = [d["status"] for d in findings_io.load_findings(fp)]
        assert statuses == ["applied", "applied"]

    def test_fix_romaji_and_reading(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "かおる,kaoru,薫", "fix_romaji", "kaworu",
                     check="romaji_reading_mismatch"),
        ])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "かおる,kaworu,薫\n" in content

    def test_move_to_file_keeps_sort_order(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "かおる,kaoru,薫", "move_to_file",
                     "first_name_woman_org.csv", check="wrong_gender_file"),
        ])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        man = open(os.path.join(ds, "first_name_man_org.csv"), encoding="utf-8").read()
        woman = open(os.path.join(ds, "first_name_woman_org.csv"), encoding="utf-8").read()
        assert "かおる" not in man
        # 読みの昇順で挿入される（かおる < さくら）
        assert woman == "かおる,kaoru,薫\nさくら,sakura,桜\n"

    def test_pending_not_applied_and_rejected_goes_to_verified(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", "",
                     status="pending"),
            _finding("first_name_man_org.csv", "あい,ai,藍,愛", "remove_kanji", "愛",
                     status="rejected"),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 0
        assert result["rejected_verified"] == 1
        content = open(os.path.join(ds, "first_name_man_org.csv"),
                       encoding="utf-8").read()
        assert "ああす" in content and "愛" in content
        verified = findings_io.load_verified(
            str(tmp_path / "qa" / "verified.json"))
        h = findings_io.entry_hash("first_name_man_org.csv", "あい,ai,藍,愛")
        assert h in verified

    def test_entry_not_found_is_skipped(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "存在しない,nai,無", "remove_row", ""),
        ])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 0
        assert len(result["skipped"]) == 1
        # 見つからなかった finding は approved のまま残る
        assert findings_io.load_findings(fp)[0]["status"] == "approved"

    def test_dry_run_writes_nothing(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [
            _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", ""),
        ])
        before = open(os.path.join(ds, "first_name_man_org.csv"),
                      encoding="utf-8").read()
        apply_findings.apply(fp, ds, str(tmp_path / "qa"), dry_run=True)
        after = open(os.path.join(ds, "first_name_man_org.csv"),
                     encoding="utf-8").read()
        assert before == after
        assert findings_io.load_findings(fp)[0]["status"] == "approved"

    def test_from_report_promotes_checked(self, tmp_path):
        ds = _write_dataset(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        f = _finding("first_name_man_org.csv", "ああす,asu,亜明日", "remove_row", "",
                     status="pending")
        findings_io.append_findings(fp, [f])
        report = tmp_path / "r.md"
        report.write_text("- [x] `%s` **not_a_name** ..." % f["id"], encoding="utf-8")
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"),
                                      report_path=str(report))
        assert result["applied"] == 1
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_apply.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'apply_findings'`）

- [ ] **Step 3: apply_findings.py を実装**

```python
# .claude/skills/qa-apply/scripts/apply_findings.py
"""承認済み findings を dataset CSV に一括適用する。

必ずユーザーの明示承認を得てから実行すること（CLAUDE.md のデータ保護方針）。
status==approved のみ適用し、適用後は applied に更新する。
rejected の finding はエントリを verified.json に登録し再検出を防ぐ。
"""
import argparse
import bisect
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "validate-dataset", "scripts")))

import findings_io  # noqa: E402

_REPORT_CHECKED_RE = re.compile(r"^- \[x\] `([^`]+)`", re.IGNORECASE)


def _read_lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def _write_lines(path, lines):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def _apply_one(lines, finding):
    # type: (list, dict) -> tuple
    """1件適用し (新lines, 移動行 or None, 成功か) を返す。"""
    entry = finding["entry"]
    action = finding["proposed_fix"]["action"]
    value = finding["proposed_fix"].get("value", "")
    if entry not in lines:
        return lines, None, False
    idx = lines.index(entry)
    if action == "remove_row":
        return lines[:idx] + lines[idx + 1:], None, True
    if action == "move_to_file":
        return lines[:idx] + lines[idx + 1:], entry, True
    cols = entry.split(",")
    if action == "remove_kanji":
        cols = [cols[0], cols[1]] + [k for k in cols[2:] if k != value]
    elif action == "fix_romaji":
        cols[1] = value
    elif action == "fix_reading":
        cols[0] = value
    elif action == "none":
        return lines, None, True
    lines[idx] = ",".join(cols)
    return lines, None, True


def apply(findings_path, dataset_dir, qa_dir, report_path=None, dry_run=False):
    # type: (str, str, str, str, bool) -> dict
    findings = findings_io.load_findings(findings_path)
    if report_path:
        checked = set()
        for line in _read_lines(report_path):
            m = _REPORT_CHECKED_RE.match(line.strip())
            if m:
                checked.add(m.group(1))
        for d in findings:
            if d["id"] in checked and d["status"] == "pending":
                d["status"] = "approved"
    applied = 0
    skipped = []
    file_lines = {}  # type: dict
    moves = []  # (target_file, raw_line)
    for d in findings:
        if d["status"] != "approved":
            continue
        fname = d["file"]
        if fname not in file_lines:
            file_lines[fname] = _read_lines(os.path.join(dataset_dir, fname))
        new_lines, moved, ok = _apply_one(file_lines[fname], d)
        if not ok:
            skipped.append(d["id"])
            print("スキップ（行が見つかりません）: %s" % d["id"])
            continue
        file_lines[fname] = new_lines
        if moved is not None:
            moves.append((d["proposed_fix"]["value"], moved))
        d["status"] = "applied"
        applied += 1
    for target, raw in moves:
        if target not in file_lines:
            file_lines[target] = _read_lines(os.path.join(dataset_dir, target))
        keys = [ln.split(",")[0] for ln in file_lines[target]]
        pos = bisect.bisect_left(keys, raw.split(",")[0])
        file_lines[target].insert(pos, raw)
    rejected = [d for d in findings if d["status"] == "rejected"]
    if not dry_run:
        for fname, lines in file_lines.items():
            _write_lines(os.path.join(dataset_dir, fname), lines)
        findings_io.save_findings(findings_path, findings)
        if rejected:
            verified_path = os.path.join(qa_dir, "verified.json")
            verified = findings_io.load_verified(verified_path)
            today = datetime.date.today().isoformat()
            for d in rejected:
                h = findings_io.entry_hash(d["file"], d["entry"])
                verified[h] = {"file": d["file"],
                               "reading": d["entry"].split(",")[0],
                               "verified_at": today}
            findings_io.save_verified(verified_path, verified)
    return {"applied": applied, "skipped": skipped,
            "rejected_verified": len(rejected)}


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--qa-dir", required=True)
    parser.add_argument("--from-report")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = apply(args.findings, args.dataset_dir, args.qa_dir,
                   report_path=args.from_report, dry_run=args.dry_run)
    mode = "（dry-run）" if args.dry_run else ""
    print("適用 %d 件%s / スキップ %d 件 / rejected→verified %d 件"
          % (result["applied"], mode, len(result["skipped"]),
             result["rejected_verified"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_apply.py -v`
Expected: PASS（全件）

- [ ] **Step 5: /qa-apply の SKILL.md を書く**

````markdown
---
name: qa-apply
description: Use when qa/findings/ の承認済み疑義を dataset CSV に適用するとき、または「QA適用」「findings 適用」「クリーニング実行」を求められたとき。適用前に必ずユーザーの明示承認を得ること。
---

# 承認済み findings の一括適用

## 前提

- dataset CSV は PreToolUse フックで保護されている。このスキルは
  apply_findings.py（Bash 実行）で適用するが、**実行前に必ずユーザーへ
  適用内容を提示して明示承認を得ること**。承認なしで実行してはならない。

## 手順

1. 対象の findings ファイルを確認し、dry-run で適用予定を提示する:
   ```bash
   python3 .claude/skills/qa-apply/scripts/apply_findings.py \
     --findings qa/findings/<run-id>.jsonl \
     --dataset-dir japanese_personal_name_dataset/dataset \
     --qa-dir qa \
     --from-report qa/reports/<run-id>.md --dry-run
   ```
2. 適用予定（件数・内容）をユーザーに提示し、**明示承認を得る**。
3. ブランチを切る: `git checkout -b qa/apply-<run-id>`
4. `--dry-run` を外して実行する。
5. 回帰確認:
   ```bash
   python3 .claude/skills/validate-dataset/scripts/validate.py
   uv run pytest tests/ -v
   ```
6. 行数が変わった場合は以下の件数表記をすべて更新する:
   - `README.md` / `README_EN.md`（データ件数）
   - `CLAUDE.md`（データセット構造の件数）
   - `tests/test_core.py`（期待件数のアサーション）
   - `.claude/skills/validate-dataset/SKILL.md`（期待行数）
7. diff をユーザーに提示してからコミットし、PR を作るか main へマージするかを
   ユーザーに確認する。
8. 適用後の findings JSONL（status: applied/rejected）と qa/verified.json も
   同じコミットに含める（監査証跡）。
````

- [ ] **Step 6: コミット**

```bash
git add tests/test_qa_apply.py .claude/skills/qa-apply/
git commit -m "Add qa-apply skill and script for approved finding application

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: ドキュメント更新（SKILL.md・CLAUDE.md）

**Files:**
- Modify: `.claude/skills/validate-dataset/SKILL.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: Task 1-8 の成果物すべて
- Produces: 更新されたドキュメント

- [ ] **Step 1: validate-dataset/SKILL.md の検証内容表を更新**

「検証内容」の表に以下の行を追加し、末尾に構成説明を追記:

```markdown
| 読み⇔ローマ字 | ひらがな読みから許容ローマ字候補（ワープロ式・長音省略式・混合）を生成し、一致しない行を ERROR。表記方式の分布も出力 |
| クロスファイル | opti ⊆ org（読み・ローマ字・漢字）、男女ファイル間のローマ字食い違い |
```

```markdown
## 構成

- `scripts/validate.py` - CLI エントリポイント
- `scripts/checks.py` - チェック関数群（Phase 2 パイプラインから import 可能）
- `scripts/romaji.py` - ひらがな→ローマ字候補生成
- `scripts/findings_io.py` - 疑義台帳・検証済みキャッシュの入出力

LLM による品質レビューは /qa-review、承認済み修正の適用は /qa-apply を使う。
```

- [ ] **Step 2: CLAUDE.md に QA 基盤セクションを追加**

「Claude Code 自動化」セクション末尾の一文「その他: dataset CSV の検証は `/validate-dataset` スキル、リリース前の互換性レビューは `py38-compat-reviewer` サブエージェントを使用できます。」を以下に置き換える:

```markdown
### データ品質保証（QA基盤）

- `/validate-dataset`: 決定的チェック（形式・重複・読み⇔ローマ字照合・クロスファイル整合性）
- `/qa-review`: LLM 品質レビュー（漢字⇔読みの妥当性・人名らしさ・男女配置）。疑義は `qa/findings/*.jsonl` に、検証済みは `qa/verified.json` に記録
- `/qa-apply`: 承認済み findings の一括適用（ユーザーの明示承認必須）
- 設計書: `docs/superpowers/specs/2026-07-27-qa-foundation-design.md`
- リリース前の互換性レビューは `py38-compat-reviewer` サブエージェントを使用
```

- [ ] **Step 3: 全テスト実行で回帰がないことを確認**

Run: `uv run pytest tests/ -v`
Expected: PASS（全件）

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/validate-dataset/SKILL.md CLAUDE.md
git commit -m "Document QA foundation skills and architecture

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: 初回運用（クリーニング → CI 有効化 → v0.2.0）

実装ではなく運用タスク。構築したツール群で Phase 1 の完了定義を満たす。**各ステップでユーザーの判断・承認を挟む。**

**Files:**
- Modify: `.github/workflows/test.yml`（validate ジョブ追加）
- Modify: `japanese_personal_name_dataset/dataset/*.csv`（apply_findings.py 経由のみ）
- Modify: `README.md` / `README_EN.md` / `CLAUDE.md` / `tests/test_core.py` / `.claude/skills/validate-dataset/SKILL.md`（件数変更時）

- [ ] **Step 1: 決定的チェックの初回実行と結果の提示**

Run: `python3 .claude/skills/validate-dataset/scripts/validate.py`
検出された romaji_reading_mismatch・format_error の件数と内訳、方式分布をユーザーに報告する。

- [ ] **Step 2: /qa-review を全件実行**

`/qa-review` スキルの手順に従い、run-id `2026-MM-full` で全エントリをレビュー。決定的エラー行は `deterministic_error` 付きでサブエージェントに渡り、fix_romaji / fix_reading の提案が付く。レポートをユーザーに提示。

- [ ] **Step 3: ユーザーが findings を承認**

ユーザーがレポートのチェックボックス（または JSONL の status）で承認・却下を決める。confidence=high 以外はデフォルトで承認しない方針を提示する。

- [ ] **Step 4: /qa-apply で適用（ユーザー明示承認後）**

`/qa-apply` スキルの手順（dry-run → 承認 → ブランチ → 適用 → 回帰確認 → 件数表記更新）に従う。

- [ ] **Step 5: CI に validate ジョブを追加**

データがクリーンになった後、`.github/workflows/test.yml` に追加:

```yaml
  validate-dataset:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.12'
    - name: Validate dataset CSVs
      run: python3 .claude/skills/validate-dataset/scripts/validate.py
```

Run: `python3 .claude/skills/validate-dataset/scripts/validate.py; echo "exit=$?"`
Expected: `exit=0`（エラー0件）を確認してからコミット

- [ ] **Step 6: v0.2.0 リリース**

`/release` スキル（`.claude/skills/release/SKILL.md`）の手順に従い、バージョンを 0.2.0 に上げてリリースする。リリースノートに QA 基盤の導入とクリーニング結果（修正件数の内訳）を記載する。

- [ ] **Step 7: スペックの完了定義と照合**

`docs/superpowers/specs/2026-07-27-qa-foundation-design.md` §8 の 4 項目を1つずつ確認し、満たしていれば Issue（Milestone: Phase 1）をクローズする。

---

## 実行順序と依存関係

```text
Task 1 (romaji 基本) → Task 2 (長音・方式判定) ─┐
Task 3 (checks 分離) ──────────────────────────┴→ Task 4 (新チェック) ─┐
Task 5 (findings_io) ──────────────────────────┬───────────────────────┴→ Task 6 (qa_batch) → Task 7 (/qa-review)
                                                └→ Task 8 (/qa-apply)
Task 9 (ドキュメント) ← Task 1-8 完了後
Task 10 (初回運用) ← 全タスク完了後
```

Task 3 と Task 5 は Task 1-2 と独立に着手可能。Task 4 は Task 2 と 3 に、Task 6 は Task 4 と 5 に依存する。Task 8 は Task 5 のみに依存する。
