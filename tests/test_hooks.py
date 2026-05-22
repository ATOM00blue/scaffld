import sys

import pytest

from scaffld.errors import HookError
from scaffld.hooks import plan_hooks, run_hooks
from scaffld.manifest import Hook
from scaffld.render import make_environment


@pytest.fixture
def env():
    return make_environment()


def test_plan_hooks_renders_and_conditions(env):
    hooks = [
        Hook(name="a", run="echo {{ name }}", when="true"),
        Hook(name="b", run="echo skip", when="not enabled"),
    ]
    planned = plan_hooks(env, hooks, {"name": "demo", "enabled": True})
    assert planned[0].command == "echo demo"
    assert planned[0].will_run is True
    assert planned[1].will_run is False


def test_run_hooks_creates_file(env, tmp_path):
    # A cross-platform way to create a file: python -c.
    py = sys.executable.replace("\\", "/")
    hook = Hook(
        name="touch",
        run=f'"{py}" -c "open(\'made.txt\',\'w\').write(\'ok\')"',
        when="true",
    )
    planned = plan_hooks(env, [hook], {})
    run_hooks(planned, tmp_path)
    assert (tmp_path / "made.txt").read_text() == "ok"


def test_run_hooks_skips_false_condition(env, tmp_path):
    py = sys.executable.replace("\\", "/")
    hook = Hook(
        name="touch",
        run=f'"{py}" -c "open(\'made.txt\',\'w\').write(\'ok\')"',
        when="false",
    )
    planned = plan_hooks(env, [hook], {})
    run_hooks(planned, tmp_path)
    assert not (tmp_path / "made.txt").exists()


def test_run_hooks_failure_raises(env, tmp_path):
    py = sys.executable.replace("\\", "/")
    hook = Hook(name="boom", run=f'"{py}" -c "import sys; sys.exit(3)"', when="true")
    planned = plan_hooks(env, [hook], {})
    with pytest.raises(HookError):
        run_hooks(planned, tmp_path)
