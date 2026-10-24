"""examples/ のスクリプトが動くことを確認する（#9）。README から参照しているため。"""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
sys.path.insert(0, EXAMPLES)


def _run(script, *args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=ROOT)
    return subprocess.run([sys.executable, os.path.join(EXAMPLES, script)] + list(args),
                          capture_output=True, env=env, timeout=60)


@pytest.mark.parametrize("script", ["basic_usage.py", "name_statistics.py", "form_validation.py"])
def test_script_runs(script):
    result = _run(script)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stdout.strip()


def test_generate_test_users_json_is_deterministic():
    a = _run("generate_test_users.py", "--count", "5", "--format", "json", "--seed", "7")
    b = _run("generate_test_users.py", "--count", "5", "--format", "json", "--seed", "7")
    assert a.returncode == 0, a.stderr.decode("utf-8", "replace")
    users = json.loads(a.stdout.decode("utf-8"))
    assert len(users) == 5 and a.stdout == b.stdout
    assert {"family_name", "given_name", "family_name_kana", "given_name_kana", "email"} <= set(users[0])


def test_form_validation_accepts_known_and_suggests_unknown():
    import form_validation

    assert form_validation.check_given_name("太郎", "たろう") == []
    messages = form_validation.check_given_name("太郎", "たろ")
    assert messages and "たろう" in "".join(messages)


def test_web_api_handler():
    import web_api

    status, body = web_api.handle("/random?gender=male&count=3")
    assert status == 200 and len(body) == 3
    status, body = web_api.handle("/search?reading=%E3%81%9F%E3%82%8D%E3%81%86")
    assert status == 200 and body[0]["reading"] == "たろう"
    assert web_api.handle("/random?gender=x")[0] == 400
    assert web_api.handle("/nope")[0] == 404
