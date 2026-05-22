"""Security regression tests: path traversal, SSTI sandbox, git hardening."""

from __future__ import annotations

import pytest

from scaffld.errors import PathTraversalError, RenderError, TemplateNotFoundError
from scaffld.manifest import SkipRule
from scaffld.render import (
    _safe_relative,
    build_plan,
    make_environment,
    render_string,
    resolve_skip_paths,
    write_plan,
)
from scaffld.resolver import _resolve_git


@pytest.fixture
def env():
    return make_environment()


# --------------------------------------------------------------------------- #
# C1 — path traversal / ZIP-SLIP
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "bad",
    [
        "../escaped",
        "../../etc/passwd",
        "a/../../b",
        "/etc/passwd",
        "/abs",
        "C:/Windows/system32",
        "C:\\Windows\\evil",
        "..\\..\\evil",
        "\\\\host\\share\\x",
    ],
)
def test_safe_relative_rejects_traversal(bad):
    with pytest.raises(PathTraversalError):
        _safe_relative(bad, where="test")


@pytest.mark.parametrize(
    "good,expected",
    [
        ("a/b/c.txt", "a/b/c.txt"),
        ("./a/./b", "a/b"),
        ("file.txt", "file.txt"),
        ("", "."),  # empty -> empty relative path (PurePosixPath().as_posix() == ".")
        (".", "."),
    ],
)
def test_safe_relative_allows_confined(good, expected):
    assert _safe_relative(good, where="test").as_posix() == expected


def test_build_plan_rejects_rendered_traversal_filename(tmp_path, env):
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "{{ name }}.txt").write_text("pwn", encoding="utf-8")
    with pytest.raises(PathTraversalError):
        build_plan(env, tdir, {"name": "../../../escaped"})


def test_build_plan_rejects_rendered_traversal_dirname(tmp_path, env):
    tdir = tmp_path / "t"
    (tdir / "{{ d }}").mkdir(parents=True)
    (tdir / "{{ d }}" / "f.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PathTraversalError):
        build_plan(env, tdir, {"d": "../../../etc"})


def test_skip_paths_reject_traversal(env):
    with pytest.raises(PathTraversalError):
        resolve_skip_paths(
            env, [SkipRule(when="true", paths=["../../escape"])], {}
        )


def test_write_plan_realpath_containment(tmp_path, env):
    # Craft a plan whose rel_target is fine, then tamper to simulate escape.
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "ok.txt").write_text("x", encoding="utf-8")
    plan = build_plan(env, tdir, {})
    # Force an escaping target to prove write_plan's realpath guard fires.
    from pathlib import PurePosixPath

    plan.files[0].rel_target = PurePosixPath("../escaped.txt")
    with pytest.raises(PathTraversalError):
        write_plan(plan, tmp_path / "out")


def test_confined_paths_still_work(tmp_path, env):
    tdir = tmp_path / "t"
    (tdir / "src" / "{{ pkg }}").mkdir(parents=True)
    (tdir / "src" / "{{ pkg }}" / "x.py.jinja").write_text("# {{ pkg }}\n", encoding="utf-8")
    plan = build_plan(env, tdir, {"pkg": "demo"})
    out = tmp_path / "out"
    write_plan(plan, out)
    assert (out / "src" / "demo" / "x.py").read_text(encoding="utf-8") == "# demo\n"


# --------------------------------------------------------------------------- #
# C2 — SSTI sandbox
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "payload",
    [
        "{{ ''.__class__ }}",
        "{{ ''.__class__.__mro__ }}",
        "{{ ''.__class__.__mro__[1].__subclasses__() }}",
        "{{ cycler.__init__.__globals__ }}",
        "{{ ''.__class__.__base__.__subclasses__() }}",
    ],
)
def test_ssti_sandbox_blocks_escape(env, payload):
    with pytest.raises(RenderError):
        render_string(env, payload, {})


def test_sandbox_allows_normal_rendering(env):
    assert render_string(env, "{{ name | snake }}", {"name": "My App"}) == "my_app"


# --------------------------------------------------------------------------- #
# M1 — git argument-injection hardening
# --------------------------------------------------------------------------- #

def test_git_rejects_dash_ref():
    with pytest.raises(TemplateNotFoundError):
        _resolve_git("https://github.com/x/y", "--upload-pack=touch /tmp/pwn")


def test_git_rejects_traversal_subdir():
    with pytest.raises(TemplateNotFoundError):
        _resolve_git("https://github.com/x/y#../../etc", None)
