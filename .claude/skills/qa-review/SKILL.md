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
   全バッチの結果ファイルが揃うまで繰り返す。
5. マージ:
   ```bash
   python3 .claude/skills/qa-review/scripts/qa_batch.py merge \
     --qa-dir qa --work-dir qa/work/<run-id> --run-id <run-id>
   ```
6. 未処理/不正バッチが報告されたら、そのバッチだけ手順4をやり直して再マージ。
7. `qa/reports/<run-id>.md` をユーザーに提示し、`qa/findings/<run-id>.jsonl`
   と `qa/verified.json` をコミットする（dataset CSV は変更しない）。

## サブエージェントプロンプト（テンプレート）

```
あなたは日本人の姓名データセットの品質監査員です。
<batch-file の絶対パス> を読み、entries の各エントリを判定してください。

判定観点:
(a) kanji の各表記は reading の読みで実在の日本人名として妥当か
(b) reading/kanji は人名か（地名・一般名詞・スクレイピング残骸ではないか）
(c) file の配置は妥当か（例: 明らかに女性名が first_name_man_org.csv にある）
- deterministic_error が付いているエントリは読みとローマ字の不一致が機械検出
  済み。どちらの列が誤りかを判断し fix_romaji / fix_reading を提案すること。
- 判断に迷う場合は「疑義あり・confidence: low」とする（OK にしない）。
- 珍しいだけの名前（キラキラネーム含む）は OK とする。確実に誤りと言える
  根拠があるものだけを疑義とする。

出力: <work-dir>/results/<batch_id>.json に以下の JSON を書く。
{
  "batch_id": "<batch_id>",
  "findings": [
    {"id": "<file>:<reading>", "file": "<file>", "entry": "<raw をそのまま>",
     "check": "kanji_reading_mismatch | not_a_name | wrong_gender_file | romaji_reading_mismatch",
     "severity": "error", "confidence": "high | medium | low",
     "evidence": "<日本語で根拠>",
     "proposed_fix": {"action": "remove_row | remove_kanji | fix_romaji | fix_reading | move_to_file | none", "value": "<対象値>"},
     "status": "pending", "detected_at": "<今日の日付 YYYY-MM-DD>",
     "detected_by": "qa-review v1"}
  ],
  "ok_hashes": ["<問題なしと判定した全エントリの hash>"]
}
findings に入れたエントリの hash は ok_hashes に入れないこと。
全エントリが findings か ok_hashes のどちらかに必ず入ること。
```

## 注意

- このスキルは dataset CSV を一切変更しない。修正の適用は /qa-apply。
- qa/work/ は .gitignore 済みの一時領域。コミットするのは qa/findings/・
  qa/verified.json・qa/reports/ のみ。
