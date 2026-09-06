# 自動更新パイプライン（Phase 2）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wikidata と NDL 典拠から名の候補（新しい漢字表記・新しい読み）を根拠付きで生成し、Phase 1 の findings 台帳 → トリアージ UI → /qa-apply の導線で年次リリースできる `/qa-update` パイプラインを作る。

**Architecture:** 取得スクリプト（Wikidata SPARQL / NDL SPARQL の ID 接頭辞チャンク / JMnedict XML）が共通の正規化レコード JSONL を書き、`source_index.py` が `(kind, kanji, reading)` の統一索引を作る。`generate_candidates.py` が現データとの差分を `add_row` / `add_kanji` findings として出力し、`findings_io` / `apply_findings` / `triage_server` を拡張して既存導線で処理する。性別不明の新規読みは `gender_batch.py`（qa_batch と同型）でサブエージェント判定する。

**Tech Stack:** Python 標準ライブラリのみ（urllib, json, csv, gzip, xml.etree, re）。テストは pytest、ネットワークは注入可能な fetch 関数とフィクスチャで代替。

**Spec:** `docs/superpowers/specs/2026-09-05-update-pipeline-design.md`

## Global Constraints

- 全 .py は Python 3.8 互換構文（`typing.List/Dict/Optional/Tuple`、`X | Y`・`list[str]`・match 文は禁止）。PostToolUse フックが vermin で検査する。
- 標準ライブラリのみ。I/O は `encoding="utf-8"`、書き込みは `newline="\n"`。
- 取り込み源は Wikidata と NDL のみ。JMnedict は索引の真偽フラグにだけ使い、その漢字・読みをデータや findings の値に使わない。
- 全 HTTP リクエストは `User-Agent: japanese-personal-name-dataset/qa-update (https://github.com/shuheilocale/japanese-personal-name-dataset)` を付け、リクエスト間に 1 秒スリープ、失敗は 3 回リトライ（指数バックオフ）。
- dataset CSV は読み取りのみ。書き込みは `/qa-apply`（apply_findings.py）経由でユーザー承認後にのみ行う。
- `qa/sources/` は `.gitignore`（`manifest.json` のみ追跡）。`qa/kanji/jinmei.txt` は追跡する。
- テスト実行: `uv run pytest tests/ -q`。tests/conftest.py に `.claude/skills/qa-update/scripts` を追加する（Task 1）。
- findings の `add_row` は `entry` = 追加する完全行、`add_kanji` は `entry` = 既存行・`value` = 追加漢字（複数はカンマ区切り）。`detected_by` は `"qa-update v1"`。
- コミットメッセージは英語命令形 + `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`。

---

### Task 1: 共通ユーティリティ `sources_common.py` と conftest

**Files:**
- Create: `.claude/skills/qa-update/scripts/sources_common.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_qa_update_common.py`

**Interfaces:**
- Produces:
  - `sources_common.USER_AGENT: str`
  - `sources_common.kata_to_hira(s: str) -> str` — カタカナ→ひらがな（`ー` と非カナは維持、`ヴ`→`ゔ`）
  - `sources_common.is_japanese_name_part(s: str) -> bool` — 漢字・ひらがな・`々ヶヵ` のみで 1〜5 文字なら True（カタカナ・中黒・欧字・数字を含めば False）
  - `sources_common.record(source, kind, kanji, reading, gender=None, count=1) -> dict` — 正規化レコード。`reading` はひらがなのみ（`checks.HIRAGANA_RE`）、`kind` は `given|surname`、`gender` は `male|female|unisex|None`。違反は `ValueError`
  - `sources_common.write_jsonl(path, records) / read_jsonl(path) -> List[dict]`
  - `sources_common.http_get(url, params=None, headers=None, retries=3, timeout=120, sleep=1.0, opener=None) -> bytes` — `opener` は `urllib.request.urlopen` 互換の呼び出し可能（テストで差し替え）。失敗時は 1,2,4 秒待って再試行、最終的に `RuntimeError`

- [ ] **Step 1: conftest にパスを追加**

`tests/conftest.py` の `_rel` タプルに `os.path.join(".claude", "skills", "qa-update", "scripts"),` を追加する。

- [ ] **Step 2: 失敗するテストを書く**

```python
# tests/test_qa_update_common.py
"""sources_common.py（qa-update 共通ユーティリティ）のテスト。"""
import io
import os

import pytest

import sources_common as sc


class TestKana:
    def test_kata_to_hira(self):
        assert sc.kata_to_hira("ナツメ") == "なつめ"
        assert sc.kata_to_hira("ソウセキ") == "そうせき"
        assert sc.kata_to_hira("ヴィ") == "ゔぃ"
        assert sc.kata_to_hira("タロー") == "たろー"
        assert sc.kata_to_hira("漱石") == "漱石"


class TestNamePart:
    def test_accepts_japanese(self):
        for s in ["漱石", "たろう", "佐々木", "一ノ瀬", "凛"]:
            assert sc.is_japanese_name_part(s), s

    def test_rejects_foreign_or_garbage(self):
        for s in ["", "ジョン", "山田・太郎", "John", "太郎2", "六文字以上の名前です"]:
            assert not sc.is_japanese_name_part(s), s


class TestRecord:
    def test_valid(self):
        r = sc.record("ndl", "given", "漱石", "そうせき", count=3)
        assert r == {"source": "ndl", "kind": "given", "kanji": "漱石", "reading": "そうせき",
                     "gender": None, "count": 3}

    def test_kana_only_kanji_allowed_for_reading_evidence(self):
        r = sc.record("wikidata", "given", "", "まさとし", gender="male")
        assert r["kanji"] == "" and r["gender"] == "male"

    def test_invalid(self):
        with pytest.raises(ValueError):
            sc.record("ndl", "given", "漱石", "ソウセキ")  # 読みがひらがなでない
        with pytest.raises(ValueError):
            sc.record("ndl", "place", "漱石", "そうせき")
        with pytest.raises(ValueError):
            sc.record("ndl", "given", "漱石", "そうせき", gender="boy")


class TestJsonl:
    def test_roundtrip(self, tmp_path):
        p = str(tmp_path / "x.jsonl")
        recs = [sc.record("ndl", "given", "漱石", "そうせき"), sc.record("ndl", "surname", "夏目", "なつめ")]
        sc.write_jsonl(p, recs)
        assert sc.read_jsonl(p) == recs
        assert b"\r\n" not in open(p, "rb").read()


class TestHttpGet:
    def test_retries_then_succeeds(self):
        calls = []

        class Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def opener(req, timeout=0):
            calls.append(req.get_header("User-agent"))
            if len(calls) < 3:
                raise OSError("boom")
            return Resp(b"ok")

        data = sc.http_get("http://example.invalid/x", params={"q": "1"}, opener=opener, sleep=0)
        assert data == b"ok" and len(calls) == 3
        assert calls[0] == sc.USER_AGENT

    def test_gives_up(self):
        def opener(req, timeout=0):
            raise OSError("boom")
        with pytest.raises(RuntimeError):
            sc.http_get("http://example.invalid/x", opener=opener, sleep=0, retries=2)
```

- [ ] **Step 3: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_update_common.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'sources_common'`）

- [ ] **Step 4: 実装**

```python
# .claude/skills/qa-update/scripts/sources_common.py
"""qa-update スクリプト群の共通ユーティリティ。

正規化レコード（全ソース共通）:
    {"source": "ndl", "kind": "given", "kanji": "漱石", "reading": "そうせき",
     "gender": None, "count": 12}
kanji が空文字のレコードは「読みだけの根拠」（Wikidata の仮名ラベル項目）を表す。
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "validate-dataset", "scripts")))

import checks  # noqa: E402

USER_AGENT = ("japanese-personal-name-dataset/qa-update "
              "(https://github.com/shuheilocale/japanese-personal-name-dataset)")
KINDS = ("given", "surname")
GENDERS = ("male", "female", "unisex")
_NAME_PART_RE = re.compile(r"^[぀-ゟ一-鿿㐀-䶿豈-﫿々ヶヵ]{1,5}$")


def kata_to_hira(s):
    # type: (str) -> str
    out = []
    for ch in s:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:  # ァ..ヶ → ぁ..ゖ
            out.append(chr(code - 0x60))
        else:
            out.append(ch)
    return "".join(out)


def is_japanese_name_part(s):
    # type: (str) -> bool
    return bool(_NAME_PART_RE.match(s or ""))


def record(source, kind, kanji, reading, gender=None, count=1):
    # type: (str, str, str, str, Optional[str], int) -> dict
    if kind not in KINDS:
        raise ValueError("kind は given|surname: %r" % kind)
    if gender is not None and gender not in GENDERS:
        raise ValueError("gender は male|female|unisex|None: %r" % gender)
    if not checks.HIRAGANA_RE.match(reading or ""):
        raise ValueError("reading はひらがなのみ: %r" % reading)
    return {"source": source, "kind": kind, "kanji": kanji or "", "reading": reading,
            "gender": gender, "count": int(count)}


def write_jsonl(path, records):
    # type: (str, List[dict]) -> None
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    # type: (str) -> List[dict]
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def http_get(url, params=None, headers=None, retries=3, timeout=120, sleep=1.0, opener=None):
    # type: (str, Optional[dict], Optional[dict], int, int, float, object) -> bytes
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=dict(headers or {}))
    req.add_header("User-Agent", USER_AGENT)
    open_fn = opener or urllib.request.urlopen
    last = None
    for attempt in range(retries):
        try:
            with open_fn(req, timeout=timeout) as resp:
                data = resp.read()
            if sleep:
                time.sleep(sleep)
            return data
        except Exception as e:  # noqa: BLE001 - リトライ対象は全て
            last = e
            if attempt < retries - 1 and sleep:
                time.sleep(sleep * (2 ** attempt))
    raise RuntimeError("取得に失敗しました（%d 回試行）: %s: %s" % (retries, url[:80], last))
```

- [ ] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_update_common.py -v`
Expected: PASS（全件）

- [ ] **Step 6: コミット**

```bash
git add tests/conftest.py tests/test_qa_update_common.py .claude/skills/qa-update/scripts/sources_common.py
git commit -m "Add qa-update common utilities (kana, records, jsonl, http)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: 常用漢字・人名用漢字リストの生成 `build_kanji_list.py` と `qa/kanji/jinmei.txt`

**Files:**
- Create: `.claude/skills/qa-update/scripts/build_kanji_list.py`
- Create: `qa/kanji/jinmei.txt`（生成物。追跡する）
- Test: `tests/test_qa_update_kanji.py`

**Interfaces:**
- Consumes: `sources_common.http_get`
- Produces:
  - `build_kanji_list.extract_kanji(wikitext: str, first_per_row: bool = False) -> List[str]` — 表の `[[wikt:X|X]]` 形式の 1 文字リンクを出現順・重複なしで返す。`first_per_row=True` なら各表行（`|-` 区切り）の最初のリンクだけを取る（常用漢字表の「通用字体」列用。旧字体列を拾わない）
  - `build_kanji_list.load_allowed(path) -> set` — 1 行 1 文字のファイルを集合で返す
  - `build_kanji_list.kanji_allowed(text: str, allowed: set) -> bool` — `text` の漢字（CJK 統合漢字）が全て `allowed` に含まれるか。ひらがな・カタカナ・`々ヶヵ` は常に許可
  - CLI: `python3 build_kanji_list.py --out qa/kanji/jinmei.txt` — Wikipedia API から `常用漢字一覧`（期待 2136 字）と `人名用漢字一覧`（期待 864 字。2026-06-26 の戸籍法施行規則改正で 863 字から 864 字に変更）を取得し、件数が期待と一致しなければ exit 1

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_update_kanji.py
"""build_kanji_list.py（常用漢字・人名用漢字の抽出）のテスト。"""
import build_kanji_list as bk

WIKITEXT = """
{| class="sortable wikitable"
|-
! # || 通用字体 || 旧字体
|-
| {{0|000}}1 || style="font-size:180%" | [[wikt:亜|亜]] || style="font-size:180%" | [[wikt:亞|亞]] || 7
|-
| {{0|000}}2 || style="font-size:180%" | [[wikt:哀|哀]] || || 9
|-
| {{0|000}}3 || '''[[wikt:丑|丑]]''' || 表外人名
|}
"""


class TestExtract:
    def test_extract_in_order_unique(self):
        assert bk.extract_kanji(WIKITEXT) == ["亜", "亞", "哀", "丑"]

    def test_first_per_row_skips_old_forms(self):
        assert bk.extract_kanji(WIKITEXT, first_per_row=True) == ["亜", "哀", "丑"]

    def test_ignores_non_kanji_links(self):
        assert bk.extract_kanji("[[wikt:ab|ab]] [[wikt:一|一]]") == ["一"]


class TestAllowed:
    def test_kanji_allowed(self, tmp_path):
        p = tmp_path / "jinmei.txt"
        p.write_text("亜\n哀\n", encoding="utf-8")
        allowed = bk.load_allowed(str(p))
        assert bk.kanji_allowed("亜哀", allowed)
        assert bk.kanji_allowed("あい亜々", allowed)
        assert not bk.kanji_allowed("亜龍", allowed)
        assert bk.kanji_allowed("ゆき", allowed)
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_update_kanji.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 実装**

```python
# .claude/skills/qa-update/scripts/build_kanji_list.py
"""常用漢字（2136 字）と人名用漢字（863 字）の文字集合を生成する。

Wikipedia の「常用漢字一覧」「人名用漢字一覧」の表から [[wikt:X|X]] 形式の
1 文字リンクを抽出する。文字の集合自体は官報告示・法令別表に基づく公知の
事実であり、生成物 qa/kanji/jinmei.txt はリポジトリに同梱する。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources_common as sc  # noqa: E402

API = "https://ja.wikipedia.org/w/api.php"
# (ページ名, 期待字数, 各行の先頭リンクだけを取るか)。常用漢字表は「通用字体」列の次に旧字体列があるため先頭のみ
PAGES = [("常用漢字一覧", 2136, True), ("人名用漢字一覧", 863, False)]
_LINK_RE = re.compile(r"\[\[wikt:([一-鿿㐀-䶿豈-﫿])\|\1\]\]")
_CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")


def extract_kanji(wikitext, first_per_row=False):
    # type: (str, bool) -> list
    seen = []
    if first_per_row:
        found = []
        for row in wikitext.split("\n|-"):
            links = _LINK_RE.findall(row)
            if links:
                found.append(links[0])
    else:
        found = _LINK_RE.findall(wikitext)
    for ch in found:
        if ch not in seen:
            seen.append(ch)
    return seen


def load_allowed(path):
    # type: (str) -> set
    with open(path, encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def kanji_allowed(text, allowed):
    # type: (str, set) -> bool
    return all(ch in allowed for ch in _CJK_RE.findall(text))


def fetch_page_wikitext(title, fetch=None):
    # type: (str, object) -> str
    data = (fetch or sc.http_get)(API, params={
        "action": "parse", "page": title, "prop": "wikitext", "format": "json"})
    return json.loads(data.decode("utf-8"))["parse"]["wikitext"]["*"]


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join("qa", "kanji", "jinmei.txt"))
    args = parser.parse_args()
    chars = []
    for title, expected, first_per_row in PAGES:
        found = extract_kanji(fetch_page_wikitext(title), first_per_row=first_per_row)
        print("%s: %d 字（期待 %d）" % (title, len(found), expected))
        if len(found) != expected:
            print("エラー: 期待件数と一致しません。ページ構造の変化を確認してください。")
            return 1
        chars.extend(found)
    uniq = sorted(set(chars))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(uniq) + "\n")
    print("書き込み: %s（%d 字）" % (args.out, len(uniq)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: テストが通ることを確認し、実際にリストを生成**

Run: `uv run pytest tests/test_qa_update_kanji.py -v && python3 .claude/skills/qa-update/scripts/build_kanji_list.py`
Expected: PASS。生成は「常用漢字一覧: 2136 字（期待 2136）」「人名用漢字一覧: 864 字（期待 864。2026-06-26 の戸籍法施行規則改正で 863 字から 864 字に変更）」と表示され `qa/kanji/jinmei.txt` が書かれる（常用と人名用の重複は集合化で解消されるため合計は 3000 未満でよい）。件数が一致しない場合は `_LINK_RE` か表の構造を調べて修正し、一致するまで進めない。

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_update_kanji.py .claude/skills/qa-update/scripts/build_kanji_list.py qa/kanji/jinmei.txt
git commit -m "Add joyo/jinmeiyo kanji list generator and bundled character set

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Wikidata 取得 `fetch_wikidata.py`

**Files:**
- Create: `.claude/skills/qa-update/scripts/fetch_wikidata.py`
- Modify: `.gitignore`（`qa/sources/*` を無視し `qa/sources/manifest.json` は追跡）
- Test: `tests/test_qa_update_wikidata.py`

**Interfaces:**
- Consumes: `sources_common.http_get / record / write_jsonl / kata_to_hira`
- Produces:
  - `fetch_wikidata.CLASSES = {"given": {"male": "Q12308941", "female": "Q11879590", "unisex": "Q3409032"}, "surname": {None: "Q101352"}}`
  - `fetch_wikidata.build_query(kind: str, qid: str) -> str`
  - `fetch_wikidata.rows_to_records(kind, gender, rows: List[dict]) -> List[dict]` — rows は `{"label": "博", "kana": "ひろし", "people": "423"}`。仮名ラベル（label が全てかな）は `kanji=""` の読み根拠レコードにする。count は `max(1, people)`
  - CLI: `python3 fetch_wikidata.py --out qa/sources/wikidata-<date>.jsonl`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_update_wikidata.py
"""fetch_wikidata.py のテスト（ネットワークはフィクスチャで代替）。"""
import json

import fetch_wikidata as fw


class TestQuery:
    def test_query_mentions_class_and_kana(self):
        q = fw.build_query("given", "Q12308941")
        assert "wd:Q12308941" in q and "wdt:P1814" in q and "wdt:P735" in q
        q2 = fw.build_query("surname", "Q101352")
        assert "wdt:P734" in q2


class TestRows:
    def test_kanji_and_kana_rows(self):
        rows = [{"label": "博", "kana": "ひろし", "people": "423"},
                {"label": "まさとし", "kana": "まさとし", "people": "190"},
                {"label": "宏", "kana": "ヒロシ", "people": "0"}]
        recs = fw.rows_to_records("given", "male", rows)
        assert recs[0] == {"source": "wikidata", "kind": "given", "kanji": "博", "reading": "ひろし",
                           "gender": "male", "count": 423}
        assert recs[1]["kanji"] == "" and recs[1]["reading"] == "まさとし"
        assert recs[2]["reading"] == "ひろし" and recs[2]["count"] == 1

    def test_skips_invalid(self):
        rows = [{"label": "John", "kana": "ジョン", "people": "1"},
                {"label": "博", "kana": "hiroshi", "people": "1"}]
        assert fw.rows_to_records("given", "male", rows) == []

    def test_parse_sparql_json(self):
        body = json.dumps({"results": {"bindings": [
            {"label": {"value": "博"}, "kana": {"value": "ひろし"}, "people": {"value": "3"}}]}})
        assert fw.parse_bindings(body.encode("utf-8")) == [{"label": "博", "kana": "ひろし", "people": "3"}]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_update_wikidata.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# .claude/skills/qa-update/scripts/fetch_wikidata.py
"""Wikidata から日本語の名・姓（仮名表記 P1814 付き）を取得して正規化 JSONL に書く。

クラス: 男性名 Q12308941 / 女性名 Q11879590 / 中性名 Q3409032 / 姓 Q101352。
count はその名を持つ人物数（P735 / P734 の参照数、項目が存在すれば最低 1）。
"""
import argparse
import datetime
import json
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checks  # noqa: E402  (sources_common が validate-dataset/scripts をパスに追加する)
import sources_common as sc  # noqa: E402

ENDPOINT = "https://query.wikidata.org/sparql"
CLASSES = {
    "given": {"male": "Q12308941", "female": "Q11879590", "unisex": "Q3409032"},
    "surname": {None: "Q101352"},
}


def build_query(kind, qid):
    # type: (str, str) -> str
    prop = "wdt:P735" if kind == "given" else "wdt:P734"
    return (
        "SELECT ?label ?kana (COUNT(?h) AS ?people) WHERE { "
        "?item wdt:P31 wd:%s ; wdt:P407 wd:Q5287 ; wdt:P1814 ?kana ; rdfs:label ?label . "
        "FILTER(LANG(?label)=\"ja\") OPTIONAL { ?h %s ?item } } "
        "GROUP BY ?label ?kana" % (qid, prop))


def parse_bindings(data):
    # type: (bytes) -> List[dict]
    body = json.loads(data.decode("utf-8"))
    return [{k: v["value"] for k, v in b.items()} for b in body["results"]["bindings"]]


def rows_to_records(kind, gender, rows):
    # type: (str, str, List[dict]) -> List[dict]
    out = []
    for r in rows:
        reading = sc.kata_to_hira(r.get("kana", ""))
        if not checks.HIRAGANA_RE.match(reading):
            continue
        label = r.get("label", "")
        if checks.HIRAGANA_RE.match(sc.kata_to_hira(label)):
            kanji = ""  # 仮名ラベル項目は読みだけの根拠
        elif sc.is_japanese_name_part(label):
            kanji = label
        else:
            continue
        try:
            people = int(r.get("people", "0") or 0)
        except ValueError:
            people = 0
        out.append(sc.record("wikidata", kind, kanji, reading, gender=gender, count=max(1, people)))
    return out


def fetch_all(fetch=None):
    # type: (object) -> List[dict]
    records = []
    for kind, classes in CLASSES.items():
        for gender, qid in classes.items():
            data = (fetch or sc.http_get)(
                ENDPOINT, params={"query": build_query(kind, qid)},
                headers={"Accept": "application/sparql-results+json"})
            rows = parse_bindings(data)
            recs = rows_to_records(kind, gender, rows)
            print("%s/%s: %d 行 → %d レコード" % (kind, gender, len(rows), len(recs)))
            records.extend(recs)
    return records


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(
        "qa", "sources", "wikidata-%s.jsonl" % datetime.date.today().isoformat()))
    args = parser.parse_args()
    records = fetch_all()
    sc.write_jsonl(args.out, records)
    print("書き込み: %s（%d 件）" % (args.out, len(records)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`.gitignore` に追記:

```text
# qa-update の取得スナップショット（manifest.json だけ追跡）
qa/sources/*
!qa/sources/manifest.json
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_update_wikidata.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_update_wikidata.py .claude/skills/qa-update/scripts/fetch_wikidata.py .gitignore
git commit -m "Add Wikidata fetcher for Japanese given names and surnames

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: NDL 典拠取得 `fetch_ndl.py`（ID 接頭辞チャンク・再開可能）

**Files:**
- Create: `.claude/skills/qa-update/scripts/fetch_ndl.py`
- Test: `tests/test_qa_update_ndl.py`

**Interfaces:**
- Consumes: `sources_common`
- Produces:
  - `fetch_ndl.build_query(prefix: str) -> str` — `FILTER(STRSTARTS(STR(?s), "http://id.ndl.go.jp/auth/ndlna/<prefix>"))` を含む SELECT
  - `fetch_ndl.parse_label(label: str) -> Optional[Tuple[str, str]]` — `"夏目, 漱石, 1867-1916"` → `("夏目", "漱石")`。名が無い・各部が日本人名の文字でない場合は None
  - `fetch_ndl.parse_yomi(yomi: str) -> Optional[Tuple[str, str]]` — `"ナツメ, ソウセキ, 1867-1916"` → `("なつめ", "そうせき")`
  - `fetch_ndl.bindings_to_records(bindings: List[dict]) -> List[dict]` — `xml:lang` が大文字小文字を無視して `ja-kana` の行だけを使い、given と surname のレコード（count=1）を返す
  - `fetch_ndl.aggregate(records) -> List[dict]` — `(source, kind, kanji, reading)` で count を合計
  - `fetch_ndl.fetch_prefixes(prefixes, work, fetch=None, cap=1000, max_depth=9)` — cap 以上の接頭辞は 1 桁深く再分割（manifest の split）。leaf は done。max_depth でも cap 以上は saturated。完了接頭辞は再実行でスキップ
  - CLI: `python3 fetch_ndl.py --out qa/sources/ndl-<date>.jsonl [--prefix-len 3] [--work qa/sources/ndl-work] [--cap 1000] [--max-depth 9]` — 適応分割で接頭辞を取得。saturated 接頭辞があれば exit 1

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_update_ndl.py
"""fetch_ndl.py のテスト（ネットワークはフィクスチャで代替）。"""
import json
import os

import fetch_ndl as fn


def _b(s, label, yomi, lang):
    return {"s": {"value": s}, "label": {"value": label},
            "yomi": {"value": yomi, "xml:lang": lang}}


class TestParse:
    def test_label(self):
        assert fn.parse_label("夏目, 漱石, 1867-1916") == ("夏目", "漱石")
        assert fn.parse_label("内藤, 英憲") == ("内藤", "英憲")
        assert fn.parse_label("夏目漱石") is None
        assert fn.parse_label("スミス, ジョン") is None
        assert fn.parse_label("山田, 太郎 (1950-)") is None

    def test_yomi(self):
        assert fn.parse_yomi("ナツメ, ソウセキ, 1867-1916") == ("なつめ", "そうせき")
        assert fn.parse_yomi("Natsume, Soseki") is None


class TestRecords:
    def test_only_kana_lang_and_both_kinds(self):
        bindings = [
            _b("http://id.ndl.go.jp/auth/ndlna/1", "夏目, 漱石, 1867-1916", "Natsume, Soseki", "ja-latn"),
            _b("http://id.ndl.go.jp/auth/ndlna/1", "夏目, 漱石, 1867-1916", "ナツメ, ソウセキ, 1867-1916", "ja-Kana"),
            _b("http://id.ndl.go.jp/auth/ndlna/2", "スミス, ジョン", "スミス, ジョン", "ja-Kana"),
        ]
        recs = fn.bindings_to_records(bindings)
        assert {"source": "ndl", "kind": "given", "kanji": "漱石", "reading": "そうせき",
                "gender": None, "count": 1} in recs
        assert {"source": "ndl", "kind": "surname", "kanji": "夏目", "reading": "なつめ",
                "gender": None, "count": 1} in recs
        assert len(recs) == 2

    def test_aggregate(self):
        recs = fn.bindings_to_records([
            _b("a", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana"),
            _b("b", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana"),
            _b("c", "山田, 花子", "ヤマダ, ハナコ", "ja-Kana"),
        ])
        agg = {(r["kind"], r["kanji"], r["reading"]): r["count"] for r in fn.aggregate(recs)}
        assert agg[("surname", "山田", "やまだ")] == 3
        assert agg[("given", "太郎", "たろう")] == 2


class TestResume:
    def test_fetch_prefixes_resumes(self, tmp_path):
        work = str(tmp_path / "work")
        calls = []

        def fetch(url, params=None, headers=None):
            calls.append(params["query"])
            body = {"results": {"bindings": [
                _b("x", "山田, 太郎", "ヤマダ, タロウ", "ja-Kana")]}}
            return json.dumps(body).encode("utf-8")

        fn.fetch_prefixes(["00", "01"], work, fetch=fetch)
        assert len(calls) == 2
        fn.fetch_prefixes(["00", "01", "02"], work, fetch=fetch)
        assert len(calls) == 3  # 完了済み接頭辞はスキップ
        manifest = json.load(open(os.path.join(work, "manifest.json"), encoding="utf-8"))
        assert manifest["done"] == ["00", "01", "02"]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_update_ndl.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# .claude/skills/qa-update/scripts/fetch_ndl.py
"""国立国会図書館典拠データ（Web NDL Authorities）から人名を取得して正規化 JSONL に書く。

SPARQL の ORDER BY + OFFSET は大きなオフセットでサーバエラーになるため、
典拠 ID（http://id.ndl.go.jp/auth/ndlna/NNNNNNNN）の接頭辞でチャンク分割する。
接頭辞ごとの結果を作業ディレクトリに保存し、manifest.json で再開できる。
"""
import argparse
import datetime
import json
import os
import re
import sys
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources_common as sc  # noqa: E402

ENDPOINT = "https://id.ndl.go.jp/auth/ndla/sparql"
_DATE_RE = re.compile(r"^[0-9]{3,4}-?([0-9]{3,4})?$")


def build_query(prefix):
    # type: (str) -> str
    return (
        "PREFIX xl: <http://www.w3.org/2008/05/skos-xl#> "
        "PREFIX skos: <http://www.w3.org/2004/02/skos/core#> "
        "PREFIX ndl: <http://ndl.go.jp/dcndl/terms/> "
        "SELECT ?s ?label ?yomi WHERE { "
        "?s skos:inScheme <http://id.ndl.go.jp/auth#personalNames> ; xl:prefLabel ?pl . "
        "?pl xl:literalForm ?label ; ndl:transcription ?yomi . "
        "FILTER(STRSTARTS(STR(?s), \"http://id.ndl.go.jp/auth/ndlna/%s\")) }" % prefix)


def _split(label):
    # type: (str) -> List[str]
    return [p.strip() for p in label.split(",")]


def parse_label(label):
    # type: (str) -> Optional[Tuple[str, str]]
    parts = _split(label)
    if len(parts) < 2:
        return None
    surname, given = parts[0], parts[1]
    if not (sc.is_japanese_name_part(surname) and sc.is_japanese_name_part(given)):
        return None
    return surname, given


def parse_yomi(yomi):
    # type: (str) -> Optional[Tuple[str, str]]
    parts = _split(yomi)
    if len(parts) < 2:
        return None
    s, g = sc.kata_to_hira(parts[0]), sc.kata_to_hira(parts[1])
    if not (sc.checks.HIRAGANA_RE.match(s) and sc.checks.HIRAGANA_RE.match(g)):
        return None
    return s, g


def bindings_to_records(bindings):
    # type: (List[dict]) -> List[dict]
    out = []
    for b in bindings:
        if b.get("yomi", {}).get("xml:lang") != "ja-Kana":
            continue
        names = parse_label(b["label"]["value"])
        yomis = parse_yomi(b["yomi"]["value"])
        if not names or not yomis:
            continue
        out.append(sc.record("ndl", "surname", names[0], yomis[0]))
        out.append(sc.record("ndl", "given", names[1], yomis[1]))
    return out


def aggregate(records):
    # type: (List[dict]) -> List[dict]
    totals = {}
    for r in records:
        k = (r["source"], r["kind"], r["kanji"], r["reading"])
        totals[k] = totals.get(k, 0) + r["count"]
    return [sc.record(s, kind, kanji, reading, count=n)
            for (s, kind, kanji, reading), n in sorted(totals.items())]


def fetch_prefixes(prefixes, work, fetch=None):
    # type: (List[str], str, object) -> None
    os.makedirs(work, exist_ok=True)
    mpath = os.path.join(work, "manifest.json")
    manifest = {"done": []}
    if os.path.exists(mpath):
        with open(mpath, encoding="utf-8") as f:
            manifest = json.load(f)
    for prefix in prefixes:
        if prefix in manifest["done"]:
            continue
        data = (fetch or sc.http_get)(ENDPOINT, params={"query": build_query(prefix)},
                                      headers={"Accept": "application/sparql-results+json"})
        bindings = json.loads(data.decode("utf-8"))["results"]["bindings"]
        sc.write_jsonl(os.path.join(work, "prefix-%s.jsonl" % prefix), bindings_to_records(bindings))
        manifest["done"].append(prefix)
        with open(mpath, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        print("prefix %s: %d 行" % (prefix, len(bindings)))


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(
        "qa", "sources", "ndl-%s.jsonl" % datetime.date.today().isoformat()))
    parser.add_argument("--work", default=os.path.join("qa", "sources", "ndl-work"))
    parser.add_argument("--prefix-len", type=int, default=3)
    args = parser.parse_args()
    prefixes = ["%0*d" % (args.prefix_len, i) for i in range(10 ** args.prefix_len)]
    fetch_prefixes(prefixes, args.work)
    records = []
    for prefix in prefixes:
        records.extend(sc.read_jsonl(os.path.join(args.work, "prefix-%s.jsonl" % prefix)))
    agg = aggregate(records)
    sc.write_jsonl(args.out, agg)
    print("書き込み: %s（%d 件）" % (args.out, len(agg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`sources_common` 経由で `checks` を参照するため、`sources_common.py` に `checks` がモジュール属性として存在することを確認する（`import checks` 済みなので `sc.checks` で参照可能）。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_update_ndl.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_update_ndl.py .claude/skills/qa-update/scripts/fetch_ndl.py
git commit -m "Add NDL authorities fetcher with prefix chunking and resume

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: JMnedict 取得 `fetch_jmnedict.py`（照合専用）

**Files:**
- Create: `.claude/skills/qa-update/scripts/fetch_jmnedict.py`
- Test: `tests/test_qa_update_jmnedict.py`

**Interfaces:**
- Consumes: `sources_common`
- Produces:
  - `fetch_jmnedict.iter_entries(fileobj) -> Iterator[dict]` — `{"kanji": [...], "readings": [...], "types": [...]}`（`xml.etree.ElementTree.iterparse`）
  - `fetch_jmnedict.entries_to_records(entries) -> List[dict]` — `name_type` テキストに `"male given"` → given/male、`"female given"` → given/female、`"given name"`（性別なし）→ given/None、`"family or surname"` → surname。他の種別は無視。count=1
  - CLI: `python3 fetch_jmnedict.py --out qa/sources/jmnedict-<date>.jsonl [--cache qa/sources/JMnedict.xml.gz]`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_update_jmnedict.py
"""fetch_jmnedict.py のテスト（小さな XML フィクスチャ）。"""
import io

import fetch_jmnedict as fj

XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE JMnedict [
<!ENTITY masc "male given name or forename">
<!ENTITY fem "female given name or forename">
<!ENTITY given "given name or forename, gender not specified">
<!ENTITY surname "family or surname">
<!ENTITY place "place name">
]>
<JMnedict>
<entry><ent_seq>1</ent_seq><k_ele><keb>漱石</keb></k_ele><r_ele><reb>そうせき</reb></r_ele>
<trans><name_type>&masc;</name_type></trans></entry>
<entry><ent_seq>2</ent_seq><k_ele><keb>夏目</keb></k_ele><r_ele><reb>なつめ</reb></r_ele>
<trans><name_type>&surname;</name_type></trans></entry>
<entry><ent_seq>3</ent_seq><k_ele><keb>東京</keb></k_ele><r_ele><reb>とうきょう</reb></r_ele>
<trans><name_type>&place;</name_type></trans></entry>
<entry><ent_seq>4</ent_seq><k_ele><keb>薫</keb></k_ele><r_ele><reb>かおる</reb></r_ele>
<trans><name_type>&masc;</name_type><name_type>&fem;</name_type></trans></entry>
</JMnedict>
"""


def test_entries_and_records():
    entries = list(fj.iter_entries(io.BytesIO(XML.encode("utf-8"))))
    assert len(entries) == 4
    recs = fj.entries_to_records(entries)
    assert {"source": "jmnedict", "kind": "given", "kanji": "漱石", "reading": "そうせき",
            "gender": "male", "count": 1} in recs
    assert {"source": "jmnedict", "kind": "surname", "kanji": "夏目", "reading": "なつめ",
            "gender": None, "count": 1} in recs
    kaoru = [r for r in recs if r["kanji"] == "薫"]
    assert kaoru and kaoru[0]["gender"] == "unisex"
    assert not [r for r in recs if r["kanji"] == "東京"]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_update_jmnedict.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# .claude/skills/qa-update/scripts/fetch_jmnedict.py
"""JMnedict（EDRDG、CC BY-SA 3.0）を取得して正規化 JSONL に書く。

ライセンスの share-alike 条項のため、このソースは索引での「存在確認」にだけ
使い、漢字・読みをデータセットや findings の値に転記してはならない。
"""
import argparse
import datetime
import gzip
import os
import sys
import xml.etree.ElementTree as ET
from typing import Iterator, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources_common as sc  # noqa: E402

URL = "http://ftp.edrdg.org/pub/Nihongo/JMnedict.xml.gz"


def iter_entries(fileobj):
    # type: (object) -> Iterator[dict]
    for _event, elem in ET.iterparse(fileobj, events=("end",)):
        if elem.tag != "entry":
            continue
        yield {
            "kanji": [k.text for k in elem.iter("keb") if k.text],
            "readings": [r.text for r in elem.iter("reb") if r.text],
            "types": [t.text or "" for t in elem.iter("name_type")],
        }
        elem.clear()


def _classify(types):
    # type: (List[str]) -> List[tuple]
    kinds = []
    joined = " | ".join(types)
    male = "male given" in joined
    female = "female given" in joined
    if male and female:
        kinds.append(("given", "unisex"))
    elif male:
        kinds.append(("given", "male"))
    elif female:
        kinds.append(("given", "female"))
    elif "given name" in joined:
        kinds.append(("given", None))
    if "surname" in joined:
        kinds.append(("surname", None))
    return kinds


def entries_to_records(entries):
    # type: (Iterator[dict]) -> List[dict]
    out = []
    for e in entries:
        kinds = _classify(e["types"])
        if not kinds or not e["kanji"]:
            continue
        for kanji in e["kanji"]:
            for reb in e["readings"]:
                reading = sc.kata_to_hira(reb)
                if not sc.checks.HIRAGANA_RE.match(reading) or not sc.is_japanese_name_part(kanji):
                    continue
                for kind, gender in kinds:
                    out.append(sc.record("jmnedict", kind, kanji, reading, gender=gender))
    return out


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=os.path.join(
        "qa", "sources", "jmnedict-%s.jsonl" % datetime.date.today().isoformat()))
    parser.add_argument("--cache", default=os.path.join("qa", "sources", "JMnedict.xml.gz"))
    args = parser.parse_args()
    if not os.path.exists(args.cache):
        os.makedirs(os.path.dirname(args.cache), exist_ok=True)
        with open(args.cache, "wb") as f:
            f.write(sc.http_get(URL, timeout=600))
        print("ダウンロード: %s" % args.cache)
    with gzip.open(args.cache, "rb") as f:
        records = entries_to_records(iter_entries(f))
    sc.write_jsonl(args.out, records)
    print("書き込み: %s（%d 件）" % (args.out, len(records)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_update_jmnedict.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_update_jmnedict.py .claude/skills/qa-update/scripts/fetch_jmnedict.py
git commit -m "Add JMnedict fetcher for cross-reference only

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: 統一索引 `source_index.py`

**Files:**
- Create: `.claude/skills/qa-update/scripts/source_index.py`
- Test: `tests/test_qa_update_index.py`

**Interfaces:**
- Consumes: 正規化レコード（Task 1 の形）
- Produces:
  - `source_index.pair_key(kind, kanji, reading) -> str`（`"given|漱石|そうせき"`）、`source_index.reading_key(kind, reading) -> str`（`"given||そうせき"`）
  - `source_index.build_index(records: Iterable[dict]) -> dict` — `{"pairs": {key: {"ndl": n, "wikidata": n, "jmnedict": bool, "gender": {"wikidata": g, "jmnedict": g}}}, "readings": {key: 同形}}`。kanji が空のレコードは readings にだけ、それ以外は pairs と readings の両方に集計
  - `source_index.support(index, kind, kanji, reading) -> dict` — `{"ndl": 0, "wikidata": 0, "jmnedict": False}` を既定に pairs の値を返す
  - `source_index.gender_of(index, kind, reading) -> Optional[str]` — readings の gender を wikidata 優先、次に jmnedict で返す（同一ソース内で male と female が両方出れば unisex）
  - `source_index.save_index(path, index) / load_index(path)`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_update_index.py
"""source_index.py のテスト。"""
import source_index as si
import sources_common as sc


def _recs():
    return [
        sc.record("ndl", "given", "漱石", "そうせき", count=12),
        sc.record("wikidata", "given", "漱石", "そうせき", gender="male", count=3),
        sc.record("wikidata", "given", "", "そうせき", gender="male", count=5),
        sc.record("jmnedict", "given", "漱石", "そうせき", gender="male"),
        sc.record("ndl", "surname", "夏目", "なつめ", count=40),
        sc.record("jmnedict", "given", "薫", "かおる", gender="unisex"),
        sc.record("wikidata", "given", "", "かおる", gender="male", count=1),
        sc.record("wikidata", "given", "", "かおる", gender="female", count=1),
    ]


class TestBuild:
    def test_pairs_and_readings(self):
        idx = si.build_index(_recs())
        p = idx["pairs"][si.pair_key("given", "漱石", "そうせき")]
        assert p["ndl"] == 12 and p["wikidata"] == 3 and p["jmnedict"] is True
        assert p["gender"]["wikidata"] == "male"
        r = idx["readings"][si.reading_key("given", "そうせき")]
        assert r["wikidata"] == 8 and r["ndl"] == 12  # 漢字付き 3 + 仮名のみ 5

    def test_support_default(self):
        idx = si.build_index(_recs())
        assert si.support(idx, "given", "無い", "ない") == {"ndl": 0, "wikidata": 0, "jmnedict": False}
        assert si.support(idx, "surname", "夏目", "なつめ")["ndl"] == 40

    def test_gender_of(self):
        idx = si.build_index(_recs())
        assert si.gender_of(idx, "given", "そうせき") == "male"
        assert si.gender_of(idx, "given", "かおる") == "unisex"  # wikidata で male/female 両方
        assert si.gender_of(idx, "given", "ない") is None

    def test_roundtrip(self, tmp_path):
        idx = si.build_index(_recs())
        p = str(tmp_path / "index.json")
        si.save_index(p, idx)
        assert si.load_index(p) == idx
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_update_index.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# .claude/skills/qa-update/scripts/source_index.py
"""正規化レコードから (kind, kanji, reading) の統一索引を作る。

pairs:    "given|漱石|そうせき" → {"ndl": 12, "wikidata": 3, "jmnedict": true, "gender": {...}}
readings: "given||そうせき"    → 同形（漢字を問わない読みレベルの根拠。仮名のみの Wikidata 項目もここに入る）
"""
import json
import os
from typing import Iterable, Optional

COUNT_SOURCES = ("ndl", "wikidata")


def pair_key(kind, kanji, reading):
    # type: (str, str, str) -> str
    return "%s|%s|%s" % (kind, kanji, reading)


def reading_key(kind, reading):
    # type: (str, str) -> str
    return "%s||%s" % (kind, reading)


def _empty():
    # type: () -> dict
    return {"ndl": 0, "wikidata": 0, "jmnedict": False, "gender": {}}


def _merge_gender(slot, source, gender):
    # type: (dict, str, Optional[str]) -> None
    if not gender:
        return
    cur = slot["gender"].get(source)
    if cur is None or cur == gender:
        slot["gender"][source] = gender
    else:
        slot["gender"][source] = "unisex"


def _add(slot, r):
    # type: (dict, dict) -> None
    if r["source"] in COUNT_SOURCES:
        slot[r["source"]] += r["count"]
    elif r["source"] == "jmnedict":
        slot["jmnedict"] = True
    _merge_gender(slot, r["source"], r.get("gender"))


def build_index(records):
    # type: (Iterable[dict]) -> dict
    index = {"pairs": {}, "readings": {}}
    for r in records:
        rk = reading_key(r["kind"], r["reading"])
        _add(index["readings"].setdefault(rk, _empty()), r)
        if r["kanji"]:
            pk = pair_key(r["kind"], r["kanji"], r["reading"])
            _add(index["pairs"].setdefault(pk, _empty()), r)
    return index


def support(index, kind, kanji, reading):
    # type: (dict, str, str, str) -> dict
    slot = index["pairs"].get(pair_key(kind, kanji, reading))
    if not slot:
        return {"ndl": 0, "wikidata": 0, "jmnedict": False}
    return {"ndl": slot["ndl"], "wikidata": slot["wikidata"], "jmnedict": slot["jmnedict"]}


def gender_of(index, kind, reading):
    # type: (dict, str, str) -> Optional[str]
    slot = index["readings"].get(reading_key(kind, reading))
    if not slot:
        return None
    for source in ("wikidata", "jmnedict"):
        if slot["gender"].get(source):
            return slot["gender"][source]
    return None


def save_index(path, index):
    # type: (str, dict) -> None
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def load_index(path):
    # type: (str) -> dict
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import argparse
    import sys

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import sources_common as sc

    parser = argparse.ArgumentParser(description="正規化 JSONL から統一索引を作る")
    parser.add_argument("--sources", nargs="+", required=True, help="正規化 JSONL ファイル")
    parser.add_argument("--out", default=os.path.join("qa", "sources", "index.json"))
    args = parser.parse_args()
    recs = []
    for p in args.sources:
        recs.extend(sc.read_jsonl(p))
    idx = build_index(recs)
    save_index(args.out, idx)
    print("索引: pairs %d / readings %d → %s" % (len(idx["pairs"]), len(idx["readings"]), args.out))
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_update_index.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_update_index.py .claude/skills/qa-update/scripts/source_index.py
git commit -m "Add unified source index for kanji-reading evidence

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: findings スキーマ拡張と apply / rebase の add 対応

**Files:**
- Modify: `.claude/skills/validate-dataset/scripts/findings_io.py`
- Modify: `.claude/skills/qa-apply/scripts/apply_findings.py`
- Modify: `.claude/skills/qa-apply/scripts/rebase_findings.py`
- Test: `tests/test_qa_findings_io.py`、`tests/test_qa_apply.py`、`tests/test_qa_rebase.py`

**Interfaces:**
- Produces:
  - `findings_io.CHECK_TYPES` に `"missing_entry"`、`findings_io.ACTIONS` に `"add_row"`, `"add_kanji"` を追加。`validate_finding` は `add_row` の `entry` が名 CSV 形式（`ひらがな,ローマ字,漢字...` で 3 列以上、ひらがな/ローマ字の文字種が正しい）であること、`add_kanji` の value が空でないこと、任意フィールド `sources` があれば `{"ndl": int, "wikidata": int, "jmnedict": bool}` であることを検証
  - `apply_findings._apply_one` に `add_kanji`（既存行末尾へ重複除去して追加）と、`apply()` に `add_row`（同じ読みの行が無ければ読み順で挿入、あれば漢字を統合）を実装。add_row の finding は `entry` が「追加する行」なので `lines.index` で探さず、読みで既存行を探す
  - `rebase_findings.rebase` は `add_row` / `add_kanji` の finding を対象外にする（add_kanji の entry は既存行なので本来は対象にできるが、Phase 2 では候補生成側が毎回最新行を書くため不要）

- [ ] **Step 1: 失敗するテストを追加**

```python
# tests/test_qa_findings_io.py に追加
class TestPhase2Schema:
    def _f(self, action, value, entry, file="first_name_man_org.csv", sources=None):
        f = _valid_finding()
        f["file"] = file
        f["check"] = "missing_entry"
        f["proposed_fix"] = {"action": action, "value": value}
        f["entry"] = entry
        if sources is not None:
            f["sources"] = sources
        return f

    def test_add_row_valid(self):
        f = self._f("add_row", "", "あいり,airi,愛莉,愛梨", sources={"ndl": 12, "wikidata": 1, "jmnedict": True})
        assert findings_io.validate_finding(f) == []

    def test_add_row_entry_format(self):
        assert findings_io.validate_finding(self._f("add_row", "", "あいり,airi"))
        assert findings_io.validate_finding(self._f("add_row", "", "アイリ,airi,愛莉"))
        assert findings_io.validate_finding(self._f("add_row", "", "あいり,Airi!,愛莉"))

    def test_add_kanji_needs_value(self):
        assert findings_io.validate_finding(self._f("add_kanji", "", "あい,ai,藍"))
        assert findings_io.validate_finding(self._f("add_kanji", "愛", "あい,ai,藍")) == []

    def test_sources_shape(self):
        assert findings_io.validate_finding(self._f("add_kanji", "愛", "あい,ai,藍", sources={"ndl": "12"}))
```

```python
# tests/test_qa_apply.py に追加
class TestAddActions:
    def _ds(self, tmp_path):
        d = tmp_path / "dataset"
        d.mkdir()
        (d / "first_name_man_org.csv").write_text("あい,ai,藍\nかおる,kaoru,薫\n", encoding="utf-8")
        (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
        return str(d)

    def _add(self, file, action, entry, value=""):
        return {"id": "%s:%s:%s" % (file, entry.split(",")[0], action), "file": file, "entry": entry,
                "check": "missing_entry", "severity": "warning", "confidence": "high",
                "evidence": "NDL 3人", "proposed_fix": {"action": action, "value": value},
                "status": "approved", "detected_at": "2026-09-06", "detected_by": "qa-update v1"}

    def test_add_kanji_appends_dedup(self, tmp_path):
        ds = self._ds(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [self._add("first_name_man_org.csv", "add_kanji", "あい,ai,藍", "愛,藍")])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert "あい,ai,藍,愛\n" in open(os.path.join(ds, "first_name_man_org.csv"), encoding="utf-8").read()

    def test_add_row_inserts_sorted(self, tmp_path):
        ds = self._ds(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [self._add("first_name_man_org.csv", "add_row", "いつき,itsuki,樹,一樹")])
        apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert open(os.path.join(ds, "first_name_man_org.csv"), encoding="utf-8").read() == \
            "あい,ai,藍\nいつき,itsuki,樹,一樹\nかおる,kaoru,薫\n"

    def test_add_row_merges_when_reading_exists(self, tmp_path):
        ds = self._ds(tmp_path)
        fp = str(tmp_path / "f.jsonl")
        findings_io.append_findings(fp, [self._add("first_name_man_org.csv", "add_row", "あい,ai,愛,藍")])
        result = apply_findings.apply(fp, ds, str(tmp_path / "qa"))
        assert result["applied"] == 1
        assert open(os.path.join(ds, "first_name_man_org.csv"), encoding="utf-8").read() == \
            "あい,ai,藍,愛\nかおる,kaoru,薫\n"
```

```python
# tests/test_qa_rebase.py に追加
def test_rebase_skips_add_actions(tmp_path):
    ds = tmp_path / "dataset"
    ds.mkdir()
    (ds / "first_name_man_org.csv").write_text("あい,ai,藍\n", encoding="utf-8")
    fp = str(tmp_path / "f.jsonl")
    f = {"id": "x", "file": "first_name_man_org.csv", "entry": "いつき,itsuki,樹",
         "check": "missing_entry", "severity": "warning", "confidence": "high", "evidence": "e",
         "proposed_fix": {"action": "add_row", "value": ""}, "status": "pending",
         "detected_at": "2026-09-06", "detected_by": "qa-update v1"}
    findings_io.save_findings(fp, [f])
    summary = rebase_findings.rebase(fp, str(ds), dry_run=False)
    assert findings_io.load_findings(fp)[0]["entry"] == "いつき,itsuki,樹"
    assert summary["unresolved"] == 0
```

（`tests/test_qa_rebase.py` の既存 import に `findings_io` と `rebase_findings` があることを確認し、`rebase()` の戻り値のキー名は既存実装に合わせる。既存の戻り値が `unresolved` でなければ、そのキー名でアサートする。）

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_findings_io.py tests/test_qa_apply.py tests/test_qa_rebase.py -v`
Expected: 新規テストのみ FAIL

- [ ] **Step 3: findings_io.py を拡張**

```python
# findings_io.py: 定数を更新
CHECK_TYPES = {
    "format_error", "romaji_reading_mismatch", "kanji_reading_mismatch",
    "not_a_name", "wrong_gender_file", "duplicate", "cross_file_inconsistency",
    "missing_entry",
}
ACTIONS = {"remove_row", "remove_kanji", "fix_romaji", "fix_reading", "move_to_file", "none",
           "add_row", "add_kanji"}

# validate_finding の proposed_fix 検証ブロック（既存の else 節）に追加:
        if fix["action"] == "add_kanji" and not (value or "").strip():
            problems.append("add_kanji の value が空です")
        if fix["action"] == "add_row":
            cols = (d.get("entry") or "").split(",")
            if len(cols) < 3 or not _FIX_READING_RE.match(cols[0]) or not _FIX_ROMAJI_RE.match(cols[1]) \
                    or any(not k.strip() for k in cols[2:]):
                problems.append("add_row の entry は「ひらがな,ローマ字,漢字...」の完全行である必要があります: %r" % d.get("entry"))
# 関数末尾（return problems の前）に追加:
    sources = d.get("sources")
    if sources is not None:
        if not isinstance(sources, dict) or not isinstance(sources.get("ndl", 0), int) \
                or not isinstance(sources.get("wikidata", 0), int) \
                or not isinstance(sources.get("jmnedict", False), bool):
            problems.append("sources は {ndl: int, wikidata: int, jmnedict: bool} である必要があります")
```

- [ ] **Step 4: apply_findings.py に add_kanji / add_row を実装**

`_apply_one` の `elif action == "fix_reading":` の前に追加:

```python
    elif action == "add_kanji":
        existing = cols[2:]
        for k in _split_values(value):
            if k not in existing:
                existing.append(k)
        cols = cols[:2] + existing
```

`apply()` のメインループで、`d["proposed_fix"]["action"] == "add_row"` の場合は `_apply_one` を呼ばず以下を行う（既存の `current = evolution.get(...)` の解決より前に分岐する）:

```python
        if d["proposed_fix"]["action"] == "add_row":
            new_cols = d["entry"].split(",")
            reading = new_cols[0]
            lines = file_lines[fname]
            dup_idx = _find_duplicate_row(lines, reading)
            if dup_idx is not None:
                merged = _merge_kanji_cols(lines[dup_idx].split(","), new_cols[2:])
                old_line = lines[dup_idx]
                lines[dup_idx] = ",".join(merged)
                _propagate_merge(evolution, fname, old_line, lines[dup_idx])
                print("適用: %s（既存行 %s に統合）" % (d["id"], reading))
            else:
                keys = [ln.split(",")[0] for ln in lines]
                lines.insert(bisect.bisect_left(keys, reading), d["entry"])
                print("適用: %s（行を追加）" % d["id"])
            d["status"] = "applied"
            applied += 1
            continue
```

dry-run の内訳表示（`適用予定:` 行）はそのまま add_row / add_kanji にも出る。

- [ ] **Step 5: rebase_findings.py で add_* を除外**

`rebase()` の対象選定で `if d["proposed_fix"]["action"] in ("add_row", "add_kanji"): continue` を、status による絞り込みの直後に追加する。

- [ ] **Step 6: テストが通ることを確認**

Run: `uv run pytest tests/ -q`
Expected: PASS（全件）

- [ ] **Step 7: コミット**

```bash
git add .claude/skills/validate-dataset/scripts/findings_io.py .claude/skills/qa-apply/scripts/apply_findings.py .claude/skills/qa-apply/scripts/rebase_findings.py tests/test_qa_findings_io.py tests/test_qa_apply.py tests/test_qa_rebase.py
git commit -m "Extend findings schema and apply with add_row/add_kanji for update pipeline

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: 候補生成 `generate_candidates.py`

**Files:**
- Create: `.claude/skills/qa-update/scripts/generate_candidates.py`
- Test: `tests/test_qa_update_candidates.py`

**Interfaces:**
- Consumes: `source_index.load_index/support/gender_of/pair_key`、`build_kanji_list.load_allowed/kanji_allowed`、`checks.load_rows`、`romaji`（validate-dataset/scripts）、`findings_io`
- Produces:
  - `generate_candidates.load_dataset(dataset_dir) -> dict` — `{"first_name_man_org.csv": {reading: [kanji...]}, "first_name_woman_org.csv": {...}, "surnames": {kanji: reading}}`
  - `generate_candidates.romaji_for(reading) -> str` — `romaji.py` のかな通り候補のうちアポストロフィ無しを優先した先頭
  - `generate_candidates.generate(index, dataset, allowed, min_ndl=2, auto_ndl=5, max_candidates=2000, today="YYYY-MM-DD") -> (findings: List[dict], gender_pending: List[dict])`
    - add_kanji: 索引 pairs の given のうち現データに無い (漢字, 読み) で、読みが男女いずれかのファイルに存在するもの。候補条件 `ndl >= min_ndl or wikidata >= 1`。追加先はその読みを持つファイル全て。事前承認条件 `ndl >= auto_ndl and wikidata >= 1`、ただし `gender_of` が追加先と矛盾（male→woman ファイル / female→man ファイル）なら pending
    - add_row: 読みがどのファイルにも無い given。その読みの候補漢字 = 条件を満たす pairs（`kanji_allowed`）。`gender_of` が male/female/unisex なら該当ファイル（unisex は両方）に add_row（entry = `reading,romaji,kanji...`、漢字は根拠降順）。事前承認は索引の gender が wikidata 由来かつ全漢字が事前承認条件を満たすとき。gender が None なら findings に出さず `gender_pending` に `{"reading", "kanji": [...], "sources": {...}}` を入れる
    - 除外: `kanji_allowed(kanji, allowed)` が False の表記は候補にしない
    - 姓: `dataset["surnames"]` の各 (kanji, reading) について、索引 pairs に `surname|kanji|*` が 1 つ以上あり、現 reading の pair が無い場合 `kanji_reading_mismatch`（file=last_name_org.csv、entry=現行行、fix_reading=索引で ndl 最多の読み、confidence=medium）
    - 上限: add_* findings を `ndl + wikidata` 降順に並べ `max_candidates` 件で切る（姓の findings は対象外）
    - id: `<file>:<reading>:missing_entry:add_row` / `<file>:<reading>:missing_entry:add_kanji`、`sources` フィールド、`evidence` = `"NDL 12人 / Wikidata 3人 / JMnedict ✓"`
  - `generate_candidates.carry_over(new, existing) -> List[dict]` — 同 id の既存 status を引き継ぐ（applied/rejected/approved/pending）
  - CLI: `python3 generate_candidates.py --index qa/sources/index.json --dataset-dir ... --out qa/findings/<run-id>-update.jsonl --gender-pending qa/work/<run-id>/gender_pending.json [--min-ndl 2 --auto-ndl 5 --max-candidates 2000]`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_update_candidates.py
"""generate_candidates.py のテスト。"""
import json
import os

import generate_candidates as gc
import source_index as si
import sources_common as sc


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text("あい,ai,藍\nかおる,kaoru,薫\n", encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("かおる,kaoru,香\nさくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("", encoding="utf-8")
    (d / "last_name_org.csv").write_text("金子,100,きんす,kinsu\n佐藤,200,さとう,satou\n", encoding="utf-8")
    return str(d)


def _index():
    return si.build_index([
        sc.record("ndl", "given", "愛", "あい", count=9),           # add_kanji（強根拠）
        sc.record("wikidata", "given", "愛", "あい", gender="female", count=2),
        sc.record("ndl", "given", "哀", "あい", count=1),           # 根拠不足
        sc.record("ndl", "given", "樹", "いつき", count=7),          # add_row（性別は wikidata）
        sc.record("wikidata", "given", "", "いつき", gender="male", count=3),
        sc.record("wikidata", "given", "樹", "いつき", gender="male", count=3),
        sc.record("ndl", "given", "凛", "りん", count=6),            # add_row（性別不明 → pending 判定へ）
        sc.record("ndl", "given", "龘", "たつ", count=9),            # 人名用漢字外 → 除外
        sc.record("ndl", "surname", "金子", "かねこ", count=50),      # 姓の照合
        sc.record("ndl", "surname", "佐藤", "さとう", count=90),
    ])


ALLOWED = {"愛", "哀", "樹", "凛", "藍", "薫", "香", "桜"}


class TestGenerate:
    def test_add_kanji_and_thresholds(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, min_ndl=2, auto_ndl=5, today="2026-09-06")
        by_id = {f["id"]: f for f in fs}
        f = by_id["first_name_man_org.csv:あい:missing_entry:add_kanji"]
        assert f["proposed_fix"] == {"action": "add_kanji", "value": "愛"}
        assert f["status"] == "pending"  # female と man ファイルが矛盾 → 事前承認しない
        assert f["sources"] == {"ndl": 9, "wikidata": 2, "jmnedict": False}
        assert "哀" not in json.dumps(fs, ensure_ascii=False)

    def test_add_row_with_wikidata_gender_is_auto_approved(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        f = next(x for x in fs if x["proposed_fix"]["action"] == "add_row" and x["entry"].startswith("いつき,"))
        assert f["file"] == "first_name_man_org.csv"
        assert f["entry"] == "いつき,itsuki,樹"
        assert f["status"] == "approved"

    def test_gender_unknown_goes_to_pending_list(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        assert not [x for x in fs if x["entry"].startswith("りん,")]
        assert pending == [{"reading": "りん", "kanji": ["凛"], "sources": {"ndl": 6, "wikidata": 0, "jmnedict": False}}]

    def test_disallowed_kanji_excluded(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, pending = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        assert "龘" not in json.dumps(fs, ensure_ascii=False) and not [p for p in pending if p["reading"] == "たつ"]

    def test_surname_mismatch(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, _ = gc.generate(_index(), ds, ALLOWED, today="2026-09-06")
        s = next(x for x in fs if x["file"] == "last_name_org.csv")
        assert s["entry"] == "金子,100,きんす,kinsu" and s["proposed_fix"] == {"action": "fix_reading", "value": "かねこ"}
        assert not [x for x in fs if x["file"] == "last_name_org.csv" and "佐藤" in x["entry"]]

    def test_max_candidates(self, tmp_path):
        ds = gc.load_dataset(_dataset(tmp_path))
        fs, _ = gc.generate(_index(), ds, ALLOWED, max_candidates=1, today="2026-09-06")
        adds = [x for x in fs if x["proposed_fix"]["action"].startswith("add_")]
        assert len(adds) == 1 and adds[0]["sources"]["ndl"] == 9  # 根拠最大のもの

    def test_carry_over(self):
        old = [{"id": "a", "status": "rejected"}, {"id": "b", "status": "applied"}]
        new = [{"id": "a", "status": "pending"}, {"id": "b", "status": "approved"}, {"id": "c", "status": "pending"}]
        out = gc.carry_over(new, old)
        assert [x["status"] for x in out] == ["rejected", "applied", "pending"]


def test_romaji_for():
    assert gc.romaji_for("いつき") == "itsuki"
    assert gc.romaji_for("けんいち") == "kenichi"
    assert gc.romaji_for("さとう") == "satou"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_update_candidates.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# .claude/skills/qa-update/scripts/generate_candidates.py
"""統一索引と現データの差分から findings（add_row / add_kanji / 姓の照合）を生成する。

ポリシーは docs/superpowers/specs/2026-09-05-update-pipeline-design.md §4 に従う。
"""
import argparse
import datetime
import json
import os
import sys
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
    reading = entry.split(",")[0] if file != LAST else entry.split(",")[2]
    return {
        "id": "%s:%s:%s:%s" % (file, reading, check, action), "file": file, "entry": entry,
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
    return adds + surname_findings, gender_pending


def dataset_romaji(dataset, fn, reading):
    # type: (dict, str, str) -> str
    return dataset.get("_romaji", {}).get((fn, reading)) or romaji_for(reading)


def _surname_rows(dataset, kanji, reading):
    # type: (dict, str, str) -> List[List[str]]
    return dataset.get("_surname_rows", {}).get(kanji, [])


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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_update_candidates.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_update_candidates.py .claude/skills/qa-update/scripts/generate_candidates.py
git commit -m "Add candidate generation from source index (add_row/add_kanji/surname check)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: トリアージ UI の add 対応と `source_support` シグナル

**Files:**
- Modify: `.claude/skills/qa-apply/scripts/triage_server.py`
- Modify: `.claude/skills/qa-apply/scripts/triage_ui.html`
- Test: `tests/test_qa_triage.py`

**Interfaces:**
- Produces:
  - `triage_server.compute_signals(finding, index, source_index=None)` — `add_row` / `add_kanji` の finding には `entry_stale` と `value_not_in_row` を付けない。`source_index`（`source_index.load_index` の dict）が与えられた場合、finding の `sources` があればそれを、無ければ対象 (kind, kanji, reading) の `source_index.support` を `{"type": "source_support", "ndl": n, "wikidata": n, "jmnedict": bool}` として付ける（remove_kanji は対象漢字ごと、それ以外は行の先頭漢字）
  - `TriageState(findings_path, dataset_dir, source_index_path=None)`、`make_server(..., source_index_path=None)`、CLI `--source-index qa/sources/index.json`
  - UI: `SIG_LABEL` に `source_support`（`根拠: NDL 12人 / Wikidata 3人 / JMnedict ✓`）を追加し、signal フィルタに `source_support` を追加。add_row のカードは「追加行」と明示し、漢字チップを緑枠（`chip.add`）で表示

- [ ] **Step 1: 失敗するテストを追加**

```python
# tests/test_qa_triage.py に追加
import source_index as si
import sources_common as sc


class TestPhase2Signals:
    def _idx(self, tmp_path):
        return triage_server.load_dataset_index(_dataset(tmp_path))

    def test_add_actions_have_no_stale_signals(self, tmp_path):
        idx = self._idx(tmp_path)
        f = _finding("a", "first_name_man_org.csv", "いつき,itsuki,樹", "add_row", "", check="missing_entry")
        types = {s["type"] for s in triage_server.compute_signals(f, idx)}
        assert "entry_stale" not in types and "value_not_in_row" not in types

    def test_source_support_from_index(self, tmp_path):
        idx = self._idx(tmp_path)
        src = si.build_index([sc.record("ndl", "given", "風雅", "あきお", count=4)])
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅")
        sig = [s for s in triage_server.compute_signals(f, idx, source_index=src) if s["type"] == "source_support"]
        assert sig == [{"type": "source_support", "kanji": "風雅", "ndl": 4, "wikidata": 0, "jmnedict": False}]

    def test_source_support_prefers_finding_sources(self, tmp_path):
        idx = self._idx(tmp_path)
        f = _finding("a", "first_name_man_org.csv", "いつき,itsuki,樹", "add_row", "", check="missing_entry")
        f["sources"] = {"ndl": 7, "wikidata": 3, "jmnedict": True}
        sig = [s for s in triage_server.compute_signals(f, idx, source_index={"pairs": {}, "readings": {}})
               if s["type"] == "source_support"]
        assert sig[0]["ndl"] == 7 and sig[0]["jmnedict"] is True
```

（`_finding` ヘルパは既存のものを使う。`check` 引数が無ければ追加する。）

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_triage.py -v`
Expected: 新規のみ FAIL

- [ ] **Step 3: triage_server.py を修正**

```python
# import に追加（qa-update/scripts をパスへ）
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir, "qa-update", "scripts")))
import source_index as si  # noqa: E402

ADD_ACTIONS = ("add_row", "add_kanji")

# compute_signals(finding, index, source_index=None) に変更し、
# entry_stale / value_not_in_row のブロックを `if action not in ADD_ACTIONS:` で囲む。末尾に追加:
    if source_index is not None:
        if isinstance(finding.get("sources"), dict):
            s = finding["sources"]
            signals.append({"type": "source_support", "kanji": value if action in ("remove_kanji", "add_kanji") else (row["kanji"][0] if row["kanji"] else ""),
                            "ndl": int(s.get("ndl", 0)), "wikidata": int(s.get("wikidata", 0)),
                            "jmnedict": bool(s.get("jmnedict", False))})
        else:
            kind = "surname" if finding["file"] == LAST_NAME_FILE else "given"
            targets = split_values(value) if action == "remove_kanji" else (row["kanji"][:1])
            for k in targets:
                sup = si.support(source_index, kind, k, row["reading"])
                signals.append(dict({"type": "source_support", "kanji": k}, **sup))
```

`TriageState.__init__` に `source_index_path=None` を追加して `self.source_index = si.load_index(source_index_path) if source_index_path else None` を保持し、`items_payload` → `build_items(self.findings, self.index, self.source_index)`、`build_items(findings, index, source_index=None)` は `compute_signals(d, index, source_index)` を呼ぶ。`make_server(findings_path, dataset_dir, port=0, source_index_path=None)`、CLI に `--source-index` を追加。

- [ ] **Step 4: triage_ui.html を修正**

- `SIG_LABEL` に追加: `s.type === 'source_support' ? \`根拠 ${esc(s.kanji)}: NDL ${s.ndl}人 / Wikidata ${s.wikidata}人 / JMnedict ${s.jmnedict ? '✓' : '-'}\``
- signal フィルタの `<select id="fSig">` に `<option value="source_support">source_support</option>` を追加
- カード描画で `g[0].proposed_fix.action === 'add_row'` のとき見出しに `<span class="badge">追加行</span>` を付け、漢字チップに `chip add` クラス（CSS: `.chip.add { border-color: #16a34a; color: #166534; background: #f0fdf4; }`）を適用。`add_kanji` は value の各漢字を緑チップとして行末に追加表示する

- [ ] **Step 5: テストが通ることを確認**

Run: `uv run pytest tests/ -q`
Expected: PASS（全件）

- [ ] **Step 6: コミット**

```bash
git add .claude/skills/qa-apply/scripts/triage_server.py .claude/skills/qa-apply/scripts/triage_ui.html tests/test_qa_triage.py
git commit -m "Show source support signals and add-actions in triage UI

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: 性別判定バッチ `gender_batch.py` と `/qa-update` スキル文書

**Files:**
- Create: `.claude/skills/qa-update/scripts/gender_batch.py`
- Create: `.claude/skills/qa-update/SKILL.md`
- Modify: `CLAUDE.md`
- Test: `tests/test_qa_update_gender.py`

**Interfaces:**
- Consumes: `generate_candidates.romaji_for / _finding 相当の生成`、`findings_io`
- Produces:
  - `gender_batch.prep(pending_path, out_dir, batch_size=100) -> dict` — `gender_pending.json` を `gbatch_NNN.json`（`{"batch_id", "entries": [{"reading", "kanji": [...], "sources": {...}}]}`）に分割し `manifest.json` を書く
  - `gender_batch.merge(out_dir, findings_path, today) -> dict` — `results/gbatch_NNN.json`（`{"batch_id", "decisions": {"りん": "female", ...}}`）を読み、`male|female|unisex` の読みについて add_row findings（status=pending、evidence に「性別: LLM 判定」を付記）を `findings_path` に追加（同 id が既にあれば更新しない）。`unknown` は追加しない。未処理・不正バッチを summary に返す
  - CLI: `python3 gender_batch.py prep --pending P --out-dir D` / `merge --out-dir D --findings F`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_update_gender.py
"""gender_batch.py のテスト。"""
import json
import os

import findings_io
import gender_batch as gb


def _pending(tmp_path):
    p = str(tmp_path / "gender_pending.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump([{"reading": "りん", "kanji": ["凛", "鈴"], "sources": {"ndl": 6, "wikidata": 0, "jmnedict": False}},
                   {"reading": "ひなた", "kanji": ["陽向"], "sources": {"ndl": 3, "wikidata": 0, "jmnedict": True}}], f, ensure_ascii=False)
    return p


def test_prep_and_merge(tmp_path):
    p = _pending(tmp_path)
    out = str(tmp_path / "work")
    m = gb.prep(p, out, batch_size=1)
    assert m["batch_ids"] == ["gbatch_001", "gbatch_002"]
    os.makedirs(os.path.join(out, "results"))
    with open(os.path.join(out, "results", "gbatch_001.json"), "w", encoding="utf-8") as f:
        json.dump({"batch_id": "gbatch_001", "decisions": {"りん": "female"}}, f, ensure_ascii=False)
    fp = str(tmp_path / "f.jsonl")
    findings_io.save_findings(fp, [])
    summary = gb.merge(out, fp, today="2026-09-06")
    fs = findings_io.load_findings(fp)
    assert len(fs) == 1 and fs[0]["file"] == "first_name_woman_org.csv"
    assert fs[0]["entry"] == "りん,rin,凛,鈴" and fs[0]["status"] == "pending"
    assert "LLM" in fs[0]["evidence"] and fs[0]["sources"]["ndl"] == 6
    assert summary["missing_batches"] == ["gbatch_002"]


def test_unisex_and_unknown(tmp_path):
    p = _pending(tmp_path)
    out = str(tmp_path / "work")
    gb.prep(p, out, batch_size=10)
    os.makedirs(os.path.join(out, "results"))
    with open(os.path.join(out, "results", "gbatch_001.json"), "w", encoding="utf-8") as f:
        json.dump({"batch_id": "gbatch_001", "decisions": {"りん": "unisex", "ひなた": "unknown"}}, f, ensure_ascii=False)
    fp = str(tmp_path / "f.jsonl")
    findings_io.save_findings(fp, [])
    gb.merge(out, fp, today="2026-09-06")
    fs = findings_io.load_findings(fp)
    assert sorted(f["file"] for f in fs) == ["first_name_man_org.csv", "first_name_woman_org.csv"]
    assert not [f for f in fs if f["entry"].startswith("ひなた")]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_update_gender.py -v`
Expected: FAIL

- [ ] **Step 3: 実装**

```python
# .claude/skills/qa-update/scripts/gender_batch.py
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

import findings_io  # noqa: E402
import generate_candidates as gc  # noqa: E402

DECISIONS = ("male", "female", "unisex", "unknown")


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
                                extra_evidence="（性別: LLM 判定 %s）" % gender)
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
```

- [ ] **Step 4: SKILL.md を書く**

````markdown
---
name: qa-update
description: Use when データセットを外部ソース（Wikidata・NDL典拠）から年次更新するとき、新しい名の候補を生成するとき、または「データ更新」「候補生成」「qa-update」を求められたとき。取り込み源は MIT 互換ソースのみ。
---

# データセット年次更新（/qa-update）

Wikidata（CC0）と国立国会図書館典拠（自由利用）から名の候補を生成し、Phase 1 の
台帳 → トリアージ UI → /qa-apply の導線で適用する。JMnedict（CC BY-SA）は照合専用。
ランキングサイトはスクレイピングしない。

## 手順

1. run-id を決める（例: `2026-09-update`）。`git status` がクリーンであること。
2. 取得（初回は NDL に 30〜60 分。中断しても再実行で再開する）:
   ```bash
   S=.claude/skills/qa-update/scripts
   python3 $S/fetch_wikidata.py --out qa/sources/wikidata-<date>.jsonl
   python3 $S/fetch_ndl.py --out qa/sources/ndl-<date>.jsonl
   python3 $S/fetch_jmnedict.py --out qa/sources/jmnedict-<date>.jsonl
   ```
3. 索引: `python3 $S/source_index.py --sources qa/sources/wikidata-<date>.jsonl qa/sources/ndl-<date>.jsonl qa/sources/jmnedict-<date>.jsonl --out qa/sources/index.json`
   `qa/sources/manifest.json` に取得日とレコード数を記録してコミットする（スナップショット本体は追跡しない）。
4. 候補生成:
   ```bash
   python3 $S/generate_candidates.py --index qa/sources/index.json \
     --dataset-dir japanese_personal_name_dataset/dataset \
     --out qa/findings/<run-id>.jsonl --gender-pending qa/work/<run-id>/gender_pending.json
   ```
5. 性別判定（`gender_pending.json` が空でない場合）:
   `python3 $S/gender_batch.py prep --pending qa/work/<run-id>/gender_pending.json --out-dir qa/work/<run-id>/gender`
   → バッチごとにサブエージェント（general-purpose）へ下のプロンプトを渡し、`results/` に書かせる（同時 4 つまで）
   → `python3 $S/gender_batch.py merge --out-dir qa/work/<run-id>/gender --findings qa/findings/<run-id>.jsonl`
6. 判断: `python3 .claude/skills/qa-apply/scripts/triage_server.py --findings qa/findings/<run-id>.jsonl --dataset-dir japanese_personal_name_dataset/dataset --source-index qa/sources/index.json`
   事前承認済み（approved）は dry-run で内訳を確認するだけでよい。
7. 適用: `/qa-apply` の手順（dry-run → 明示承認 → ブランチ → 適用 → validate/pytest → 件数同期）。
8. リリース: `/release <version>`（データ追加はマイナーバージョンを上げる）。

## 性別判定プロンプト（テンプレート）

```
あなたは日本人の名前の専門家です。<batch-file の絶対パス> を読み、entries の各 reading について、
kanji（候補漢字）と sources（NDL/Wikidata の人物数）を参考に、その名前が主に使われる性別を判定してください。
判定は male / female / unisex / unknown のいずれか。確信が持てなければ unknown。
出力: <out-dir>/results/<batch_id>.json に {"batch_id": "<batch_id>", "decisions": {"<reading>": "<判定>", ...}} を書く。
全 reading を必ず含めること。
```

## 注意

- `qa/sources/*` は再取得できるため追跡しない。取得日と件数は `qa/sources/manifest.json` に記録する。
- JMnedict 由来の漢字・読みを候補や evidence の値に転記しないこと（索引の ✓ 表示のみ）。
- 候補の上限（既定 2000 件）を超えた分は次回に回る。閾値は `--min-ndl` / `--auto-ndl` で調整する。
````

- [ ] **Step 5: CLAUDE.md の QA 基盤セクションに 1 行追加**

`- \`/qa-apply\`: ...` の行の次に `- \`/qa-update\`: 外部ソース（Wikidata・NDL典拠）からの年次更新。候補は add_row/add_kanji の findings として台帳に入る。設計書: \`docs/superpowers/specs/2026-09-05-update-pipeline-design.md\`` を追加する。

- [ ] **Step 6: テストが通ることを確認**

Run: `uv run pytest tests/ -q`
Expected: PASS（全件）

- [ ] **Step 7: コミット**

```bash
git add .claude/skills/qa-update/scripts/gender_batch.py .claude/skills/qa-update/SKILL.md CLAUDE.md tests/test_qa_update_gender.py
git commit -m "Add gender judgment batch tooling and qa-update skill documentation

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: 初回運用（取得 → 候補 → 判断 → 適用 → v0.3.0）【HITL】

実装ではなく運用タスク。各段階でユーザーの確認を挟む。

- [ ] **Step 1: 実取得（スモーク）** — `fetch_wikidata.py` を実行し件数（Wikidata 男 3,109 / 女 772 / 中性 297 前後、姓 11,000 前後）を報告。`fetch_ndl.py` を実行（長時間。適応分割により 2,000 リクエスト以上、1 秒スリープで 40〜90 分の見込み。失敗時は再実行で再開）し、集計後の given/surname レコード数を報告。`fetch_jmnedict.py` を実行。
- [ ] **Step 2: 索引と候補生成** — `source_index.py`、`generate_candidates.py` を実行し、findings の内訳（add_kanji / add_row / 姓の照合、approved / pending 件数、性別判定待ち件数）を報告。`qa/sources/manifest.json` を書いてコミット。
- [ ] **Step 3: 性別判定バッチ** — `gender_batch.py prep` → サブエージェント → `merge`。
- [ ] **Step 4: トリアージ** — UI を起動し、`source_support` シグナルを見ながらユーザーが判断（事前承認分は内訳確認のみ）。
- [ ] **Step 5: 適用とリリース** — `/qa-apply`（明示承認）→ validate/pytest → README・CLAUDE.md・テストの件数同期 → main マージ → `/release 0.3.0`（ユーザー実行）。

---

## 実行順序と依存関係

```text
Task 1 (common) → Task 2 (kanji list) ─┐
                → Task 3 (wikidata)     ├→ Task 6 (index) → Task 8 (candidates) → Task 10 (gender batch + docs)
                → Task 4 (ndl)          │                       ↑
                → Task 5 (jmnedict)  ───┘                       │
Task 7 (schema/apply/rebase) ──────────────────────────────────┘（Task 8 は findings_io の add_* を使う）
Task 9 (triage UI) ← Task 6, Task 7
Task 11 (運用) ← 全タスク
```

Task 2〜5 は Task 1 の後に並列可（ただし実装サブエージェントは逐次投入する）。Task 7 は Task 1 と独立。
