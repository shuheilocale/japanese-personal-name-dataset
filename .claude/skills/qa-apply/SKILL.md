---
name: qa-apply
description: Use when qa/findings/ の承認済み疑義を dataset CSV に適用するとき、または「QA適用」「findings 適用」「クリーニング実行」を求められたとき。適用前に必ずユーザーの明示承認を得ること。
---

# 承認済み findings の一括適用

## 前提

- dataset CSV は PreToolUse フックで保護されている。このスキルは
  apply_findings.py（Bash 実行）で適用するが、**実行前に必ずユーザーへ
  適用内容を提示して明示承認を得ること**。承認なしで実行してはならない。

## 承認（トリアージ UI）

保留 findings の承認/却下は以下で起動するローカル UI で行う（判断は即座に JSONL へ保存される）:

```bash
python3 .claude/skills/qa-apply/scripts/triage_server.py \
  --findings qa/findings/<run-id>.jsonl \
  --dataset-dir japanese_personal_name_dataset/dataset
```

行単位でキー操作（a=承認 / r=却下 / s=保留 / u=取り消し / j,k=移動）。左のフィルタで絞り込み、「表示中を一括承認/却下」で同種の疑義をまとめて処理できる。客観シグナル（別読み行に同一漢字あり・接尾辞ルール違反・提案読みの重複）が ⚑ で表示される。判断後はこのスキルの手順で適用する。

## 手順

1. 対象の findings ファイルを確認し、dry-run で適用予定を提示する:
   ```bash
   python3 .claude/skills/qa-apply/scripts/apply_findings.py \
     --findings qa/findings/<run-id>.jsonl \
     --dataset-dir japanese_personal_name_dataset/dataset \
     --qa-dir qa \
     --from-report qa/reports/<run-id>.md --dry-run
   ```
2. 適用予定（件数・内容）をユーザーに提示し、**明示承認を得る**。
3. ブランチを切る: `git checkout -b qa/apply-<run-id>`
4. `--dry-run` を外して実行する。
5. 回帰確認:
   ```bash
   python3 .claude/skills/validate-dataset/scripts/validate.py
   uv run pytest tests/ -v
   ```
6. 行数が変わった場合は以下の件数表記をすべて更新する:
   - `README.md` / `README_EN.md`（データ件数）
   - `CLAUDE.md`（データセット構造の件数）
   - `tests/test_core.py`（期待件数のアサーション）
   - `.claude/skills/validate-dataset/SKILL.md`（期待行数）
7. diff をユーザーに提示してからコミットし、PR を作るか main へマージするかを
   ユーザーに確認する。
8. 適用後の findings JSONL（status: applied/rejected）と qa/verified.json も
   同じコミットに含める（監査証跡）。
