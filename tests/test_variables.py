import pytest

from scaffld.errors import VariableError
from scaffld.manifest import Variable
from scaffld.render import make_environment
from scaffld.variables import coerce, parse_var_flags, resolve_context


def test_parse_var_flags():
    assert parse_var_flags(["a=1", "b=hello world"]) == {"a": "1", "b": "hello world"}


def test_parse_var_flags_value_with_equals():
    assert parse_var_flags(["k=a=b"]) == {"k": "a=b"}


def test_parse_var_flags_invalid():
    with pytest.raises(VariableError):
        parse_var_flags(["noequals"])


def test_coerce_bool():
    v = Variable(name="x", type="bool")
    assert coerce(v, "true") is True
    assert coerce(v, "no") is False
    assert coerce(v, True) is True


def test_coerce_bool_invalid():
    with pytest.raises(VariableError):
        coerce(Variable(name="x", type="bool"), "maybe")


def test_coerce_int():
    assert coerce(Variable(name="x", type="int"), "42") == 42
    with pytest.raises(VariableError):
        coerce(Variable(name="x", type="int"), "nope")


def test_coerce_choice():
    v = Variable(name="x", type="choice", choices=["a", "b"])
    assert coerce(v, "a") == "a"
    with pytest.raises(VariableError):
        coerce(v, "c")


def test_coerce_multichoice_from_csv():
    v = Variable(name="x", type="multichoice", choices=["a", "b", "c"])
    assert coerce(v, "a,c") == ["a", "c"]
    with pytest.raises(VariableError):
        coerce(v, "a,z")


def test_resolve_context_defaults_only():
    env = make_environment()
    variables = [
        Variable(name="name", type="str", default="Demo"),
        Variable(name="slug", type="str", default="{{ name | snake }}"),
    ]
    ctx = resolve_context(env, variables, no_input=True)
    assert ctx == {"name": "Demo", "slug": "demo"}


def test_resolve_context_override_wins():
    env = make_environment()
    variables = [Variable(name="name", type="str", default="Demo")]
    ctx = resolve_context(env, variables, overrides={"name": "Other"}, no_input=True)
    assert ctx["name"] == "Other"


def test_resolve_context_computed_default_uses_override():
    env = make_environment()
    variables = [
        Variable(name="name", type="str", default="Demo"),
        Variable(name="slug", type="str", default="{{ name | kebab }}"),
    ]
    ctx = resolve_context(env, variables, overrides={"name": "Cool App"}, no_input=True)
    assert ctx["slug"] == "cool-app"


def test_resolve_context_bool_default():
    env = make_environment()
    variables = [Variable(name="flag", type="bool")]
    ctx = resolve_context(env, variables, no_input=True)
    assert ctx["flag"] is False


def test_unknown_override_passed_through():
    env = make_environment()
    ctx = resolve_context(env, [], overrides={"extra": "v"}, no_input=True)
    assert ctx["extra"] == "v"
