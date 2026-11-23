---
name: qa-review
description: Use when dataset CSV の LLM 品質レビューを実行するとき（漢字と読みの対応・人名らしさ・男女ファイル配置の検証）、または「QAレビュー」「品質チェック」「疑義検出」を求められたとき。決定的チェックは /validate-dataset を使う。
---

# dataset LLM 品質レビュー

エントリごとに (a) 漢字と読みの対応妥当性 (b) 日本人名としての実在性
(c) 収録ファイルの妥当性を判定し、疑義を qa/findings/ に記録する。
判定以外はすべて qa_batch.py が決定的に処理する。

## 手順

1. `git status` がクリーンであることを確認（差分があればユーザーに確認）。
2. run-id を決める: `YYYY-MM-<対象>` 形式（例: `2026-07-full`）。
3. バッチ準備:
   ```bash
   python3 .claude/skills/qa-review/scripts/qa_batch.py prep \
     --dataset-dir japanese_personal_name_dataset/dataset \
     --qa-dir qa --out-dir qa/work/<run-id> --batch-size 100
   ```
4. `qa/work/<run-id>/manifest.json` の batch_ids ごとに、下のプロンプトで
   サブエージェント（general-purpose）を起動する。同時実行は 4 つまで。
   レビュアーは疑義だけを `qa/work/<run-id>/decisions/<batch_id>.json` に書き、
   `review_result.py` で結果ファイル（`results/<batch_id>.json`）を作る。行の書き写しと
   「問題なし」の一覧はスクリプトが埋めるので、バッチが不正・未完了になりにくい。
   全バッチの結果ファイルが揃うまで繰り返す。
   - 費用の目安（2026-11）: 1 バッチ（100 行）10〜48 万トークン・6〜54 分。エージェントが
     `qa/sources/index.json` で裏取りするため、表記の多いバッチほど重い。4 バッチ程度で試し、
     指摘の量と質を見てから残りを流す。
   - 表記の多い行（最適化版など）は見落としが出る。2026-11 では同じ表記について最適化版側の
     指摘は完全版側の 3 割ほどだった。適用前に `/qa-apply` の手順0で完全版と最適化版の判断を揃える。
5. マージ:
   ```bash
   python3 .claude/skills/qa-review/scripts/qa_batch.py merge \
     --qa-dir qa --work-dir qa/work/<run-id> --run-id <run-id>
   ```
6. 未処理（結果ファイルなし）・不正（スキーマ違反または id 重複）・未完了
   （エントリの一部が findings/ok_hashes のどちらにも入っていない）バッチが
   報告されたら、そのバッチだけ手順4をやり直して再マージする。merge は
   run-id の findings JSONL をそのつど全置換するため、同じ結果を何度
   再マージしても疑義が重複しない（人間が承認/却下した status は引き継がれる）。
7. `qa/reports/<run-id>.md` をユーザーに提示し、`qa/findings/<run-id>.jsonl`
   と `qa/verified.json` をコミットする（dataset CSV は変更しない）。

## サブエージェントプロンプト（テンプレート）

```
あなたは日本人の姓名データセットの品質監査員です。
<work-dir の絶対パス>/<batch_id>.json を読み、entries の各エントリ（データセットの 1 行）を判定してください。
入力は分割して最後まで読み、表記の多い行でも表記を 1 つずつ確認すること。

判定観点:
(a) kanji の各表記は reading の読みで実在の日本人名として妥当か（名乗り読みを含め、その読みで読めるか）
(b) reading/kanji は人名か（地名・一般名詞・号や雅号・外国人名の音読み・スクレイピング残骸ではないか）
(c) file の配置は妥当か（例: 明らかに女性名が first_name_man_org.csv にある）
- deterministic_error が付いているエントリは読みとローマ字の不一致が機械検出
  済み。どちらの列が誤りかを判断し fix_romaji / fix_reading を提案すること。
- 判断に迷う場合は「疑義あり・confidence: low」とする（OK にしない）。
- 珍しいだけの名前（キラキラネーム・古風な名を含む）は OK とする。確実に誤りと言える
  根拠があるものだけを疑義とする。
- 裏付けは qa/sources/index.json（NDL・Wikidata・JMnedict の索引、50 MB）をスクリプトで
  必要なキー（given|<表記>|<読み> など）だけ引いて確かめてよい。
- JMnedict は照合専用（CC BY-SA）。evidence には「JMnedict に収録あり／なし」までしか書かず、
  JMnedict にしかない表記・読みの組を evidence や value に書き写さない。NDL・Wikidata の人数は書いてよい。

出力:
1. <work-dir>/decisions/<batch_id>.json に、疑義だけを次の形で書く（問題のない行は書かない）。
{"batch_id": "<batch_id>", "findings": [
  {"hash": "<エントリの hash>",
   "check": "kanji_reading_mismatch | not_a_name | wrong_gender_file | romaji_reading_mismatch",
   "confidence": "high | medium | low", "evidence": "<日本語で根拠。どの表記がなぜ誤りか>",
   "action": "remove_kanji | remove_row | fix_romaji | fix_reading | move_to_file | none",
   "value": "<対象値>"}]}
   - remove_kanji: value は外す表記。同じ行から複数外すときは 1 つの finding にまとめ「、」で並べる。
     行の全表記を外すなら remove_row（value は空文字）。
   - fix_reading はひらがなのみ、fix_romaji は小文字の英字のみ、move_to_file は移動先の名ファイル名。
   - 同じ行に同じ check の finding は 1 つまで。
2. python3 <リポジトリ>/.claude/skills/qa-review/scripts/review_result.py --work-dir <work-dir> <batch_id>
   を実行し、エラーが出たら decisions を直して `OK:` が出るまで繰り返す。
3. 判定は 1 行ずつ自分で行う（スクリプトによる機械的な判定はしない）。decisions と results 以外は変更しない。
最終報告は `OK:` の行を 1 行だけ。
```

## 注意

- このスキルは dataset CSV を一切変更しない。修正の適用は /qa-apply。
- qa/work/ は .gitignore 済みの一時領域。コミットするのは qa/findings/・
  qa/verified.json・qa/reports/ のみ。
