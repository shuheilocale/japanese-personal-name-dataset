# Japanese Personal Name Dataset

日本人の姓名データセット

[English README](README_EN.md)


## データ仕様
データセットは以下にて構成されています。

1. 男性の名 ・・・ first_name_man_org.csv
2. 男性の名（最適化） ・・・ first_name_man_opti.csv
3. 女性の名 ・・・ first_name_woman_org.csv
4. 女性の名（最適化） ・・・ first_name_woman_opti.csv
5. 姓 ・・・ last_name_org.csv

* 最適化とは、独断で有名な名前のみを抜粋したものです。 <br>
*  各ファイルはCSV形式、文字コードUTF-8、改行コードLFとなります。

## CSVフォーマット

### 名

一行につき、一つの名です。 <br>
各列は、 <br>
1列目：ひらがな <br> 
2列目：ローマ字 <br>
3列目～：漢字 <br>
となります。 <br>
漢字列については、各名前で可変です。

### 姓

一行につき、一つの姓です。 <br>
各列は、 <br>

1列目：漢字 <br>
2列目：推定人数 <br>
3列目：ひらがな <br>
4列目：ローマ字 <br>
となります。


ローマ字はヘボン式です（確認はしていますが、ミスがある可能性もあります）。

## データ数

姓名の種類は下記の通りです。 <br>

1. 男性の名 ・・・ 5,678種類
2. 男性の名（最適化） ・・・ 703種類
3. 女性の名 ・・・ 3,346種類
4. 女性の名（最適化） ・・・ 241種類
5. 姓 ・・・ 2,000種類

また、漢字の種類の平均、標準偏差、中央値、最頻値、最大値、最小値はそれぞれ下記の通りです。

1. 男性の名 ・・・10、26、2、1、447、1
2. 男性の名（最適化） ・・・ 45、59、27、4、447、1
3. 女性の名 ・・・ 11、26、2、1、398、1
4. 女性の名（最適化） ・・・ 51、55、32、2、291、1



## インストール

```bash
pip install japanese-personal-name-dataset
```

## 使用例

### 基本的な使い方

```python
from japanese_personal_name_dataset import load_dataset

# データセットを読み込む（デフォルト：完全版）
man_names, woman_names = load_dataset()

# 男性の名前を確認
print(man_names['たろう'])
# {'en': 'tarou', 'kanji': ['多朗', '多郎', '太朗', '太郎', '大郎']}

# 女性の名前を確認
print(woman_names['はなこ'])
# {'en': 'hanako', 'kanji': ['花子', '華子', ...]}
```

### 最適化版（人気の名前のみ）を使う

```python
# 人気の名前のみを読み込む
man_names, woman_names = load_dataset(kind='opti')
print(f"男性の名前: {len(man_names)}種類")  # 703種類
print(f"女性の名前: {len(woman_names)}種類")  # 241種類
```

### 姓データも読み込む

```python
# 姓データも含めて読み込む
man_names, woman_names, last_names = load_dataset(include_last_names=True)

# 姓の情報を確認
print(last_names['佐藤'])
# {'reading': 'さとう', 'en': 'satou', 'count': 1887000}
```

### ユーティリティ関数を使う

```python
from japanese_personal_name_dataset import (
    generate_random_name,
    generate_random_full_name,
    search_by_reading,
    search_by_kanji,
    get_last_names,
    is_valid_name,
)

# ランダムな名前を生成
name = generate_random_name(gender='male')
print(name)  # 例: 太郎

# ランダムなフルネームを生成（読み仮名付き）
full_name, reading = generate_random_full_name(gender='female', return_reading=True)
print(f"{full_name} ({reading})")  # 例: 佐藤 花子 (さとう はなこ)

# 読み仮名で検索（部分一致）
results = search_by_reading('こう', partial=True, gender='male')
for r in results[:3]:
    print(f"{r['reading']} ({r['romaji']}): {', '.join(r['kanji'][:3])}")
# 例: こうじ (kouji): 浩二, 孝二, 幸治

# 漢字で検索（「子」を含む名前）
results = search_by_kanji('子', partial=True, gender='female')
print(f"「子」を含む名前: {len(results)}件")

# 人気の姓トップ10
top_10 = get_last_names(limit=10)
for i, name in enumerate(top_10, 1):
    print(f"{i}. {name['kanji']} ({name['reading']}) - {name['count']:,}人")

# 名前の妥当性チェック
if is_valid_name('太郎', 'たろう'):
    print("太郎（たろう）は正しい組み合わせです")
```

## 参考
- [名字由来net](https://myoji-yurai.net/prefectureRanking.htm)
