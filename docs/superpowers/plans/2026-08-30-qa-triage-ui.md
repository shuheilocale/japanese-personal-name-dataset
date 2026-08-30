# QA トリアージ UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留 findings を行単位で表示し、客観シグナル付きでキー操作・一括操作により承認/却下できるローカル Web ツールを作る。

**Architecture:** 標準ライブラリの `http.server` によるサーバ（`triage_server.py`）が findings JSONL と dataset CSV を読み、シグナルを計算して JSON API で返す。静的 HTML（`triage_ui.html`）が画面を描画し、判断を `POST /api/decide` で書き戻す。既存の `findings_io` / `checks` を再利用する。

**Tech Stack:** Python 標準ライブラリ（http.server, json, urllib, webbrowser, threading）、vanilla JS/CSS。

**Spec:** `docs/superpowers/specs/2026-08-30-qa-triage-ui-design.md`

## Global Constraints

- 全 .py は Python 3.8 互換構文（`typing.List/Dict/Optional`、`X | Y` 禁止）。PostToolUse フックが vermin で検査する。
- 標準ライブラリのみ。I/O は `encoding="utf-8"`、JSONL 書き込みは `newline="\n"`。
- dataset CSV は読み取りのみ。findings JSONL の書き込みは tmp ファイル→`os.replace` で原子的に行う。
- `applied` 状態の finding は変更禁止。status は `pending|approved|rejected` のみ受け付ける。
- テスト実行: `uv run pytest tests/test_qa_triage.py -v`。tests/conftest.py が `.claude/skills/qa-apply/scripts` をパスに追加済み。
- コミットメッセージは英語命令形 + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

### Task 1: シグナル計算・アイテム構築・判断書き戻し（`triage_server.py` のコア）

**Files:**
- Create: `.claude/skills/qa-apply/scripts/triage_server.py`
- Test: `tests/test_qa_triage.py`

**Interfaces:**
- Consumes: `findings_io.load_findings/save_findings`、`checks.load_rows`（`.claude/skills/validate-dataset/scripts`）
- Produces:
  - `load_dataset_index(dataset_dir) -> Dict[str, dict]`: ファイル名 → `{"kanji_index": {漢字: set(読み)}, "readings": set(読み)}`
  - `parse_row(file, entry) -> dict`: `{"reading", "romaji", "kanji": List[str], "population": Optional[str]}`
  - `compute_signals(finding, index) -> List[dict]`
  - `build_items(findings, index) -> List[dict]`
  - `count_statuses(findings) -> Dict[str, int]`
  - `apply_decision(findings, ids, status) -> int`（更新件数。例外: `ValueError`）
  - `save_atomic(path, findings) -> None`

- [ ] **Step 1: 失敗するテストを書く**

```python
# tests/test_qa_triage.py
"""triage_server.py（保留 findings の判断 UI）のテスト。"""
import json
import os
import urllib.parse

import pytest

import findings_io
import triage_server


def _dataset(tmp_path):
    d = tmp_path / "dataset"
    d.mkdir()
    (d / "first_name_man_org.csv").write_text(
        "あきお,akio,明男,風雅\nあきら,akira,明,晃\nふうが,fuuga,風雅\nたろう,tarou,太郎\n",
        encoding="utf-8")
    (d / "first_name_man_opti.csv").write_text("あきら,akira,明\n", encoding="utf-8")
    (d / "first_name_woman_org.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "first_name_woman_opti.csv").write_text("さくら,sakura,桜\n", encoding="utf-8")
    (d / "last_name_org.csv").write_text("佐藤,1887000,さとう,satou\n", encoding="utf-8")
    return str(d)


def _finding(id_, file, entry, action, value, check="kanji_reading_mismatch",
             status="pending", confidence="medium"):
    return {"id": id_, "file": file, "entry": entry, "check": check, "severity": "error",
            "confidence": confidence, "evidence": "テスト", "proposed_fix": {"action": action, "value": value},
            "status": status, "detected_at": "2026-08-30", "detected_by": "qa-review v1"}


class TestSignals:
    def test_dup_elsewhere(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅")
        sig = triage_server.compute_signals(f, idx)
        assert {"type": "dup_elsewhere", "readings": ["ふうが"]} in sig

    def test_no_dup_signal_when_only_here(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "明男")
        assert not [s for s in triage_server.compute_signals(f, idx) if s["type"] == "dup_elsewhere"]

    def test_suffix_rule(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男,太郎", "remove_kanji", "太郎")
        sig = triage_server.compute_signals(f, idx)
        assert {"type": "suffix_rule", "suffix": "郎", "expected": "ろう"} in sig
        ok = _finding("b", "first_name_man_org.csv", "たろう,tarou,太郎", "remove_kanji", "太郎")
        assert not [s for s in triage_server.compute_signals(ok, idx) if s["type"] == "suffix_rule"]

    def test_fix_reading_dup(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        f = _finding("a", "first_name_man_org.csv", "あきお,akio,明男", "fix_reading", "あきら")
        assert {"type": "fix_reading_dup"} in triage_server.compute_signals(f, idx)
        g = _finding("b", "first_name_man_org.csv", "あきお,akio,明男", "fix_reading", "あきひこ")
        assert not [s for s in triage_server.compute_signals(g, idx) if s["type"] == "fix_reading_dup"]


class TestBuildItems:
    def test_row_and_targets(self, tmp_path):
        idx = triage_server.load_dataset_index(_dataset(tmp_path))
        fs = [_finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅"),
              _finding("b", "last_name_org.csv", "佐藤,1887000,さとう,satou", "fix_reading", "さと")]
        items = triage_server.build_items(fs, idx)
        assert items[0]["row"] == {"reading": "あきお", "romaji": "akio", "kanji": ["明男", "風雅"], "population": None}
        assert items[0]["targets"] == ["風雅"]
        assert items[1]["row"] == {"reading": "さとう", "romaji": "satou", "kanji": ["佐藤"], "population": "1887000"}
        assert "風雅" in urllib.parse.unquote(items[0]["search_url"])

    def test_counts(self):
        fs = [_finding("a", "f", "x,y", "none", "", status="pending"),
              _finding("b", "f", "x,y", "none", "", status="applied")]
        assert triage_server.count_statuses(fs) == {"pending": 1, "approved": 0, "rejected": 0, "applied": 1}


class TestDecision:
    def test_apply_and_save(self, tmp_path):
        p = str(tmp_path / "f.jsonl")
        fs = [_finding("a", "f", "x,y", "none", ""), _finding("b", "f", "x,y", "none", "")]
        findings_io.save_findings(p, fs)
        n = triage_server.apply_decision(fs, ["a"], "approved")
        assert n == 1 and fs[0]["status"] == "approved"
        triage_server.save_atomic(p, fs)
        assert findings_io.load_findings(p)[0]["status"] == "approved"
        assert not [x for x in os.listdir(str(tmp_path)) if x.endswith(".tmp")]

    def test_rejects_bad_input(self):
        fs = [_finding("a", "f", "x,y", "none", "", status="applied")]
        with pytest.raises(ValueError):
            triage_server.apply_decision(fs, ["a"], "approved")
        with pytest.raises(ValueError):
            triage_server.apply_decision(fs, ["zzz"], "approved")
        with pytest.raises(ValueError):
            triage_server.apply_decision(fs, [], "done")
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_triage.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'triage_server'`）

- [ ] **Step 3: コアを実装**

```python
# .claude/skills/qa-apply/scripts/triage_server.py
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_triage.py -v`
Expected: PASS（全件）

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_triage.py .claude/skills/qa-apply/scripts/triage_server.py
git commit -m "Add triage core: objective signals and decision write-back for pending findings

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: HTTP サーバと CLI

**Files:**
- Modify: `.claude/skills/qa-apply/scripts/triage_server.py`（末尾に追加）
- Test: `tests/test_qa_triage.py`（クラス追加）

**Interfaces:**
- Consumes: Task 1 の全関数
- Produces:
  - `make_server(findings_path, dataset_dir, port=0) -> ThreadingHTTPServer`（`server.server_address[1]` で実ポート取得）
  - HTTP: `GET /`（triage_ui.html）、`GET /api/items`、`POST /api/decide`
  - CLI: `--findings --dataset-dir [--port 8765] [--no-browser]`

- [ ] **Step 1: 失敗するテストを追加**

```python
# tests/test_qa_triage.py に追加
import http.client
import threading


class TestHttp:
    def _start(self, tmp_path):
        ds = _dataset(tmp_path)
        p = str(tmp_path / "f.jsonl")
        findings_io.save_findings(p, [
            _finding("a", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "風雅"),
            _finding("b", "first_name_man_org.csv", "あきお,akio,明男,風雅", "remove_kanji", "明男"),
        ])
        srv = triage_server.make_server(p, ds, port=0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        return srv, p

    def _req(self, srv, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        conn.close()
        return resp.status, data

    def test_items_and_decide(self, tmp_path):
        srv, p = self._start(tmp_path)
        try:
            status, data = self._req(srv, "GET", "/api/items")
            assert status == 200
            body = json.loads(data)
            assert body["counts"]["pending"] == 2
            assert body["items"][0]["signals"][0]["type"] == "dup_elsewhere"
            status, data = self._req(srv, "POST", "/api/decide", {"ids": ["a"], "status": "approved"})
            assert status == 200 and json.loads(data)["counts"]["approved"] == 1
            assert findings_io.load_findings(p)[0]["status"] == "approved"
            status, _ = self._req(srv, "POST", "/api/decide", {"ids": ["zzz"], "status": "approved"})
            assert status == 400
            status, data = self._req(srv, "GET", "/")
            assert status == 200 and "<html" in data.lower()
        finally:
            srv.shutdown()
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_qa_triage.py::TestHttp -v`
Expected: FAIL（`make_server` 未定義）

- [ ] **Step 3: サーバを実装**

```python
# triage_server.py 末尾に追加
UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "triage_ui.html")


class TriageState(object):
    def __init__(self, findings_path, dataset_dir):
        # type: (str, str) -> None
        self.findings_path = findings_path
        self.findings = findings_io.load_findings(findings_path)
        self.index = load_dataset_index(dataset_dir)

    def items_payload(self):
        # type: () -> dict
        return {"items": build_items(self.findings, self.index),
                "counts": count_statuses(self.findings)}

    def decide(self, ids, status):
        # type: (List[str], str) -> dict
        n = apply_decision(self.findings, ids, status)
        save_atomic(self.findings_path, self.findings)
        return {"updated": n, "counts": count_statuses(self.findings)}


def make_handler(state):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, content_type="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                with open(UI_PATH, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            elif self.path == "/api/items":
                self._send(200, state.items_payload())
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/decide":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                result = state.decide(list(body.get("ids", [])), body.get("status", ""))
            except (ValueError, KeyError, TypeError) as e:
                self._send(400, {"error": str(e)})
                return
            self._send(200, result)

        def log_message(self, fmt, *args):  # 静かにする
            pass

    return Handler


def make_server(findings_path, dataset_dir, port=0):
    # type: (str, str, int) -> ThreadingHTTPServer
    state = TriageState(findings_path, dataset_dir)
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(state))


def _force_utf8_output():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = make_server(args.findings, args.dataset_dir, args.port)
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    print("トリアージ UI: %s  （Ctrl+C で終了）" % url)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    _force_utf8_output()
    sys.exit(main())
```

Task 3 で triage_ui.html を作るまで `GET /` はファイル不在で失敗するため、このタスクでは `.claude/skills/qa-apply/scripts/triage_ui.html` に最小のプレースホルダ `<html><body>triage</body></html>` を置く（Task 3 で置き換える）。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_qa_triage.py -v`
Expected: PASS（全件）

- [ ] **Step 5: コミット**

```bash
git add tests/test_qa_triage.py .claude/skills/qa-apply/scripts/triage_server.py .claude/skills/qa-apply/scripts/triage_ui.html
git commit -m "Add triage HTTP server and CLI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 画面（`triage_ui.html`）

**Files:**
- Modify: `.claude/skills/qa-apply/scripts/triage_ui.html`（プレースホルダを置き換え）

**Interfaces:**
- Consumes: `GET /api/items`（items[].row/targets/signals/search_url + finding フィールド）、`POST /api/decide`
- Produces: ブラウザ UI（外部リソース読み込みなし）

- [ ] **Step 1: 画面を実装**

````html
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>QA トリアージ</title>
<style>
  body { margin: 0; font-family: -apple-system, "Hiragino Sans", "Noto Sans JP", sans-serif; display: grid; grid-template-columns: 320px 1fr; grid-template-rows: 48px 1fr; height: 100vh; }
  header { grid-column: 1 / 3; display: flex; align-items: center; gap: 16px; padding: 0 16px; background: #1f2937; color: #fff; }
  header .counts span { margin-right: 12px; }
  header button { background: #374151; color: #fff; border: 0; padding: 6px 10px; border-radius: 4px; cursor: pointer; }
  aside { overflow: auto; border-right: 1px solid #ddd; padding: 8px; font-size: 13px; }
  aside select, aside input { width: 100%; margin: 2px 0 8px; }
  #list div { padding: 4px 6px; cursor: pointer; border-radius: 4px; display: flex; justify-content: space-between; }
  #list div.cur { background: #dbeafe; }
  main { overflow: auto; padding: 16px 24px; }
  .chip { display: inline-block; padding: 2px 8px; margin: 2px; border: 1px solid #cbd5e1; border-radius: 12px; font-size: 15px; }
  .chip.target { border-color: #dc2626; color: #dc2626; text-decoration: line-through; background: #fef2f2; }
  .finding { border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; margin: 10px 0; }
  .finding.approved { border-color: #16a34a; background: #f0fdf4; }
  .finding.rejected { border-color: #9ca3af; background: #f9fafb; opacity: .7; }
  .badge { display: inline-block; font-size: 12px; padding: 1px 6px; border-radius: 4px; margin-right: 4px; background: #e5e7eb; }
  .badge.sig { background: #fef3c7; }
  .badge.high { background: #fecaca; } .badge.medium { background: #fde68a; } .badge.low { background: #e5e7eb; }
  .keys { color: #6b7280; font-size: 12px; margin-top: 12px; }
</style>
</head>
<body>
<header>
  <strong>QA トリアージ</strong>
  <div class="counts" id="counts"></div>
  <button id="bulkApprove">表示中を一括承認</button>
  <button id="bulkReject">表示中を一括却下</button>
</header>
<aside>
  <label>status <select id="fStatus"><option value="pending">pending</option><option value="approved">approved</option><option value="rejected">rejected</option><option value="">all</option></select></label>
  <label>check <select id="fCheck"><option value="">all</option></select></label>
  <label>confidence <select id="fConf"><option value="">all</option><option>high</option><option>medium</option><option>low</option></select></label>
  <label>action <select id="fAction"><option value="">all</option></select></label>
  <label>file <select id="fFile"><option value="">all</option></select></label>
  <label>signal <select id="fSig"><option value="">all</option><option value="dup_elsewhere">dup_elsewhere</option><option value="suffix_rule">suffix_rule</option><option value="fix_reading_dup">fix_reading_dup</option><option value="none">なし</option></select></label>
  <div id="listCount"></div>
  <div id="list"></div>
</aside>
<main id="main"></main>
<script>
let items = [], rows = [], cur = 0, undo = [];
const $ = id => document.getElementById(id);
const SIG_LABEL = s => s.type === 'dup_elsewhere' ? `別読み行にも存在: ${s.readings.join('・')}`
  : s.type === 'suffix_rule' ? `接尾辞「${s.suffix}」は通常「${s.expected}」読み` : '提案読みは既存行と重複';

async function load() {
  const r = await fetch('/api/items'); const body = await r.json();
  items = body.items; renderCounts(body.counts); fillFilters(); apply();
}
function renderCounts(c) {
  $('counts').innerHTML = ['pending','approved','rejected','applied'].map(k => `<span>${k}: <b>${c[k]||0}</b></span>`).join('');
}
function fillFilters() {
  const uniq = (k) => [...new Set(items.map(i => k(i)))].sort();
  for (const [id, f] of [['fCheck', i => i.check], ['fAction', i => i.proposed_fix.action], ['fFile', i => i.file]]) {
    const sel = $(id); for (const v of uniq(f)) { const o = document.createElement('option'); o.value = v; o.textContent = v; sel.appendChild(o); }
  }
}
function filtered() {
  const st = $('fStatus').value, ck = $('fCheck').value, cf = $('fConf').value, ac = $('fAction').value, fl = $('fFile').value, sg = $('fSig').value;
  return items.filter(i => (!st || i.status === st) && (!ck || i.check === ck) && (!cf || i.confidence === cf)
    && (!ac || i.proposed_fix.action === ac) && (!fl || i.file === fl)
    && (!sg || (sg === 'none' ? i.signals.length === 0 : i.signals.some(s => s.type === sg))));
}
function apply() {
  const f = filtered(); const map = new Map();
  for (const i of f) { const key = i.file + '|' + i.entry; if (!map.has(key)) map.set(key, []); map.get(key).push(i); }
  rows = [...map.values()]; cur = Math.min(cur, Math.max(rows.length - 1, 0));
  $('listCount').textContent = `${f.length} 件 / ${rows.length} 行`;
  $('list').innerHTML = rows.map((g, n) => `<div class="${n === cur ? 'cur' : ''}" data-n="${n}"><span>${g[0].row.reading}</span><span>${g.length}件 ${g.some(i => i.signals.length) ? '⚑' : ''}</span></div>`).join('');
  $('list').querySelectorAll('div').forEach(d => d.onclick = () => { cur = +d.dataset.n; apply(); });
  renderMain();
}
function renderMain() {
  const g = rows[cur]; if (!g) { $('main').innerHTML = '<p>表示する行がありません。</p>'; return; }
  const row = g[0].row, targets = new Set(g.flatMap(i => i.targets));
  const chips = row.kanji.map(k => `<span class="chip ${targets.has(k) ? 'target' : ''}">${k}</span>`).join('');
  const findings = g.map(i => `<div class="finding ${i.status}">
      <span class="badge ${i.confidence}">${i.confidence}</span><span class="badge">${i.check}</span>
      <span class="badge">${i.proposed_fix.action} ${i.proposed_fix.value || ''}</span><span class="badge">${i.status}</span>
      ${i.signals.map(s => `<span class="badge sig">⚑ ${SIG_LABEL(s)}</span>`).join('')}
      <p>${i.evidence}</p><a href="${i.search_url}" target="_blank">検索</a></div>`).join('');
  $('main').innerHTML = `<h2>${row.reading} <small>${row.romaji}${row.population ? ' / ' + row.population + '人' : ''}</small> <small>${g[0].file}</small></h2>
    <div>${chips}</div>${findings}
    <div class="keys">a=承認 r=却下 s=保留 u=取り消し j/k=次/前 （この行の ${g.length} 件すべてに適用）</div>`;
  const el = $('list').children[cur]; if (el) el.scrollIntoView({ block: 'nearest' });
}
async function decide(ids, status, remember = true) {
  if (remember) undo.push(ids.map(id => ({ id, prev: items.find(i => i.id === id).status })));
  const r = await fetch('/api/decide', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids, status }) });
  if (!r.ok) { alert('エラー: ' + (await r.text())); return; }
  const body = await r.json(); renderCounts(body.counts);
  for (const i of items) if (ids.includes(i.id)) i.status = status;
}
async function decideRow(status) {
  const g = rows[cur]; if (!g) return;
  await decide(g.map(i => i.id), status);
  apply();
}
async function undoLast() {
  const last = undo.pop(); if (!last) return;
  for (const { id, prev } of last) await decide([id], prev, false);
  apply();
}
async function bulk(status) {
  const f = filtered(); if (!f.length) return;
  if (!confirm(`表示中の ${f.length} 件を ${status} にします。よろしいですか？`)) return;
  await decide(f.map(i => i.id), status); apply();
}
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
  if (e.key === 'a') decideRow('approved'); else if (e.key === 'r') decideRow('rejected'); else if (e.key === 's') decideRow('pending');
  else if (e.key === 'u') undoLast(); else if (e.key === 'j') { cur = Math.min(cur + 1, rows.length - 1); apply(); }
  else if (e.key === 'k') { cur = Math.max(cur - 1, 0); apply(); }
});
for (const id of ['fStatus', 'fCheck', 'fConf', 'fAction', 'fFile', 'fSig']) $(id).onchange = () => { cur = 0; apply(); };
$('bulkApprove').onclick = () => bulk('approved'); $('bulkReject').onclick = () => bulk('rejected');
load();
</script>
</body>
</html>
````

- [ ] **Step 2: 実データでスモーク確認**

Run: `python3 .claude/skills/qa-apply/scripts/triage_server.py --findings qa/findings/2026-07-full.jsonl --dataset-dir japanese_personal_name_dataset/dataset --port 8765 --no-browser &` → `curl -s http://127.0.0.1:8765/api/items | python3 -c "import json,sys; b=json.load(sys.stdin); print(b['counts'], len(b['items']))"` → counts の pending が 763 であること。`curl -s http://127.0.0.1:8765/ | head -3` に `<!doctype html>` が含まれること。確認後サーバを停止（`kill %1`）。**判断の POST は実データに対して行わないこと**（テストでのみ）。

- [ ] **Step 3: pytest 全体の回帰確認**

Run: `uv run pytest tests/ -q`
Expected: PASS（全件）

- [ ] **Step 4: コミット**

```bash
git add .claude/skills/qa-apply/scripts/triage_ui.html
git commit -m "Add triage UI page with row-grouped review, signals, keyboard and bulk actions

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: ドキュメント更新

**Files:**
- Modify: `.claude/skills/qa-apply/SKILL.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: qa-apply SKILL.md の「手順」の前に承認セクションを追加**

```markdown
## 承認（トリアージ UI）

保留 findings の承認/却下は以下で起動するローカル UI で行う（判断は即座に JSONL へ保存される）:

```bash
python3 .claude/skills/qa-apply/scripts/triage_server.py \
  --findings qa/findings/<run-id>.jsonl \
  --dataset-dir japanese_personal_name_dataset/dataset
```

行単位でキー操作（a=承認 / r=却下 / s=保留 / u=取り消し / j,k=移動）。左のフィルタで絞り込み、「表示中を一括承認/却下」で同種の疑義をまとめて処理できる。客観シグナル（別読み行に同一漢字あり・接尾辞ルール違反・提案読みの重複）が ⚑ で表示される。判断後はこのスキルの手順で適用する。
```

- [ ] **Step 2: CLAUDE.md の QA 基盤セクションの `/qa-apply` 行を更新**

`- \`/qa-apply\`: 承認済み findings の一括適用（ユーザーの明示承認必須）` を
`- \`/qa-apply\`: 承認済み findings の一括適用（ユーザーの明示承認必須）。承認判断は \`triage_server.py\` のローカル UI で行う` に置き換える。

- [ ] **Step 3: コミット**

```bash
git add .claude/skills/qa-apply/SKILL.md CLAUDE.md
git commit -m "Document triage UI in qa-apply skill and CLAUDE.md

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
