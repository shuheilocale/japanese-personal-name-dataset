# 多フォーマット配布と生年代メタデータ 設計

対象 Issue: #3（JSON 化）、#15（多フォーマットとビルド）、#10（データ拡充）、#16（時系列メタデータ）。
決定日: 2026-10-24（ユーザー承認: JSON+SQLite をリリース添付 / 生年代は NDL・Wikidata の生年から推定）。

## 1. 方針

- **正本は CSV のまま。** `japanese_personal_name_dataset/dataset/*.csv` と `load_dataset()` は変更しない（後方互換）。
- **派生形式はビルドで生成し、GitHub Releases に添付する。** PyPI パッケージには同梱しない（wheel を軽く保つ）。
- 形式は標準ライブラリだけで生成できる **JSON と SQLite**。YAML・Parquet・MessagePack は需要が出たら追加する。
- **年代情報はランキングではなく「その名を持つ人物の生年の分布」。** 出典は NDL 典拠（「姓, 名, 生年-没年」）と Wikidata（P735 名 + P569 生年月日）。著者・著名人に偏るため、赤ちゃん名ランキングとは性質が違うことを明記する。

## 2. 生年代メタデータ

### 2.1 取得

- `sources_common.record()` に任意項目 `birth_year`（int または None）を追加する。既存の読み手は無視できる。
- `fetch_ndl.py`: ラベルの 3 番目の要素の先頭 4 桁（`1950-2010` → 1950、`1950-` → 1950、`生没年不詳` → None）を `birth_year` に入れる。範囲は 1800〜今年。
- `fetch_wikidata.py`: 名ごとの人物数に加え、人物ごとの生年を返すクエリを追加する（日本国籍 Q17、P735 の名項目、P569 の年）。

### 2.2 集計

`.claude/skills/qa-update/scripts/build_birth_decades.py`

- 入力: 正規化 JSONL（NDL・Wikidata）と現行の dataset CSV。
- 対象: 現行データにある (ファイル, 読み, 漢字) と (ファイル, 読み)。名ファイルは男性・女性を区別して、データセットに載っている読みだけを数える（性別は推定しない）。
- 出力: `qa/metadata/birth_decades.csv`（追跡対象、再現用）

  `kind,reading,kanji,decade,count` — `kind` は `given` / `surname`、`kanji` が空なら読み単位の集計、`decade` は 1900 のような 10 年刻み。
- 人数が 3 人未満の (読み/表記, 年代) は出さない（個人の特定を避け、ノイズを減らす）。

## 3. ビルド

`scripts/build_formats.py`（標準ライブラリのみ、`python scripts/build_formats.py --out build/`）

- `japanese_names.json`

  ```json
  {"version": "0.4.0", "generated_at": "2026-...",
   "sources": {...},
   "first_names": {"male": [{"reading": "あい", "romaji": "ai", "kanji": ["藍"], "popular": false,
                              "birth_decades": {"1950": 12}}],
                   "female": [...]},
   "last_names": [{"kanji": "佐藤", "reading": "さとう", "romaji": "satou", "count": 1887000,
                   "birth_decades": {...}}]}
  ```

  `popular` は opti ファイルにあるかどうか。`birth_decades` は集計がある場合のみ。
- `japanese_names.sqlite`: テーブル `first_names(id, gender, reading, romaji, popular)`、`first_name_kanji(first_name_id, position, kanji)`、`last_names(kanji, reading, romaji, count)`、`birth_decades(kind, gender, reading, kanji, decade, count)`、`metadata(key, value)`。
- 検証: 生成物を読み戻して CSV と件数・内容が一致することを確認し、不一致なら終了コード 1。
- 統計: 形式ごとのファイルサイズと件数を表示する。

## 4. リリース

`publish.yml` に別ジョブ `release-assets`（`permissions: contents: write`、`release` イベントのときのみ）を追加し、ビルドして `gh release upload` で添付する。PyPI 公開ジョブ（`id-token: write`）とは権限を分ける。

## 5. テスト

- ビルド: 小さなフィクスチャ CSV から JSON / SQLite を作り、内容と読み戻し検証を確認する。実データでも件数一致を確認する。
- 生年: ラベルからの生年抽出（範囲外・不詳・没年のみ）、集計の閾値と年代の丸め。
