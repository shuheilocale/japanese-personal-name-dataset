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
<entry><ent_seq>5</ent_seq><k_ele><keb>薫子</keb></k_ele><r_ele><reb>かおるこ</reb></r_ele>
<trans><name_type>&fem;</name_type></trans></entry>
</JMnedict>
"""


def test_entries_and_records():
    entries = list(fj.iter_entries(io.BytesIO(XML.encode("utf-8"))))
    assert len(entries) == 5
    recs = fj.entries_to_records(entries)
    assert {"source": "jmnedict", "kind": "given", "kanji": "漱石", "reading": "そうせき",
            "gender": "male", "count": 1} in recs
    assert {"source": "jmnedict", "kind": "surname", "kanji": "夏目", "reading": "なつめ",
            "gender": None, "count": 1} in recs
    kaoru = [r for r in recs if r["kanji"] == "薫"]
    assert kaoru and kaoru[0]["gender"] == "unisex"
    kaoru_ko = [r for r in recs if r["kanji"] == "薫子"]
    assert kaoru_ko and kaoru_ko[0]["gender"] == "female"
    assert not [r for r in recs if r["kanji"] == "東京"]
