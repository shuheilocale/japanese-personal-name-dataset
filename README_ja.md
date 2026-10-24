# Japanese Personal Name Dataset（日本人の姓名データセット）

[![Tests](https://github.com/shuheilocale/japanese-personal-name-dataset/actions/workflows/test.yml/badge.svg)](https://github.com/shuheilocale/japanese-personal-name-dataset/actions/workflows/test.yml)
[![PyPI version](https://badge.fury.io/py/japanese-personal-name-dataset.svg)](https://badge.fury.io/py/japanese-personal-name-dataset)
[![Python Versions](https://img.shields.io/pypi/pyversions/japanese-personal-name-dataset.svg)](https://pypi.org/project/japanese-personal-name-dataset/)
[![codecov](https://codecov.io/gh/shuheilocale/japanese-personal-name-dataset/branch/main/graph/badge.svg)](https://codecov.io/gh/shuheilocale/japanese-personal-name-dataset)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

[English](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/README.md) | **日本語**

日本人の名（男性・女性）と姓のデータセットです。ひらがなの読み、ローマ字（ヘボン式）、漢字表記を収録し、依存ライブラリなしで使える Python API を同梱しています。

```python
>>> from japanese_personal_name_dataset import load_dataset
>>> man_names, woman_names = load_dataset()
>>> man_names['たろう']
{'en': 'tarou', 'kanji': ['多朗', '多郎', '太朗', '太郎', '大郎']}
```

## 目次

- [特徴](#特徴)
- [インストール](#インストール)
- [使い方](#使い方)
- [API 一覧](#api-一覧)
- [データ仕様](#データ仕様)
- [データの出典と品質](#データの出典と品質)
- [サンプルコード](#サンプルコード)
- [コントリビュート](#コントリビュート)
- [ライセンス](#ライセンス)

## 特徴

- 男性の名 **6,120 読み**・女性の名 **3,343 読み**。読みごとに知られている漢字表記をすべて収録
- 推定人数つきの姓 **1,999 種類**
- 有名な名前だけを抜粋した「最適化版」（男性 702 / 女性 241）
- ローマ字はヘボン式
- 純粋な Python、実行時依存なし、Python 3.8 以上
- 型ヒント完備（`py.typed` 同梱）。初回読み込み後はキャッシュされる

## インストール

```bash
pip install japanese-personal-name-dataset
```

## 使い方

### データを読み込む

```python
from japanese_personal_name_dataset import load_dataset

# 完全版（デフォルト）
man_names, woman_names = load_dataset()
print(woman_names['はなこ']['kanji'][:4])   # ['羽奈子', '羽那子', '英子', '花菜子']

# 最適化版（有名な名前のみ）
man_opti, woman_opti = load_dataset(kind='opti')
print(len(man_opti), len(woman_opti))      # 702 241

# 姓も読み込む
man_names, woman_names, last_names = load_dataset(include_last_names=True)
print(last_names['佐藤'])
# {'reading': 'さとう', 'en': 'satou', 'count': 1887000}
```

### ランダムな名前を生成する

```python
from japanese_personal_name_dataset import generate_random_name, generate_random_full_name

generate_random_name(gender='male')                       # 例: '健一'
generate_random_full_name(gender='female', return_reading=True)
# 例: ('川瀬 梅乃', 'かわせ うめの')
```

### 検索とチェック

```python
from japanese_personal_name_dataset import (
    search_by_reading, search_by_kanji, get_last_names, is_valid_name,
)

# 読みはひらがなで指定する。partial=True で部分一致
for r in search_by_reading('こう', partial=True, gender='male')[:3]:
    print(r['reading'], r['romaji'], r['kanji'][:3])
# いっこう ikkou ['一興', '一光', '一公'] ...

search_by_kanji('翔', partial=True, gender='male')       # 「翔」を含む名前

for name in get_last_names(limit=3):                       # 人数の多い姓
    print(name['kanji'], name['reading'], f"{name['count']:,}")
# 佐藤 さとう 1,887,000 / 鈴木 すずき 1,806,000 / 高橋 たかはし 1,421,000

is_valid_name('太郎', 'たろう')                            # True
```

## API 一覧

| 関数 | 内容 |
| --- | --- |
| `load_dataset(kind='org', include_last_names=False)` | `(男性, 女性)` または `(男性, 女性, 姓)` の辞書を返す |
| `generate_random_name(gender, kind, return_reading)` | ランダムな名 |
| `generate_random_full_name(gender, kind, return_reading)` | ランダムな「姓 名」 |
| `search_by_reading(reading, gender, kind, partial)` | ひらがなの読みで名を検索 |
| `search_by_kanji(kanji, gender, kind, partial)` | 漢字で名を検索 |
| `search_last_name(query, search_by='kanji', partial, limit)` | 漢字または読みで姓を検索 |
| `get_last_names(limit, min_count)` | 推定人数の多い順に姓を取得 |
| `get_popular_names(gender, top=50)` | 最適化版から名を取得 |
| `is_valid_name(kanji, reading, gender, kind)` | 漢字と読みの組み合わせが存在するか |
| `get_readings_for_kanji(kanji, gender, kind)` | 漢字表記に対応する読みの一覧 |
| `clear_cache()` | キャッシュを破棄し、次回 CSV を読み直す |

型チェッカー向けに戻り値の型 `FirstNameEntry` / `LastNameEntry` / `NameDict` / `LastNameDict` を公開しています。`load_dataset(include_last_names=True)` は 3 要素のタプルとして型付けされます。

`load_dataset()` は CSV をプロセスにつき 1 回だけ読み、呼び出すたびに新しい辞書を返します。結果を書き換えても次回の結果には影響しません。

## データ仕様

CSV は `japanese_personal_name_dataset/dataset/` にあります（UTF-8、改行 LF）。

| ファイル | 内容 | 行数 |
| --- | --- | --- |
| `first_name_man_org.csv` | 男性の名 | 6,120 |
| `first_name_man_opti.csv` | 男性の名（最適化版） | 702 |
| `first_name_woman_org.csv` | 女性の名 | 3,343 |
| `first_name_woman_opti.csv` | 女性の名（最適化版） | 241 |
| `last_name_org.csv` | 姓 | 1,999 |

### 名

`ひらがな,ローマ字,漢字1,漢字2,...`。1 行が 1 つの読みで、漢字列の数は可変です。

```csv
あい,ai,藍,愛,亜衣
```

### 姓

`漢字,推定人数,ひらがな,ローマ字`

```csv
佐藤,1887000,さとう,satou
```

### 読みあたりの漢字表記の数

| ファイル | 平均 | 中央値 | 最大 |
| --- | --- | --- | --- |
| 男性（完全版） | 9 | 2 | 446 |
| 男性（最適化版） | 45 | 26 | 446 |
| 女性（完全版） | 11 | 2 | 394 |
| 女性（最適化版） | 50 | 32 | 287 |

## データの出典と品質

- 姓の推定人数は [名字由来net](https://myoji-yurai.net/prefectureRanking.htm) を参考にしています。
- v0.3.0 から、名は [Wikidata](https://www.wikidata.org/)（CC0）と [国立国会図書館 Web NDL Authorities](https://id.ndl.go.jp/auth/ndla/) で照合・拡充しています。[JMnedict](https://www.edrdg.org/enamdict/enamdict_doc.html) は照合にのみ使い、再配布はしていません。
- 変更はすべて、決定的なチェック（形式・重複・読みとローマ字の整合）と、[`qa/`](https://github.com/shuheilocale/japanese-personal-name-dataset/tree/main/qa/) 以下の疑義台帳でのレビューを経ます。雅号・法名・称号らしい候補は除外しています。

ローマ字はヘボン式です。長音はかなの通り（`ou`・`oo`）に書き、省略形もチェック上は許容しています。

データは現状のまま提供します。読み・ローマ字・表記の誤りを見つけたら [Issue](https://github.com/shuheilocale/japanese-personal-name-dataset/issues/new/choose) でお知らせください。

## サンプルコード

[`examples/`](https://github.com/shuheilocale/japanese-personal-name-dataset/tree/main/examples/) に実行できるスクリプトがあります。

| スクリプト | 内容 |
| --- | --- |
| [`basic_usage.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/basic_usage.py) | 読み込み・参照・ヘルパー関数の基本 |
| [`generate_test_users.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/generate_test_users.py) | テストやシード用のダミーユーザーを CSV / JSON で生成 |
| [`form_validation.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/form_validation.py) | 会員登録フォームの氏名チェックと読みの候補提示 |
| [`name_statistics.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/name_statistics.py) | よく使われる漢字や男女共通の読みなどの簡単な分析 |
| [`web_api.py`](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/examples/web_api.py) | 標準ライブラリだけで作る小さな JSON API |

主な用途: Web アプリのテストデータ・シードデータ、入力チェック、日本語学習ツール、ゲーム、データ分析。

## コントリビュート

Issue や Pull Request を歓迎します。開発環境の用意やデータ修正のレビュー方法は [CONTRIBUTING.md](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/CONTRIBUTING.md) を参照してください。

## ライセンス

MIT License。[LICENSE](https://github.com/shuheilocale/japanese-personal-name-dataset/blob/main/LICENSE) を参照してください。
