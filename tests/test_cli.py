from typer.testing import CliRunner

from scaffld import __version__
from scaffld.cli import app

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_list():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "python-package" in result.stdout


def test_info():
    result = runner.invoke(app, ["info", "python-package"])
    assert result.exit_code == 0
    assert "project_name" in result.stdout


def test_new_dry_run():
    result = runner.invoke(
        app,
        ["new", "python-package", "--dry-run", "--no-input", "--var", "project_name=Demo"],
    )
    assert result.exit_code == 0
    assert "pyproject.toml" in result.stdout


def test_new_writes(tmp_path):
    dest = tmp_path / "proj"
    result = runner.invoke(
        app,
        [
            "new",
            "python-package",
            str(dest),
            "--no-input",
            "--no-hooks",
            "--var",
            "project_name=Demo",
            "--var",
            "package_name=demo",
            "--var",
            "use_cli=false",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert (dest / "pyproject.toml").is_file()
    assert (dest / "src" / "demo" / "__init__.py").is_file()
    assert not (dest / "src" / "demo" / "cli.py").exists()


def test_new_unknown_template_errors():
    result = runner.invoke(app, ["new", "nope-not-real", "--no-input"])
    assert result.exit_code == 1


def test_new_bad_var_errors():
    result = runner.invoke(app, ["new", "python-package", "--no-input", "--var", "broken"])
    assert result.exit_code == 1


def test_new_collision_without_force(tmp_path):
    dest = tmp_path / "proj"
    args = [
        "new",
        "cli-app",
        str(dest),
        "--no-input",
        "--no-hooks",
        "--var",
        "app_name=Demo",
        "--var",
        "command=demo",
    ]
    first = runner.invoke(app, args)
    assert first.exit_code == 0
    second = runner.invoke(app, args)
    assert second.exit_code == 1
    third = runner.invoke(app, args + ["--force"])
    assert third.exit_code == 0
