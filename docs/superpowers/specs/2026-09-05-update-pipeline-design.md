# 自動更新パイプライン（Phase 2）設計書

- 作成日: 2026-09-05
- ステータス: レビュー待ち
- 前提: Phase 1（QA基盤: `2026-07-27-qa-foundation-design.md`）とトリアージ UI（`2026-08-30-qa-triage-ui-design.md`）が稼働済み

## 1. 目的と方針

OSS支援申請書の柱「権威あるソースから取得し、漢字⇔読みを照合・重複除去して検証済みの年次リリースを出す」を実現する。Phase 1 の台帳（findings）・トリアージ UI・適用スクリプトをそのまま導線として再利用し、更新作業を「取得 → 候補生成 → 採否判断 → 適用 → リリース」の年次サイクルにする。

決定事項（brainstorming で確定）:

- **ライセンス方針**: 取り込み源は MIT 配布と互換なものだけ — **Wikidata（CC0）** と **国立国会図書館典拠データ（自由利用）**。**JMnedict（CC BY-SA 3.0）は照合（存在確認）専用**でデータには取り込まない。明治安田生命・たまひよ等のランキングサイトはスクレイピングしない（Phase 3 の人気度指標で別途検討）。
- **対象**: 新規追加は男性名・女性名のみ。姓は既存 1,999 件の読みの照合だけ行い、追加しない（推定人数の無償ソースが無く、ファイルの意味が崩れるため）。
- **実行形態**: 手動起動のスキル `/qa-update`（ローカル）。CI には載せない。
- **アプローチ**: findings 拡張型。候補は `add_row` / `add_kanji` アクションの findings として台帳に入れ、根拠が閾値以上のものは事前承認（approved）、それ以外は pending でトリアージ UI に出す。

## 2. ソース調査結果（2026-09-05 時点）

| ソース | 規模 | 取得手段 | 得られるもの |
| --- | --- | --- | --- |
| Wikidata | 日本語の名 約4,200項目（男 3,109 / 女 772 / 中性 297） | SPARQL（`P31`=男性名/女性名/中性名, `P407`=日本語, `P1814`=仮名表記） | 漢字＋読み＋性別クラス＋その名を持つ人物数（`P735` 参照数） |
| NDL 典拠 | 人名 1,761,192 件（読み付き） | SPARQL `https://id.ndl.go.jp/auth/ndla/sparql`（skos-xl: `literalForm`＝「姓, 名, 生没年」、`ndl:transcription`＝カタカナ読み／ローマ字転写）。一括ダウンロードファイルが使えれば優先 | 実在人物の姓・名（漢字＋カタカナ読み）を人物数付きで集計可能 |
| JMnedict | 固有名詞 約74万件（`JMnedict.xml.gz` 12.4MB） | ダウンロード | `name_type`（masc/fem/given/surname）付きの漢字＋読み。照合専用 |
| 常用漢字・人名用漢字 | 2,136 + 864 字（2026-06-26 の戸籍法施行規則改正で 863 字から 864 字に変更） | 公的リストの文字集合をリポジトリに同梱（`qa/kanji/jinmei.txt`） | 候補の除外ルール（戸籍で使えない字を含む表記は候補化しない） |

## 3. 構成

```text
.claude/skills/qa-update/
├── SKILL.md                    # /qa-update の年次運用手順
└── scripts/
    ├── fetch_wikidata.py       # SPARQL → qa/sources/wikidata-<date>.jsonl
    ├── fetch_ndl.py            # SPARQL を典拠 ID 接頭辞で適応分割（1,000 行上限到達で1桁深く再分割、done/split/saturated を manifest に記録、再開可）→ qa/sources/ndl-<date>.jsonl
    ├── fetch_jmnedict.py       # xml.gz → qa/sources/jmnedict-<date>.jsonl
    ├── source_index.py         # 統一索引の構築
    └── generate_candidates.py  # 現データとの差分 → findings（add_row / add_kanji / 姓の照合）
qa/sources/                     # 取得スナップショット（.gitignore。manifest.json だけ追跡）
qa/kanji/jinmei.txt             # 常用漢字＋人名用漢字の文字集合
```

### 3.1 正規化レコード（全ソース共通・JSONL 1行1件）

```json
{"source": "ndl", "kind": "given", "kanji": "漱石", "reading": "そうせき", "gender": null, "count": 12}
```

- `kind`: `given` | `surname`。`gender`: `male` | `female` | `unisex` | `null`。`count`: そのソースで当該 (漢字, 読み) を持つ人物数（Wikidata は `P735`/`P734` の参照数、項目が存在すれば最低 1）
- NDL: `literalForm` を `, ` で分割し [姓, 名, 生没年] とする。カタカナ読みをひらがなに変換。名が取れない・カタカナ表記の姓名（外国人）・中黒/欧字を含むものは除外
- Wikidata: ja ラベル、`P1814`（ひらがな/カタカナ→ひらがな統一）、クラスを gender に
- JMnedict: `keb`/`reb`、`name_type` を gender/kind に。索引には真偽（存在）だけを持たせる

### 3.2 統一索引

`(kind, kanji, reading)` → `{"ndl": n, "wikidata": n, "jmnedict": true|false, "gender": {"wikidata": "male", "jmnedict": "masc"}}`。スナップショットからオフラインで再構築できる（再現性）。

## 4. 候補生成ポリシー（決定的）

- **add_kanji**（既存読みへの新しい漢字表記）: 索引にあって現データに無い (漢字, 読み)。候補化は `ndl >= 2` または `wikidata >= 1`。事前承認（`status: approved`）は `ndl >= 5` かつ `wikidata >= 1`。閾値は CLI 引数 `--min-ndl 2 --auto-ndl 5` で調整可。
  追加先はその読みが存在するファイル（男女両方にあれば両方）。Wikidata の性別クラスが追加先と矛盾する場合（例: 女性名クラスの表記を男性名ファイルの読みに追加）は候補化するが事前承認はしない（evidence に矛盾を明記）。
- **add_row**（現データに無い読み）: 性別は Wikidata のクラスから決定（`unisex` は両ファイルに追加）。NDL にしかない読みは LLM 判定バッチ（qa-review と同じサブエージェント方式、出力は `male|female|unisex|unknown`）で性別を付け、`unknown` は pending のまま UI で手動決定。事前承認は性別が Wikidata 由来の場合のみ。ローマ字は `romaji.py` のかな通り表記で生成。追加先は `*_org.csv` のみ。
- **除外ルール**: `qa/kanji/jinmei.txt` に無い字を含む表記は候補化しない。
- **姓の照合**: 現 1,999 姓について、索引に同じ漢字の姓があり、現データの読みが索引のどの読みとも一致しない場合のみ `kanji_reading_mismatch`（`fix_reading` 提案＝索引で最多の読み、`confidence: medium`）。
- **名の既存エントリ**: 索引での裏付け（人物数）を UI シグナル `source_support` として表示するだけで findings は出さない（未収載 ≠ 誤り）。
- 1回の実行で出す候補は根拠（`ndl + wikidata`）の降順で `--max-candidates 2000` 件まで。残りは次回。
- 出力先: `qa/findings/<YYYY-MM>-update.jsonl`（`detected_by: "qa-update v1"`）。同一 run-id で再実行した場合は既存 status を引き継ぐ（qa_batch の merge と同じキー規則）。

## 5. スキーマ拡張（Phase 1 設計書 §5 の安定契約への追加）

- `check` に `missing_entry` を追加
- `proposed_fix.action` に `add_row`（`entry` = 追加する完全な行 `読み,ローマ字,漢字,...`、`value` = 空）と `add_kanji`（`entry` = 既存行、`value` = 追加する漢字。複数はカンマ区切り）を追加
- 任意フィールド `sources: {"ndl": n, "wikidata": n, "jmnedict": bool}` を追加（`validate_finding` は存在すれば型を検証）
- `entry` の意味: add_row のみ「追加する行」。他は従来どおり「対象の既存行」

## 6. 既存コンポーネントの改修

- `apply_findings.py`: `add_row` は読み順で挿入（同じ読みの行が既にあれば `add_kanji` 相当で統合）。`add_kanji` は末尾追加（重複除去）。dry-run の表示に追加行を明記
- `triage_server.py` / `triage_ui.html`: `add_*` は `entry_stale` / `value_not_in_row` の対象外。`source_support` シグナル（NDL n / Wikidata m / JMnedict ✓）を全 finding に表示（索引スナップショットがある場合のみ）
- `rebase_findings.py`: `add_*` は対象外
- `findings_io.py`: 上記スキーマ拡張

## 7. エラー処理と運用

- 取得は 3 回リトライ（指数バックオフ）。失敗時は前回スナップショットでの続行を提案する。NDL の SPARQL は 1 クエリ 1,000 行で打ち切るため、典拠 ID の接頭辞で適応分割して取得する（上限到達時は接頭辞を 1 桁深く再分割、各 leaf の結果と manifest を都度保存して中断再開可。176万件で約 2,000 リクエスト以上、1 秒スリープで 40〜90 分の見込み）。max_depth でも上限に達した接頭辞は saturated として警告し exit 1
- 全スクリプトで User-Agent（リポジトリ URL 入り）を明示
- 年次運用手順（SKILL.md）: 取得 → 索引 → 候補生成 → 性別判定バッチ → トリアージ UI → `/qa-apply` → validate/pytest/件数同期 → `/release`

## 8. テスト

- 正規化: NDL ラベル分割・生没年除去・外国人名除外・カタカナ→ひらがな、Wikidata の仮名統一、JMnedict の name_type 対応
- 索引: 集計と gender 集約
- 候補生成: 閾値の境界、事前承認条件、unisex の両ファイル追加、除外ルール、上限件数、姓の照合、既存 status の引き継ぎ
- apply: add_row の読み順挿入と同読み統合、add_kanji の重複除去
- UI: `source_support` の表示と add_* のシグナル除外
- ネットワークは固定 JSON/XML フィクスチャで代替し、実取得は手動スモークで確認

## 9. Phase 2 完了の定義

1. `/qa-update` で取得 → 索引 → 候補台帳が実データで生成できる
2. 候補がトリアージ UI で判断でき、`/qa-apply` が `add_row` / `add_kanji` を適用できる
3. 初回の更新分を v0.3.0 としてリリースする（README・CLAUDE.md・テストの件数同期を含む）
4. `qa-update` の SKILL.md、CLAUDE.md、本設計書が実装と一致している
