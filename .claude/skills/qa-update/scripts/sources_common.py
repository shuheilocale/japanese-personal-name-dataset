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
_NAME_PART_RE = re.compile(r"^[぀-ゟ一-鿿㐀-䶿豈-﫿々ヶヵノ]{1,5}$")


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


def force_utf8_output():
    # type: () -> None
    """stdout/stderr を UTF-8 に再設定する（Windows の cp1252 コンソールで日本語出力が落ちるのを防ぐ）。

    各 CLI の `if __name__ == "__main__":` で main() の前に呼ぶ。argparse の --help も
    日本語を含むため、parse_args より前に済ませる必要がある。
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure") and (stream.encoding or "").lower() not in ("utf-8", "utf8"):
            stream.reconfigure(encoding="utf-8", errors="replace")
