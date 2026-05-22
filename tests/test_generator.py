import pytest

from scaffld.errors import OutputExistsError, ScaffldError
from scaffld.generator import describe, generate


def test_generate_basic(make_template, tmp_path):
    root = make_template(
        manifest=(
            "name: basic\n"
            "variables:\n"
            "  project: {default: Demo}\n"
            "  pkg: {default: '{{ project | snake }}'}\n"
        ),
        files={
            "template/{{ pkg }}/__init__.py.jinja": '"""{{ project }}"""\n',
            "template/README.md.jinja": "# {{ project }}\n",
        },
    )
    dest = tmp_path / "out"
    result = generate(str(root), dest, no_input=True)
    assert not result.dry_run
    assert (dest / "demo" / "__init__.py").read_text(encoding="utf-8") == '"""Demo"""\n'
    assert (dest / "README.md").read_text(encoding="utf-8") == "# Demo\n"
    assert sorted(result.files) == ["README.md", "demo/__init__.py"]


def test_generate_with_overrides(make_template, tmp_path):
    root = make_template(
        manifest="name: t\nvariables:\n  name: {default: x}\n",
        files={"template/{{ name }}.txt": "v={{ name }}"},
    )
    dest = tmp_path / "out"
    generate(str(root), dest, overrides={"name": "custom"}, no_input=True)
    assert (dest / "custom.txt").read_text(encoding="utf-8") == "v=custom"


def test_dry_run_writes_nothing(make_template, tmp_path):
    root = make_template(
        manifest="name: t\n", files={"template/a.txt": "hi"}
    )
    dest = tmp_path / "out"
    result = generate(str(root), dest, no_input=True, dry_run=True)
    assert result.dry_run
    assert result.files == ["a.txt"]
    assert not dest.exists()


def test_collision_protection(make_template, tmp_path):
    root = make_template(manifest="name: t\n", files={"template/a.txt": "hi"})
    dest = tmp_path / "out"
    generate(str(root), dest, no_input=True)
    with pytest.raises(OutputExistsError):
        generate(str(root), dest, no_input=True)
    # force overwrites
    generate(str(root), dest, no_input=True, force=True)


def test_skip_rule_applied(make_template, tmp_path):
    root = make_template(
        manifest=(
            "name: t\n"
            "variables:\n"
            "  use_cli: {type: bool, default: false}\n"
            "skip:\n"
            "  - when: 'not use_cli'\n"
            "    paths: ['cli.py']\n"
        ),
        files={"template/cli.py": "x", "template/core.py": "y"},
    )
    dest = tmp_path / "out"
    result = generate(str(root), dest, no_input=True)
    assert result.files == ["core.py"]
    assert not (dest / "cli.py").exists()


def test_composition_extends(make_template, tmp_path):
    base = make_template(
        manifest="name: base\n",
        files={"template/base.txt": "base", "template/shared.txt": "from-base"},
        name="base",
    )
    child = make_template(
        manifest=f"name: child\nextends: ['{base.as_posix()}']\n",
        files={"template/child.txt": "child", "template/shared.txt": "from-child"},
        name="child",
    )
    dest = tmp_path / "out"
    result = generate(str(child), dest, no_input=True)
    assert set(result.files) == {"base.txt", "child.txt", "shared.txt"}
    # later layer (child) overrides shared.txt
    assert (dest / "shared.txt").read_text(encoding="utf-8") == "from-child"


def _hook_manifest(tmp_path):
    """Build a manifest (as YAML) whose post-gen hook creates ``hooked.txt``."""
    import sys

    import yaml

    py = sys.executable.replace("\\", "/")
    script = tmp_path / "hookscript.py"
    script.write_text("import pathlib; pathlib.Path('hooked.txt').write_text('1')\n", encoding="utf-8")
    command = f'"{py}" "{script.as_posix()}"'
    return yaml.safe_dump(
        {"name": "t", "hooks": {"post_gen": [{"name": "make", "run": command}]}}
    )


def test_hooks_run(make_template, tmp_path):
    root = make_template(manifest=_hook_manifest(tmp_path), files={"template/a.txt": "x"})
    dest = tmp_path / "out"
    generate(str(root), dest, no_input=True)
    assert (dest / "hooked.txt").exists()


def test_hooks_can_be_disabled(make_template, tmp_path):
    root = make_template(manifest=_hook_manifest(tmp_path), files={"template/a.txt": "x"})
    dest = tmp_path / "out"
    generate(str(root), dest, no_input=True, run_post_hooks=False)
    assert not (dest / "hooked.txt").exists()


def test_describe(make_template):
    root = make_template(
        manifest="name: described\ndescription: a thing\nvariables:\n  x: hi\n",
        files={"template/a.txt": "x"},
    )
    m = describe(str(root))
    assert m.name == "described"
    assert m.description == "a thing"
    assert m.variables[0].name == "x"


def test_circular_extends_detected(make_template, tmp_path):
    a = make_template(manifest="name: a\nextends: ['__B__']\n", files={"template/a.txt": "a"}, name="a")
    b = make_template(
        manifest=f"name: b\nextends: ['{a.as_posix()}']\n", files={"template/b.txt": "b"}, name="b"
    )
    # Point a -> b -> a to form a cycle.
    (a / "scaffld.yaml").write_text(f"name: a\nextends: ['{b.as_posix()}']\n", encoding="utf-8")
    with pytest.raises(ScaffldError):
        generate(str(a), tmp_path / "out", no_input=True)
