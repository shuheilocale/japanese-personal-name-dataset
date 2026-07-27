"""QA ツール（.claude/skills/*/scripts/）を import できるようにする。"""
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
for _rel in (
    os.path.join(".claude", "skills", "validate-dataset", "scripts"),
    os.path.join(".claude", "skills", "qa-review", "scripts"),
    os.path.join(".claude", "skills", "qa-apply", "scripts"),
):
    _p = os.path.join(_REPO_ROOT, _rel)
    if _p not in sys.path:
        sys.path.insert(0, _p)
