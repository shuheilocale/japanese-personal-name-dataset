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



## 使用例

```python
from japanese_personal_name_dataset import load_dataset

# データセットを読み込む
man_names, woman_names = load_dataset()

# 男性の名前を確認
print(man_names['たろう'])
# {'en': 'tarou', 'kanji': ['太郎', '太朗', '大郎', ...]}

# 女性の名前を確認
print(woman_names['はなこ'])
# {'en': 'hanako', 'kanji': ['花子', '華子', ...]}

# ランダムな名前を取得
import random
random_reading = random.choice(list(man_names.keys()))
print(f"{random_reading}: {man_names[random_reading]}")
```

## 参考
- [名字由来net](https://myoji-yurai.net/prefectureRanking.htm)
