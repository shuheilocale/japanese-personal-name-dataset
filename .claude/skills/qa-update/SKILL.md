---
name: qa-update
description: Use when データセットを外部ソース（Wikidata・NDL典拠）から年次更新するとき、新しい名の候補を生成するとき、または「データ更新」「候補生成」「qa-update」を求められたとき。取り込み源は MIT 互換ソースのみ。
---

# データセット年次更新（/qa-update）

Wikidata（CC0）と国立国会図書館典拠（自由利用）から名の候補を生成し、Phase 1 の
台帳 → トリアージ UI → /qa-apply の導線で適用する。JMnedict（CC BY-SA）は照合専用
（索引の ✓ 表示のみに使い、漢字・読みそのものを候補や evidence に転記しない）。
ランキングサイトはスクレイピングしない。

## 実行手順

1. run-id を決める（例: `2026-09-update`）。`git status` がクリーンであること。

2. 取得。`qa/sources/*` は manifest.json 以外 `.gitignore` 済み（再取得できるスナップショットのため追跡しない）:

   ```bash
   S=.claude/skills/qa-update/scripts
   python3 $S/fetch_wikidata.py --out qa/sources/wikidata-<date>.jsonl
   python3 $S/fetch_ndl.py --out qa/sources/ndl-<date>.jsonl --work qa/sources/ndl-work
   python3 $S/fetch_jmnedict.py --out qa/sources/jmnedict-<date>.jsonl
   ```

   - `fetch_ndl.py` は典拠 ID の接頭辞ごとに `--work`（既定 `qa/sources/ndl-work`）
     に結果と `manifest.json`（done/split/saturated）を保存する。初回は約 14 時間かかる
     （2026-09 実測: 接頭辞 9,973 件・分割 997 件・生データ約 149 万行 → 集約 209,511 件）。
     `nohup python3 $S/fetch_ndl.py ... > ndl.log 2>&1 &` で切り離し、`manifest.json` の
     `done` 件数で進捗を見るとよい（stdout はブロックバッファされるためログは遅れる）。中断してもそのまま同じコマンドを再実行すれば `done`/`split` 済みの
     接頭辞をスキップして再開する。
   - 終了コード 1（`saturated` あり）が出た場合はデータ欠損の可能性がある。
     `qa/sources/ndl-work/manifest.json` から該当接頭辞を `done` と `saturated` の
     両方から手で取り除き、`--max-depth`（既定 9）を増やして再実行する
     （`--work` を消すと全接頭辞が再取得になるため、対象接頭辞だけを外すこと）。
   - 取得失敗時（3 回リトライ後も `RuntimeError: 取得に失敗しました` で止まる、または
     エンドポイント停止）は、前回のスナップショットで続行してよい。`qa/sources/manifest.json`
     に記録されている前回の `<date>` のファイル（`qa/sources/wikidata-<date>.jsonl` 等。
     `.gitignore` 対象なのでローカルに残っているもの）をそのまま手順3の `--sources` に渡し、
     manifest.json の該当ソースは前回の `fetched_at`/件数を据え置く（そのソースだけ更新
     しなかったことを手順末尾のコミットメッセージに書く）。ローカルに前回分が無い場合は
     取得できるようになるまで待つ（ソースを欠いたまま索引を作ると、そのソースの裏付けが
     0 になり姓の照合や事前承認の判定が変わる）。

3. 索引:

   ```bash
   python3 $S/source_index.py \
     --sources qa/sources/wikidata-<date>.jsonl qa/sources/ndl-<date>.jsonl qa/sources/jmnedict-<date>.jsonl \
     --out qa/sources/index.json
   ```

   `qa/sources/manifest.json` に取得日とレコード数を記録してコミットする（スナップショット本体は
   追跡しない）。形式は次のとおり（手書きでよい。`records` は各 JSONL の行数、`prefix_len` は
   `fetch_ndl.py --prefix-len`、`version` は JMnedict.xml の日付など）:

   ```json
   {"fetched_at": "YYYY-MM-DD",
    "wikidata": {"records": N},
    "ndl": {"records": N, "prefix_len": 3},
    "jmnedict": {"records": N, "version": "..."}}
   ```

4. 候補生成:

   ```bash
   python3 $S/generate_candidates.py --index qa/sources/index.json \
     --dataset-dir japanese_personal_name_dataset/dataset \
     --out qa/findings/<run-id>.jsonl --gender-pending qa/work/<run-id>/gender_pending.json
   ```

   既存読みへの `add_kanji` と新規読みの `add_row` が status=pending/approved で
   `qa/findings/<run-id>.jsonl` に、性別を索引・現データのどちらからも判定できない
   新規読みが `qa/work/<run-id>/gender_pending.json` に出力される。候補の上限
   （既定 2000 件、`--max-candidates`）を超えた分は次回に回る。閾値は `--min-ndl`
   （既定 2）/ `--auto-ndl`（既定 5、自動承認しきい値）で調整する。
   `--out` が既にある場合の再実行は、自分が生成した pending（`detected_by: "qa-update v1"`）
   以外の既存 finding — 手順5の性別バッチ由来（`detected_by: "qa-update/gender_batch v1"`）の
   add_row や rejected/applied 済みのもの — をそのまま保持し、id・entry・action・value が
   完全一致する finding は status を引き継ぐ（内容が変わったものは pending に戻し evidence に注記。
   add_kanji は追加先の行が変わっただけでは内容変更とみなさない）。事前承認済み（approved）
   だったが今回の生成で候補外になったもの（索引更新・閾値変更・上限外れ）は根拠が消えているので
   pending に戻し evidence に「（今回の生成では候補外のため再判断）」を付記する（UI で判断するまで残る）。
   この注記付きのものを UI で再承認した場合は人の判断として尊重し、以後の再実行でも approved のまま
   保持する（候補に戻って通常生成されれば approved を引き継ぎ evidence は新しいものに置き換わる）。

5. 性別判定（`gender_pending.json` が空でない場合）:

   ```bash
   python3 $S/gender_batch.py prep --pending qa/work/<run-id>/gender_pending.json \
     --out-dir qa/work/<run-id>/gender
   ```

   → `qa/work/<run-id>/gender/manifest.json` の `batch_ids` ごとに、下のプロンプトで
   サブエージェント（general-purpose）を起動し `qa/work/<run-id>/gender/results/` に
   書かせる（同時 4 つまで）。全バッチが揃ったらマージする:

   ```bash
   python3 $S/gender_batch.py merge --out-dir qa/work/<run-id>/gender \
     --findings qa/findings/<run-id>.jsonl
   ```

   `male`/`female`/`unisex` の読みは対応する名ファイルへの `add_row` findings
   （status=pending、evidence に「性別: LLM 判定」を付記）として追加される。
   `unknown` は追加されない。未処理・不正バッチが報告されたら、そのバッチだけ
   手順5をやり直して再マージする（同 id の finding は重複追加されない）。

5.5. 以前の判断の引き継ぎ（手順5のマージ後、判断の前）:

   ```bash
   python3 $S/prior_decisions.py --findings qa/findings/<run-id>.jsonl \
     --previous qa/findings/*-update.jsonl
   ```

   以前の更新ラウンドで却下した候補・行追加時に表記を絞って外した表記・表記の性別クラスが
   追加先と矛盾する add_kanji を決定的に却下する（2026-11 では 16,594 候補のうち 1,991 件）。
   以前の判断を引き継ぐので、毎回レビューに回るのは新しく現れた候補だけになる。

6. 判断（トリアージ UI）:

   ```bash
   python3 .claude/skills/qa-apply/scripts/triage_server.py \
     --findings qa/findings/<run-id>.jsonl \
     --dataset-dir japanese_personal_name_dataset/dataset \
     --source-index qa/sources/index.json
   ```

   `--source-index` を渡すと、finding ごとに根拠シグナル `source_support`
   （NDL n人 / Wikidata m人 / JMnedict ✓）が表示に加わる（`add_row` / `add_kanji` は
   finding の `sources` を、それ以外は索引を引く）。`add_*` は追加候補なので
   `entry_stale` / `value_not_in_row` / 別読み行の既存漢字（`dup_elsewhere`）は出ない
   （これらは remove_kanji 等の既存行向けシグナル）。事前承認済み（approved）は
   dry-run で内訳を確認するだけでよい。

   件数が多くてサブエージェントにレビューさせた場合も、承認・却下は台帳の status に書き、
   根拠（却下理由・表記の絞り込み）は evidence に追記する（`(却下: …)` / `(レビューで表記を絞り込み: 除外 …)`。
   後者の書式は手順5.5の引き継ぎが読む）。2026-11 の盲検の再レビューでは、一次承認のうち再却下は
   行追加 0.8%・漢字追加 1.9%。Sonnet / Haiku は漢字追加で却下すべき候補の 3〜4 割を通すので、レビューには使わない。

6.5. 外国人名の音読みの除外（承認が済んだ後、適用の前）:

   ```bash
   python3 $S/foreign_names.py --findings qa/findings/<run-id>.jsonl \
     --ndl-work qa/sources/ndl-work-<date> --list          # 確認だけ
   python3 $S/foreign_names.py --findings qa/findings/<run-id>.jsonl \
     --ndl-work qa/sources/ndl-work-<date> --apply
   ```

   NDL 典拠には中国・朝鮮の人名が音読みで入っている（張 憲文 → けんぶん）。その名を持つ人物の姓を
   数え、中国・朝鮮系の 1 字姓の人物を除くと NDL の裏付けが 2 人未満になり Wikidata の裏付けもない表記を
   不採用にする（2026-11 では承認済みのうち 81 件）。`--ndl-work` は人物単位の生データ（fetch_ndl.py の `--work`）。

   索引の性別が female の add_row は辞書由来で当てにならず、男性表記が多く混じる（2026-11 では女性名ファイル向け
   907 件中 708 件が却下）。却下理由が「男性名」のものは、男性名ファイルへの add_row として出し直して
   レビューに回すとよい。

7. 適用: `/qa-apply` の手順（dry-run → 明示承認 → ブランチ → 適用 → validate/pytest → 件数同期）。

7.5. 生年代メタデータ（JSON/SQLite 版の `birth_decades`）を更新する。`fetch_wikidata.py` に
   `--birth-decades-out qa/sources/wikidata-births-<date>.jsonl` を付けて取得しておき、適用後のデータで集計する:

   ```bash
   python3 $S/build_birth_decades.py --ndl-work qa/sources/ndl-work \
     --sources qa/sources/wikidata-births-<date>.jsonl --out qa/metadata/birth_decades.csv
   python3 scripts/build_formats.py --out build/   # 読み戻し検証まで行う
   ```

   `qa/metadata/birth_decades.csv` はコミットする（リリース時に CI が JSON/SQLite に組み込む）。

8. 件数同期: 行数が変わった場合は `CLAUDE.md`（データセット構造の件数）と
   `README.md` / `README_ja.md`（データ件数）を更新する（`/qa-apply` 手順6と同じ対象）。

9. リリース: `/release <version>`（データ追加はマイナーバージョンを上げる）。

## 性別判定プロンプト（テンプレート）

```
あなたは日本人の名前の専門家です。<batch-file の絶対パス> を読み、entries の各 reading について、
kanji（候補漢字）と sources（NDL/Wikidata の人物数）を参考に、その名前が主に使われる性別を判定してください。
判定は male / female / unisex / unknown のいずれか。確信が持てなければ unknown。
出力: <out-dir>/results/<batch_id>.json に {"batch_id": "<batch_id>", "decisions": {"<reading>": "<判定>", ...}} を書く。
全 reading を必ず含めること。
```

## 注意

- `qa/sources/*` は再取得できるため追跡しない（`.gitignore` 済み、`manifest.json` のみ例外
  で追跡）。`qa/sources/index.json` を含むスナップショットはすべて `.gitignore` 対象。
  取得日と件数は `qa/sources/manifest.json` に記録してコミットする。
- `qa/work/` も `.gitignore` 済みの一時領域。コミットするのは `qa/findings/` と
  `qa/sources/manifest.json` のみ。
- JMnedict 由来の漢字・読みを候補や evidence の値に転記しないこと（索引の ✓ 表示のみ）。
- 候補の上限（既定 2000 件）を超えた分は次回に回る。閾値は `--min-ndl` / `--auto-ndl` で調整する。
  2026-11 は `--max-candidates 100000` で持ち越しを消化した。手順5.5で以前の判断を引き継げば、
  上限なしでもレビューに回る件数は新規分に限られる。
- このスキルは dataset CSV を一切変更しない。修正の適用は `/qa-apply`。
