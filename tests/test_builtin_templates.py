"""End-to-end checks that every shipped template renders to a valid tree."""

import pytest

from scaffld.generator import generate
from scaffld.resolver import list_builtin_templates


def test_all_builtins_have_manifests():
    names = list_builtin_templates()
    assert {"python-package", "cli-app", "static-site"} <= set(names)


def test_python_package_full(tmp_path):
    dest = tmp_path / "pkg"
    result = generate(
        "python-package",
        dest,
        overrides={
            "project_name": "Acme Lib",
            "package_name": "acme_lib",
            "use_cli": "true",
            "license": "MIT",
            "author": "Tester",
        },
        no_input=True,
        run_post_hooks=False,
    )
    files = set(result.files)
    assert "pyproject.toml" in files
    assert "src/acme_lib/__init__.py" in files
    assert "src/acme_lib/cli.py" in files
    assert "LICENSE" in files
    pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "acme-lib"' in pyproject
    assert "typer" in pyproject  # CLI dependency added
    license_text = (dest / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in license_text
    assert "Tester" in license_text


def test_python_package_no_cli_no_license(tmp_path):
    dest = tmp_path / "pkg"
    result = generate(
        "python-package",
        dest,
        overrides={"package_name": "plain", "use_cli": "false", "license": "None"},
        no_input=True,
        run_post_hooks=False,
    )
    files = set(result.files)
    assert "src/plain/cli.py" not in files
    assert "LICENSE" not in files


def test_cli_app_renders(tmp_path):
    dest = tmp_path / "app"
    result = generate(
        "cli-app",
        dest,
        overrides={"app_name": "Todo", "command": "todo", "author": "T"},
        no_input=True,
        run_post_hooks=False,
    )
    assert "src/todo/cli.py" in set(result.files)
    pyproject = (dest / "pyproject.toml").read_text(encoding="utf-8")
    assert "todo = " in pyproject
    cli = (dest / "src" / "todo" / "cli.py").read_text(encoding="utf-8")
    assert "import typer" in cli


def test_static_site_renders(tmp_path):
    dest = tmp_path / "site"
    result = generate(
        "static-site",
        dest,
        overrides={"site_title": "Blog", "accent": "#ff0000", "deploy_pages": "true"},
        no_input=True,
        run_post_hooks=False,
    )
    files = set(result.files)
    assert "index.html" in files
    assert "style.css" in files
    assert ".github/workflows/pages.yml" in files
    html = (dest / "index.html").read_text(encoding="utf-8")
    assert "<title>Blog</title>" in html
    css = (dest / "style.css").read_text(encoding="utf-8")
    assert "#ff0000" in css


def test_static_site_no_pages(tmp_path):
    dest = tmp_path / "site"
    result = generate(
        "static-site",
        dest,
        overrides={"site_title": "Blog", "deploy_pages": "false"},
        no_input=True,
        run_post_hooks=False,
    )
    assert ".github/workflows/pages.yml" not in set(result.files)


@pytest.mark.parametrize("name", ["python-package", "cli-app", "static-site"])
def test_builtin_dry_run(name, tmp_path):
    result = generate(name, tmp_path / "x", no_input=True, dry_run=True)
    assert result.files
    assert result.dry_run
