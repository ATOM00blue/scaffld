import pytest

from scaffld.errors import ManifestError
from scaffld.manifest import load_manifest, parse_manifest_data


def test_parse_minimal():
    m = parse_manifest_data({"name": "demo", "description": "d"})
    assert m.name == "demo"
    assert m.description == "d"
    assert m.variables == []
    assert m.post_gen == []


def test_parse_variables_mapping():
    m = parse_manifest_data(
        {
            "name": "t",
            "variables": {
                "project": {"type": "str", "prompt": "P", "default": "x"},
                "flag": {"type": "bool", "default": True},
            },
        }
    )
    names = [v.name for v in m.variables]
    assert names == ["project", "flag"]
    assert m.variables[0].prompt == "P"
    assert m.variables[1].normalized_type() == "bool"


def test_variable_shorthand_default():
    m = parse_manifest_data({"name": "t", "variables": {"x": "hello"}})
    assert m.variables[0].name == "x"
    assert m.variables[0].default == "hello"
    assert m.variables[0].normalized_type() == "str"


def test_choice_requires_choices():
    with pytest.raises(ManifestError):
        parse_manifest_data({"name": "t", "variables": {"x": {"type": "choice"}}})


def test_unknown_type_rejected():
    with pytest.raises(ManifestError):
        parse_manifest_data({"name": "t", "variables": {"x": {"type": "weird"}}})


def test_parse_hooks_and_skip():
    m = parse_manifest_data(
        {
            "name": "t",
            "skip": [{"when": "not x", "paths": ["a.py"]}],
            "hooks": {"post_gen": [{"name": "init", "run": "git init", "when": "true"}]},
        }
    )
    assert m.skip[0].when == "not x"
    assert m.skip[0].paths == ["a.py"]
    assert m.post_gen[0].name == "init"
    assert m.post_gen[0].run == "git init"


def test_hook_string_shorthand():
    m = parse_manifest_data({"name": "t", "hooks": {"post_gen": ["echo hi"]}})
    assert m.post_gen[0].run == "echo hi"
    assert m.post_gen[0].when == "true"


def test_extends_string_coerced_to_list():
    m = parse_manifest_data({"name": "t", "extends": "base"})
    assert m.extends == ["base"]


def test_load_manifest_missing(tmp_path):
    with pytest.raises(ManifestError):
        load_manifest(tmp_path)


def test_load_manifest_roundtrip(make_template):
    root = make_template(manifest="name: rt\ndescription: hi\n", files={})
    m = load_manifest(root)
    assert m.name == "rt"
    assert m.root == root


def test_template_dir_prefers_nested(make_template):
    root = make_template(
        manifest="name: t\n", files={"template/a.txt": "x"}
    )
    assert m_dir(root).name == "template"


def m_dir(root):
    return load_manifest(root).template_dir
