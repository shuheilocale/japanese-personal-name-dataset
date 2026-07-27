---
name: validate-dataset
description: Use when dataset/ 配下の CSV を追加・変更・レビューするとき、リリース前の品質確認をするとき、またはデータ形式・重複・文字種（ひらがな/ローマ字/全角混入）の検証を求められたとき。
---

# dataset CSV 検証

## 実行方法

```bash
python3 .claude/skills/validate-dataset/scripts/validate.py
```

引数に dataset ディレクトリを渡すと別の場所も検証できる。終了コード 0 = エラーなし、1 = エラーあり。

## 検証内容

| 対象 | チェック |
|------|---------|
| 名 CSV（`first_name_*.csv`） | 列数（ひらがな,ローマ字,漢字...）、ひらがな列の文字種、ローマ字列（`a-z` と `-` `'` のみ）、行内の漢字重複、読みの重複（core.py は読みをキーに辞書化するため重複は上書きされる） |
| 姓 CSV（`last_name_org.csv`） | 4列固定（漢字,推定人数,ひらがな,ローマ字）、推定人数が整数、文字種、姓の重複 |

ERROR は形式違反（修正必須）、WARNING はデータ品質上の注意（重複など）。

## 注意

- dataset CSV は PreToolUse フック（[.claude/settings.json](../../settings.json)）で編集がブロックされている。データ修正はユーザーの明示的な承認を得てから、フックの一時無効化またはユーザー自身の操作で行うこと。
- 期待行数（README 記載値）: man_org 5675 / man_opti 703 / woman_org 3344 / woman_opti 241 / last_name 2000。行数が変わる変更はバージョンアップとREADME更新を伴うべき。
