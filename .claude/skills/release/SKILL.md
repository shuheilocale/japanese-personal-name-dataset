---
name: release
description: Use when the user asks to release a new version, bump the version, or publish to PyPI（リリース、バージョンアップ、PyPI公開）.
disable-model-invocation: true
---

# リリース手順

引数: 新バージョン番号（例: `/release 0.1.2`）。省略時は pyproject.toml の現在値から patch bump を提案してユーザーに確認する。

## チェックリスト

以下を順に実行する。各ステップが失敗したら停止してユーザーに報告する。

1. **前提確認**: `git status` がクリーンで main ブランチにいること。`git pull` で最新化。
2. **テスト**: `uv run pytest tests/ -v` が全件パスすること。
3. **データ検証**: `python3 .claude/skills/validate-dataset/scripts/validate.py` がエラー 0 件であること。
4. **バージョン更新**: pyproject.toml の `version` を新バージョンに書き換える（バージョンのソースはここだけ）。
5. **コミット & push**: `git add pyproject.toml` → コミットメッセージ `Bump version to X.Y.Z` → `git push`。
6. **GitHub リリース作成**: `gh release create vX.Y.Z --title vX.Y.Z --generate-notes`
   → これで publish.yml（テスト → `uv build` → PyPI 公開）が発火する。
7. **公開確認**: `gh run watch` で Publish to PyPI ワークフローの成功を確認し、
   https://pypi.org/project/japanese-personal-name-dataset/ に新バージョンが出ていることを確認する。

## 注意

- PyPI 認証は publish.yml 内の `PYPI_API_TOKEN` シークレットで行われる。ローカルから `uv publish` はしない。
- リリースをやり直す場合は GitHub リリースとタグの削除（`gh release delete` / `git push --delete origin vX.Y.Z`）が必要。PyPI は同一バージョンの再アップロードを受け付けないため、失敗時はバージョンを上げて再リリースする。
