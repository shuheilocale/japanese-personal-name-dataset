# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

日本人の姓名データセットを提供するPythonパッケージです。男性・女性の名前と姓のCSVファイルが含まれており、ひらがな、ローマ字（ヘボン式）、漢字のバリエーションが格納されています。

## データセット構造

CSVデータセットは `japanese_personal_name_dataset/dataset/` に配置されています：

- `first_name_man_org.csv` - 男性の名（5,638種類）
- `first_name_man_opti.csv` - 男性の名・最適化版（702種類、有名な名前を抜粋）
- `first_name_woman_org.csv` - 女性の名（3,339種類）
- `first_name_woman_opti.csv` - 女性の名・最適化版（241種類）
- `last_name_org.csv` - 姓（1,999種類）

### CSVフォーマット

**名（first name）**: `ひらがな,ローマ字,漢字1,漢字2,...` （漢字列は可変）
例: `あい,ai,藍`

**姓（last name）**: `漢字,推定人数,ひらがな,ローマ字`
例: `佐藤,1887000,さとう,satou`

## 開発コマンド

### テスト実行

```bash
uv run pytest                           # 全テストを実行
uv run pytest tests/test_core.py        # 特定のテストファイルを実行
uv run pytest --cov=japanese_personal_name_dataset  # カバレッジ付き
```

### インストール

```bash
uv venv                          # 仮想環境を作成
uv pip install -e ".[dev]"       # 開発用依存（pytest等）込みでインストール
```

### パッケージ構造確認

```bash
python -m japanese_personal_name_dataset.core  # coreモジュールを直接実行
```

## コードアーキテクチャ

### モジュール構成

- **`api.py`**: パブリックAPIレイヤー - `load_dataset()` 関数を提供
- **`core.py`**: コア実装 - CSVの読み込みとパース処理
- **`helpers.py`**: ユーティリティ関数群 - `generate_random_name()`、`generate_random_full_name()`、`search_by_reading()`、`search_by_kanji()`、`search_last_name()`、`get_last_names()`、`get_popular_names()`、`is_valid_name()`、`get_readings_for_kanji()`
- **`__init__.py`**: パッケージのエントリーポイント - `load_dataset` とヘルパー関数をエクスポート

### データ読み込みフロー

1. ユーザーが `api.py` から `load_dataset()` を呼び出す
2. `api.py` が `core.load_dataset()` に処理を委譲
3. `core.py` が相対パス解決を使って `dataset/` ディレクトリからCSVファイルを読み込む
4. タプルを返す: `(man_names, woman_names)` 各要素は辞書型：
   - キー: ひらがな読み
   - 値: `{'en': ローマ字, 'kanji': [漢字のバリエーションリスト]}`

### パス解決

CSVファイルは以下の方法で読み込まれます：
```python
os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, 'dataset/...')
```
この処理により、コードがどこから実行されても、パッケージルートの `dataset/` ディレクトリが解決されます。

## パッケージ配布

`MANIFEST.in` に `recursive-include dataset *.csv` を記述することで、パッケージ配布時にCSVファイルが確実に含まれるようになっています。

リリースは GitHub リリースの作成をトリガーに `.github/workflows/publish.yml` が PyPI へ公開します。手順は `/release` スキル（`.claude/skills/release/SKILL.md`）を参照。

## Claude Code 自動化

`.claude/settings.json` に以下のフックが設定されています：

- **PreToolUse**: `dataset/` 配下の CSV への Edit/Write をブロック（データセット保護）。データ修正が必要な場合はユーザーの明示的な承認を得ること。
- **PostToolUse**: `.py` ファイル編集後に vermin で Python 3.8 互換性を自動チェック（`X | Y` 型ヒント等の 3.9+ 構文を検出）。

### データ品質保証（QA基盤）

- `/validate-dataset`: 決定的チェック（形式・重複・読み⇔ローマ字照合・クロスファイル整合性）
- `/qa-review`: LLM 品質レビュー（漢字⇔読みの妥当性・人名らしさ・男女配置）。疑義は `qa/findings/*.jsonl` に、検証済みは `qa/verified.json` に記録
- `/qa-apply`: 承認済み findings の一括適用（ユーザーの明示承認必須）
- 設計書: `docs/superpowers/specs/2026-07-27-qa-foundation-design.md`
- リリース前の互換性レビューは `py38-compat-reviewer` サブエージェントを使用
