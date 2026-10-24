# Contributing

Thank you for helping improve the Japanese Personal Name Dataset. Issues and pull requests are welcome in English or Japanese.

日本語での Issue・Pull Request も歓迎します。

## Ways to contribute

- **Report a data error** — a wrong reading, romaji or kanji spelling, or a name in the wrong gender file. Use the [data correction form](https://github.com/shuheilocale/japanese-personal-name-dataset/issues/new?template=data_correction.yml). This is the most valuable contribution.
- **Report a bug or request a feature** in the Python API.
- **Improve documentation or examples.**

## Development setup

You need Python 3.8 or later and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/shuheilocale/japanese-personal-name-dataset.git
cd japanese-personal-name-dataset
uv venv
uv pip install -e ".[dev]"
uv run pytest
```

Before opening a pull request, run:

```bash
uv run pytest                                              # all tests
python3 .claude/skills/validate-dataset/scripts/validate.py  # dataset checks
uvx mypy japanese_personal_name_dataset                    # type check
```

CI runs the tests on Linux, macOS and Windows with Python 3.8 to 3.12.

## Coding guidelines

- **Python 3.8 compatible.** Do not use `X | Y` type unions, `match`, `list[int]` at runtime or other 3.9+ features.
- **No runtime dependencies.** The package uses the standard library only.
- **Type hints** on public functions. The package ships `py.typed`.
- **Tests** for every behavior change, in `tests/`.
- Open files with `encoding="utf-8"` so that Windows works.
- Keep `load_dataset()` backward compatible. It is used by existing projects.

## Changing the dataset

The CSV files in `japanese_personal_name_dataset/dataset/` are not edited by hand. Data changes go through a reviewed findings ledger so that every change has evidence and can be audited:

1. Describe the correction in an issue, or add a finding to a JSONL file under `qa/findings/` following the schema in [the QA design document](docs/superpowers/specs/2026-07-27-qa-foundation-design.md).
2. A maintainer reviews it and applies approved findings with the `apply_findings.py` tool, which also keeps romaji and the optimized subsets consistent.
3. `validate.py` and the test suite must pass afterwards.

Format rules:

- First names: `reading,romaji,kanji1,kanji2,...` in hiragana, Hepburn romaji and kanji.
- Last names: `kanji,estimated_population,reading,romaji`.
- Romaji follows Hepburn romanization. Long vowels are written as in the kana (`ou`, `oo`).
- Only add given names, not pen names, posthumous names or titles.

## Pull requests

- Keep each pull request focused on one change.
- Describe what changed and why, and link the related issue.
- Fill in the checklist in the pull request template.

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.
