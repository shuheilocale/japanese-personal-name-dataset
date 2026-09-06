"""保留 findings の判断 UI（ローカル Web サーバ）。

findings JSONL と dataset CSV を読み、行単位の表示用アイテムと客観シグナルを
JSON API で返す。判断（approved/rejected/pending）は即座に JSONL へ原子的に書き戻す。
"""
import argparse
import json
import os
import re
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "validate-dataset", "scripts")))
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    os.pardir, os.pardir, "qa-update", "scripts")))

import findings_io  # noqa: E402
import source_index as si  # noqa: E402

FIRST_NAME_FILES = [
    "first_name_man_org.csv", "first_name_man_opti.csv",
    "first_name_woman_org.csv", "first_name_woman_opti.csv",
]
LAST_NAME_FILE = "last_name_org.csv"
ADD_ACTIONS = ("add_row", "add_kanji")
SUFFIX_RULES = {
    "郎": "ろう", "朗": "ろう", "彦": "ひこ", "子": "こ", "也": "や", "哉": "や",
    "夫": "お", "雄": "お", "男": "お", "美": "み", "江": "え", "恵": "え", "枝": "え",
}
DECIDABLE = ("pending", "approved", "rejected")
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
_VALUE_SEP_RE = re.compile(r"[,、]")


def split_values(value):
    # type: (str) -> List[str]
    """proposed_fix.value を `,` / `、` で分割し、strip して空要素を除いたリストを返す。

    例: "克真, 克麻, 勝真" → ["克真", "克麻", "勝真"]
    """
    return [v.strip() for v in _VALUE_SEP_RE.split(value or "") if v.strip()]


def host_allowed(host):
    # type: (str) -> bool
    """Host ヘッダが 127.0.0.1[:port] / localhost[:port] のときだけ True（CSRF 対策）。"""
    h = (host or "").strip().lower()
    if ":" in h:
        h, port = h.rsplit(":", 1)
        if not port.isdigit():
            return False
    return h in ALLOWED_HOSTS


def _read_raw_lines(path):
    # type: (str) -> List[str]
    """apply_findings と同じ規則（splitlines・空行除去）で生の行を読む。"""
    with open(path, encoding="utf-8") as f:
        return [ln for ln in f.read().splitlines() if ln.strip()]


def _empty_info():
    # type: () -> dict
    return {"kanji_index": {}, "readings": set(), "rows": set(), "by_key": {}}


def load_dataset_index(dataset_dir):
    # type: (str) -> Dict[str, dict]
    """ファイルごとに 漢字→読み集合・読み集合・現行 raw 行集合・キー→raw 行 を作る。

    キーは名ファイルでは読み（col0）、姓ファイルでは漢字（col0）。
    """
    index = {}  # type: Dict[str, dict]
    for fn in FIRST_NAME_FILES + [LAST_NAME_FILE]:
        info = _empty_info()
        for raw in _read_raw_lines(os.path.join(dataset_dir, fn)):
            r = raw.split(",")
            if len(r) < 2:
                continue
            info["rows"].add(raw)
            info["by_key"].setdefault(r[0], []).append(raw)
            if fn == LAST_NAME_FILE:
                if len(r) == 4:
                    info["readings"].add(r[2])
                continue
            info["readings"].add(r[0])
            for k in r[2:]:
                info["kanji_index"].setdefault(k, set()).add(r[0])
        index[fn] = info
    return index


def parse_row(file, entry):
    # type: (str, str) -> dict
    c = entry.split(",")
    if file == LAST_NAME_FILE and len(c) == 4:
        return {"reading": c[2], "romaji": c[3], "kanji": [c[0]], "population": c[1]}
    return {"reading": c[0], "romaji": c[1] if len(c) > 1 else "", "kanji": c[2:], "population": None}


def current_row_for(entry, info):
    # type: (str, dict) -> object
    """entry と同じキー（col0）を持つ現行行が一意ならその raw、なければ None。"""
    cands = info["by_key"].get(entry.split(",")[0], [])
    return cands[0] if len(cands) == 1 else None


def compute_signals(finding, index, source_index=None):
    # type: (dict, Dict[str, dict], object) -> List[dict]
    signals = []  # type: List[dict]
    row = parse_row(finding["file"], finding["entry"])
    action = finding["proposed_fix"]["action"]
    value = finding["proposed_fix"].get("value", "")
    info = index.get(finding["file"])
    known_file = info is not None
    if info is None:
        info = _empty_info()
    if action not in ADD_ACTIONS:
        if action == "remove_kanji":
            targets = split_values(value)
            for k in targets:
                others = sorted(info["kanji_index"].get(k, set()) - {row["reading"]})
                if others:
                    signals.append({"type": "dup_elsewhere", "kanji": k, "readings": others})
            for k in targets:
                for suffix, expected in SUFFIX_RULES.items():
                    if k.endswith(suffix) and not row["reading"].endswith(expected):
                        signals.append({"type": "suffix_rule", "kanji": k,
                                        "suffix": suffix, "expected": expected})
                        break
            missing = [k for k in targets if k not in row["kanji"]]
            if missing:
                signals.append({"type": "value_not_in_row", "kanji": missing})
        if (action == "fix_reading" and finding["file"] in FIRST_NAME_FILES
                and value in info["readings"]):
            signals.append({"type": "fix_reading_dup"})
        if known_file and finding["entry"] not in info["rows"]:
            signals.append({"type": "entry_stale",
                            "current": current_row_for(finding["entry"], info)})
    if source_index is not None:
        if isinstance(finding.get("sources"), dict):
            s = finding["sources"]
            signals.append({
                "type": "source_support",
                "kanji": value if action in ("remove_kanji", "add_kanji")
                else (row["kanji"][0] if row["kanji"] else ""),
                "ndl": int(s.get("ndl", 0)), "wikidata": int(s.get("wikidata", 0)),
                "jmnedict": bool(s.get("jmnedict", False))})
        else:
            kind = "surname" if finding["file"] == LAST_NAME_FILE else "given"
            # remove_kanji / add_kanji は対象・候補の漢字（value）、それ以外は行の先頭漢字の根拠を引く
            targets = split_values(value) if action in ("remove_kanji", "add_kanji") else row["kanji"][:1]
            for k in targets:
                sup = si.support(source_index, kind, k, row["reading"])
                signals.append(dict({"type": "source_support", "kanji": k}, **sup))
    return signals


def search_url(targets, row):
    # type: (List[str], dict) -> str
    terms = list(targets) if targets else list(row["kanji"][:3])
    query = " ".join(terms + [row["reading"], "名前"])
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)


def build_items(findings, index, source_index=None):
    # type: (List[dict], Dict[str, dict], object) -> List[dict]
    items = []
    for d in findings:
        row = parse_row(d["file"], d["entry"])
        action = d["proposed_fix"]["action"]
        value = d["proposed_fix"].get("value", "")
        # targets は UI で「削除対象」として強調する漢字（remove_kanji のみ）。
        # 検索 URL は add_kanji でも候補漢字（value）で引く。
        targets = split_values(value) if action == "remove_kanji" else []
        search_terms = split_values(value) if action == "add_kanji" else targets
        item = dict(d)
        item.update({
            "row": row, "targets": targets,
            "signals": compute_signals(d, index, source_index),
            "search_url": search_url(search_terms, row),
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
    """tmp に書いてから os.replace で置換する。失敗時は tmp を残さない。"""
    tmp = path + ".tmp"
    try:
        findings_io.save_findings(tmp, findings)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


UI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "triage_ui.html")


class TriageState(object):
    def __init__(self, findings_path, dataset_dir, source_index_path=None):
        # type: (str, str, object) -> None
        self.findings_path = findings_path
        self.findings = findings_io.load_findings(findings_path)
        self.index = load_dataset_index(dataset_dir)
        self.source_index = si.load_index(source_index_path) if source_index_path else None
        self._lock = threading.Lock()

    def items_payload(self):
        # type: () -> dict
        with self._lock:
            return {"items": build_items(self.findings, self.index, self.source_index),
                    "counts": count_statuses(self.findings)}

    def decide(self, ids, status):
        # type: (List[str], str) -> dict
        """判断を反映して保存する。保存に失敗したらメモリ上の status を戻して再送出。"""
        with self._lock:
            by_id = {d["id"]: d for d in self.findings}
            snapshot = {i: by_id[i]["status"] for i in ids if i in by_id}
            n = apply_decision(self.findings, ids, status)
            try:
                save_atomic(self.findings_path, self.findings)
            except OSError:
                for i, prev in snapshot.items():
                    by_id[i]["status"] = prev
                raise
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
            elif self.path == "/favicon.ico":
                self._send(204, b"", "text/plain; charset=utf-8")
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api/decide":
                self._send(404, {"error": "not found"})
                return
            if not host_allowed(self.headers.get("Host", "")):
                self._send(403, {"error": "許可されていない Host ヘッダです"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0:
                    raise ValueError("Content-Length が負です")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                result = state.decide(list(body.get("ids", [])), body.get("status", ""))
            except (ValueError, KeyError, TypeError, AttributeError) as e:
                self._send(400, {"error": str(e)})
                return
            except OSError as e:
                self._send(500, {"error": "保存に失敗しました: %s" % e})
                return
            self._send(200, result)

        def log_message(self, fmt, *args):  # 静かにする
            pass

    return Handler


def make_server(findings_path, dataset_dir, port=0, source_index_path=None):
    # type: (str, str, int, object) -> ThreadingHTTPServer
    state = TriageState(findings_path, dataset_dir, source_index_path)
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
    parser.add_argument("--source-index", default=None,
                         help="根拠シグナル用の統一索引（例: qa/sources/index.json）")
    args = parser.parse_args()
    extra = {"source_index_path": args.source_index} if args.source_index else {}
    try:
        server = make_server(args.findings, args.dataset_dir, args.port, **extra)
    except OSError as e:
        print("ポート %d を使用できません（他のプロセスが使用中の可能性があります。"
              "--port で別のポートを指定してください）: %s" % (args.port, e), file=sys.stderr)
        return 1
    url = "http://127.0.0.1:%d/" % server.server_address[1]
    print("トリアージ UI: %s  （Ctrl+C で終了）" % url)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    _force_utf8_output()
    sys.exit(main())
