from pathlib import Path

import pytest

from scaffld.errors import RenderError
from scaffld.manifest import SkipRule
from scaffld.render import (
    build_plan,
    evaluate_condition,
    make_environment,
    render_string,
    resolve_skip_paths,
    write_plan,
)


@pytest.fixture
def env():
    return make_environment()


def test_filters(env):
    ctx = {"name": "My Cool App"}
    assert render_string(env, "{{ name | snake }}", ctx) == "my_cool_app"
    assert render_string(env, "{{ name | kebab }}", ctx) == "my-cool-app"
    assert render_string(env, "{{ name | pascal }}", ctx) == "MyCoolApp"
    assert render_string(env, "{{ name | slugify }}", ctx) == "my-cool-app"
    assert render_string(env, "{{ name | camel }}", ctx) == "myCoolApp"


def test_render_string_error(env):
    with pytest.raises(RenderError):
        render_string(env, "{{ undefined_var }}", {})


def test_evaluate_condition(env):
    assert evaluate_condition(env, "use_cli", {"use_cli": True}) is True
    assert evaluate_condition(env, "not use_cli", {"use_cli": True}) is False
    assert evaluate_condition(env, "x == 'a'", {"x": "a"}) is True


def _make_tree(tmp_path: Path) -> Path:
    tdir = tmp_path / "template"
    (tdir / "src" / "{{ pkg }}").mkdir(parents=True)
    (tdir / "src" / "{{ pkg }}" / "__init__.py.jinja").write_text(
        '"""{{ project }}"""\n', encoding="utf-8"
    )
    (tdir / "README.md.jinja").write_text("# {{ project }}\n", encoding="utf-8")
    (tdir / "static.txt").write_text("no templating here\n", encoding="utf-8")
    return tdir


def test_build_and_write_plan(tmp_path, env):
    tdir = _make_tree(tmp_path)
    ctx = {"pkg": "demo_pkg", "project": "Demo"}
    plan = build_plan(env, tdir, ctx)
    targets = {pf.rel_target.as_posix() for pf in plan.files}
    assert targets == {
        "src/demo_pkg/__init__.py",  # .jinja stripped, dir name rendered
        "README.md",
        "static.txt",
    }

    dest = tmp_path / "out"
    write_plan(plan, dest)
    assert (dest / "src" / "demo_pkg" / "__init__.py").read_text(encoding="utf-8") == '"""Demo"""\n'
    assert (dest / "README.md").read_text(encoding="utf-8") == "# Demo\n"
    assert (dest / "static.txt").read_text(encoding="utf-8") == "no templating here\n"


def test_jinja_suffix_stripped(tmp_path, env):
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "config.yaml.jinja").write_text("name: {{ project }}\n", encoding="utf-8")
    (tdir / "plain.j2").write_text("{{ project }}\n", encoding="utf-8")
    plan = build_plan(env, tdir, {"project": "Z"})
    names = sorted(pf.rel_target.as_posix() for pf in plan.files)
    assert names == ["config.yaml", "plain"]


def test_skip_paths_remove_files(tmp_path, env):
    tdir = tmp_path / "t"
    (tdir / "src").mkdir(parents=True)
    (tdir / "src" / "cli.py").write_text("x\n", encoding="utf-8")
    (tdir / "src" / "core.py").write_text("y\n", encoding="utf-8")
    skip = resolve_skip_paths(
        env, [SkipRule(when="not use_cli", paths=["src/cli.py"])], {"use_cli": False}
    )
    assert skip == {"src/cli.py"}
    plan = build_plan(env, tdir, {"use_cli": False}, skip_paths=skip)
    names = {pf.rel_target.as_posix() for pf in plan.files}
    assert names == {"src/core.py"}


def test_binary_passthrough(tmp_path, env):
    tdir = tmp_path / "t"
    tdir.mkdir()
    blob = bytes(range(256))
    (tdir / "logo.png").write_bytes(blob)
    plan = build_plan(env, tdir, {})
    pf = plan.files[0]
    assert pf.is_binary is True
    dest = tmp_path / "out"
    write_plan(plan, dest)
    assert (dest / "logo.png").read_bytes() == blob


def test_raw_globs_not_rendered(tmp_path, env):
    tdir = tmp_path / "t"
    tdir.mkdir()
    (tdir / "keep.tmpl").write_text("literal {{ do_not_render }}\n", encoding="utf-8")
    plan = build_plan(env, tdir, {}, raw_globs=["*.tmpl"])
    dest = tmp_path / "out"
    write_plan(plan, dest)
    assert (dest / "keep.tmpl").read_text(encoding="utf-8") == "literal {{ do_not_render }}\n"


def test_empty_dir_preserved(tmp_path, env):
    tdir = tmp_path / "t"
    (tdir / "emptydir").mkdir(parents=True)
    plan = build_plan(env, tdir, {})
    assert "emptydir" in plan.dirs
    dest = tmp_path / "out"
    write_plan(plan, dest)
    assert (dest / "emptydir").is_dir()
