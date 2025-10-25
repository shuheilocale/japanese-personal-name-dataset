# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

日本人の姓名データセットを提供するPythonパッケージです。男性・女性の名前と姓のCSVファイルが含まれており、ひらがな、ローマ字（ヘボン式）、漢字のバリエーションが格納されています。

## データセット構造

CSVデータセットは `japanese_personal_name_dataset/dataset/` に配置されています：

- `first_name_man_org.csv` - 男性の名（5,678種類）
- `first_name_man_opti.csv` - 男性の名・最適化版（703種類、有名な名前を抜粋）
- `first_name_woman_org.csv` - 女性の名（3,346種類）
- `first_name_woman_opti.csv` - 女性の名・最適化版（241種類）
- `last_name_org.csv` - 姓（2,000種類）

### CSVフォーマット

**名（first name）**: `ひらがな,ローマ字,漢字1,漢字2,...` （漢字列は可変）
例: `あい,ai,藍`

**姓（last name）**: `漢字,推定人数,ひらがな,ローマ字`
例: `佐藤,1887000,さとう,satou`

## 開発コマンド

### テスト実行

```bash
pytest                           # 全テストを実行
pytest tests/test_core.py        # 特定のテストファイルを実行
pytest -v                        # 詳細出力
```

### インストール

```bash
pip install -e .                 # 編集可能モードでインストール
pip install -r requirements.txt  # 依存関係をインストール
```

### パッケージ構造確認

```bash
python -m japanese_personal_name_dataset.core  # coreモジュールを直接実行
```

## コードアーキテクチャ

### モジュール構成

- **`api.py`**: パブリックAPIレイヤー - `load_dataset()` 関数を提供
- **`core.py`**: コア実装 - CSVの読み込みとパース処理
- **`__init__.py`**: パッケージのエントリーポイント - `load_dataset` 関数をエクスポート

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
