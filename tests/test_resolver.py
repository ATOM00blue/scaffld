import pytest

from scaffld.errors import TemplateNotFoundError
from scaffld.resolver import (
    _normalize_git_url,
    _split_subdir,
    list_builtin_templates,
    resolve_template,
)


def test_list_builtin_templates():
    names = list_builtin_templates()
    assert "python-package" in names
    assert "cli-app" in names
    assert "static-site" in names


def test_resolve_builtin():
    rt = resolve_template("python-package")
    try:
        assert rt.source == "builtin"
        assert (rt.root / "scaffld.yaml").is_file()
    finally:
        rt.cleanup()


def test_resolve_local_path(make_template):
    root = make_template(manifest="name: local\n", files={"template/a.txt": "hi"})
    rt = resolve_template(str(root))
    try:
        assert rt.source == "path"
        assert rt.root == root.resolve()
    finally:
        rt.cleanup()


def test_resolve_unknown_raises():
    with pytest.raises(TemplateNotFoundError):
        resolve_template("definitely-not-a-real-template-xyz")


def test_normalize_git_url():
    assert _normalize_git_url("gh:user/repo") == "https://github.com/user/repo"
    assert _normalize_git_url("https://x.com/a.git") == "https://x.com/a.git"
    assert _normalize_git_url("git@github.com:u/r.git") == "git@github.com:u/r.git"
    assert _normalize_git_url("user/repo") == "https://github.com/user/repo"
    assert _normalize_git_url("just-a-name") is None


def test_split_subdir():
    assert _split_subdir("https://x/y#sub/dir") == ("https://x/y", "sub/dir")
    assert _split_subdir("https://x/y") == ("https://x/y", "")
