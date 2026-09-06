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
     に結果と `manifest.json`（done/split/saturated）を保存する。初回は 40〜90 分
     かかる想定。中断してもそのまま同じコマンドを再実行すれば `done`/`split` 済みの
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

7. 適用: `/qa-apply` の手順（dry-run → 明示承認 → ブランチ → 適用 → validate/pytest → 件数同期）。

8. 件数同期: 行数が変わった場合は `CLAUDE.md`（データセット構造の件数）と
   `README.md` / `README_EN.md`（データ件数）を更新する（`/qa-apply` 手順6と同じ対象）。

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
- このスキルは dataset CSV を一切変更しない。修正の適用は `/qa-apply`。
