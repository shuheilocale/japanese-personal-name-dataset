"""常用漢字（2136 字）と人名用漢字（864 字）の文字集合を生成する。

Wikipedia の「常用漢字一覧」「人名用漢字一覧」の表から [[wikt:X|X]] 形式の
1 文字リンクを抽出する。文字の集合自体は官報告示・法令別表に基づく公知の
事実であり、生成物 qa/kanji/jinmei.txt はリポジトリに同梱する。

ページ構造の実測メモ（2026-09-06 時点）:
  * 常用漢字一覧: 本表に「通用字体」「旧字体」の2列があり、各行の最初の
    wikt リンクが通用字体（first_per_row=True で抽出）。加えて、2010年
    改定で削除された5字（勺・銑・脹・匁・錘）が行番号なし（`{{0}}` に
    続く数字がない）・背景色つきの参考行として本表中に混在しており、
    これは行番号セルに数字が無いことを目印に除外する必要がある
    （`_has_row_number`）。また第1978項「猶」は
    `[[wikt:猶|<span style="...">猶</span>]]` のように表示側が
    <span> で装飾されており、表示文字がリンク先と同一かどうかだけを
    見る単純な正規表現では拾えない。
  * 人名用漢字一覧: 2026年6月26日の戸籍法施行規則別表第三改正により、
    ページが「一の表」（表外人名用漢字。634字種652字体、1字種に2字体
    ある場合は人1欄・人2欄の両方に掲げる）と「二の表」（常用漢字の
    異体字。212字体。「通用」列は常用漢字と重複するため除外し「異体」
    列のみ採用）の2表構成に変わり、期待件数は 652 + 212 = 864
    （旧来の 863 から 1 増）。一の表の最終列「備考」にはデザイン差の
    注記など無関係な wikt リンクが混入するため、各行の最終セルを
    除いてリンクを探す。また一部の行はリンク先・表示のどちらか（また
    は両方）が `&#NNNN;`（互換漢字などの数値文字参照）で書かれており、
    表示先の文字そのものではなく参照先コードポイントとして解決する
    必要がある。
    実測: 常用漢字2136字 + 人名用漢字864字（一の表652字＋二の表212字）
    を統合すると重複込みで3000字体となり、記事本文の「3000字体」の
    記述と一致する。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sources_common as sc  # noqa: E402

API = "https://ja.wikipedia.org/w/api.php"
JOYO_PAGE = "常用漢字一覧"
JINMEI_PAGE = "人名用漢字一覧"
EXPECTED_JOYO = 2136
EXPECTED_JINMEI = 864  # 2026-06-26 戸籍法施行規則別表第三改正後の件数（旧: 863）

_CJK = "一-鿿㐀-䶿豈-﫿"
_CJK_RE = re.compile("[" + _CJK + "]")
# リンク先（wikt:X）は通常1文字の漢字だが、まれに &#NNNN; の数値文字参照で
# 書かれる（戸籍統一文字の互換漢字など）。表示側（|の後）も同様に、対象と
# 同じ文字・<span>...</span> で装飾された同じ文字・数値文字参照のいずれか。
_LINK_RE = re.compile(
    r"\[\[wikt:(?:([" + _CJK + r"])|&#(\d+);)\|((?:(?!\]\]).)*)\]\]")
_SPAN_RE = re.compile(r"</?span[^>]*>")
_ENTITY_RE = re.compile(r"^&#(\d+);$")
_TEMPLATE_RE = re.compile(r"\{\{[^}]*\}\}")
_TABLE_RE = re.compile(r"\{\|.*?\n\|\}", re.S)


def _resolve_link(m):
    # type: (object) -> str or None
    target = m.group(1) if m.group(1) is not None else chr(int(m.group(2)))
    display = _SPAN_RE.sub("", m.group(3)).strip("'")
    if display == target:
        return target
    ent = _ENTITY_RE.match(display)
    if ent:
        return chr(int(ent.group(1)))
    return None


def _row_links(row):
    # type: (str) -> list
    # 最終セル（音訓・備考など）は無関係な wikt リンクを含むことがあるため
    # 除いて探す（人名用漢字一覧「一の表」の備考欄対策）。
    cells = row.split("||")
    if len(cells) > 1:
        cells = cells[:-1]
    text = "||".join(cells)
    out = []
    for m in _LINK_RE.finditer(text):
        ch = _resolve_link(m)
        if ch:
            out.append(ch)
    return out


def _has_row_number(row):
    # type: (str) -> bool
    # 行番号セルに数字があるかどうか。常用漢字一覧には削除字（勺・銑・脹・
    # 匁・錘）を示す行番号なしの参考行があり、これを除外するために使う。
    first_line = row.lstrip("\n")
    if not first_line.startswith("|"):
        parts = first_line.split("\n", 1)
        first_line = parts[1] if len(parts) > 1 else ""
    first_cell = first_line.split("||", 1)[0]
    stripped = _TEMPLATE_RE.sub("", first_cell)
    return bool(re.search(r"\d", stripped))


def extract_kanji(wikitext, first_per_row=False, last_per_row=False):
    # type: (str, bool, bool) -> list
    """表の [[wikt:X|X]] 形式の1文字リンクを出現順・重複なしで返す。

    first_per_row=True: 各表行（`|-` 区切り）の最初のリンクだけを取る
    （常用漢字表の「通用字体」列用。旧字体列を拾わない）。
    last_per_row=True: 各表行の最後のリンクだけを取る（人名用漢字一覧
    「二の表」の「異体」列用。「通用」列は常用漢字と重複するため除く）。
    """
    seen = []
    found = []
    for row in wikitext.split("\n|-"):
        links = _row_links(row)
        if not links:
            continue
        if first_per_row or last_per_row:
            if not _has_row_number(row):
                continue
            found.append(links[0] if first_per_row else links[-1])
        else:
            found.extend(links)
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
        "action": "parse", "page": title,
        "prop": "wikitext", "format": "json"})
    return json.loads(data.decode("utf-8"))["parse"]["wikitext"]["*"]


def build_joyo(fetch=None):
    # type: (object) -> list
    wikitext = fetch_page_wikitext(JOYO_PAGE, fetch=fetch)
    return extract_kanji(wikitext, first_per_row=True)


def build_jinmei(fetch=None):
    # type: (object) -> list
    wikitext = fetch_page_wikitext(JINMEI_PAGE, fetch=fetch)
    tables = _TABLE_RE.findall(wikitext)
    if len(tables) < 2:
        raise RuntimeError(
            "人名用漢字一覧のテーブル構成が想定と異なります（表が%d個）"
            % len(tables))
    # 一の表: 表外人名用漢字。1字種に2字体（人1・人2）ある場合は両方採用
    ichi = extract_kanji(tables[0], first_per_row=False)
    # 二の表: 常用漢字の異体字。「通用」列は常用漢字一覧と重複するため
    # 除外し、各行最後のリンクである「異体」列のみ採用する
    ni = extract_kanji(tables[1], last_per_row=True)
    combined = []
    for ch in ichi + ni:
        if ch not in combined:
            combined.append(ch)
    return combined


def main():
    # type: () -> int
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", default=os.path.join("qa", "kanji", "jinmei.txt"))
    args = parser.parse_args()

    joyo = build_joyo()
    print("%s: %d 字（期待 %d）" % (JOYO_PAGE, len(joyo), EXPECTED_JOYO))
    if len(joyo) != EXPECTED_JOYO:
        print("エラー: 期待件数と一致しません。ページ構造の変化を確認してください。")
        return 1

    jinmei = build_jinmei()
    print("%s: %d 字（期待 %d）" % (JINMEI_PAGE, len(jinmei), EXPECTED_JINMEI))
    if len(jinmei) != EXPECTED_JINMEI:
        print("エラー: 期待件数と一致しません。ページ構造の変化を確認してください。")
        return 1

    uniq = sorted(set(joyo) | set(jinmei))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(uniq) + "\n")
    print("書き込み: %s（%d 字）" % (args.out, len(uniq)))
    return 0


if __name__ == "__main__":
    sc.force_utf8_output()
    sys.exit(main())
