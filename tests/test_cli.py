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


def _consent_template(tmp_path):
    """A local template with one harmless post-gen hook that writes a marker."""
    import sys

    import yaml

    py = sys.executable.replace("\\", "/")
    script = tmp_path / "marker.py"
    script.write_text(
        "import pathlib; pathlib.Path('ran.txt').write_text('1')\n", encoding="utf-8"
    )
    root = tmp_path / "tpl"
    (root / "template").mkdir(parents=True)
    (root / "template" / "a.txt").write_text("x", encoding="utf-8")
    manifest = yaml.safe_dump(
        {
            "name": "consent-tpl",
            "hooks": {
                "post_gen": [
                    {"name": "marker", "run": f'"{py}" "{script.as_posix()}"'}
                ]
            },
        }
    )
    (root / "scaffld.yaml").write_text(manifest, encoding="utf-8")
    return root


def test_hooks_require_consent_declined(tmp_path):
    root = _consent_template(tmp_path)
    dest = tmp_path / "out"
    # Answer "n" to the consent prompt: project is written, hook is NOT run.
    result = runner.invoke(app, ["new", str(root), str(dest)], input="n\n")
    assert result.exit_code == 0, result.stdout
    assert (dest / "a.txt").is_file()
    assert not (dest / "ran.txt").exists()


def test_hooks_run_with_consent(tmp_path):
    root = _consent_template(tmp_path)
    dest = tmp_path / "out"
    result = runner.invoke(app, ["new", str(root), str(dest)], input="y\n")
    assert result.exit_code == 0, result.stdout
    assert (dest / "ran.txt").is_file()


def test_hooks_run_with_yes_flag(tmp_path):
    root = _consent_template(tmp_path)
    dest = tmp_path / "out"
    result = runner.invoke(app, ["new", str(root), str(dest), "--yes"])
    assert result.exit_code == 0, result.stdout
    assert (dest / "ran.txt").is_file()


def test_hooks_skipped_in_no_input_without_yes(tmp_path):
    root = _consent_template(tmp_path)
    dest = tmp_path / "out"
    result = runner.invoke(app, ["new", str(root), str(dest), "--no-input"])
    assert result.exit_code == 0, result.stdout
    assert (dest / "a.txt").is_file()
    assert not (dest / "ran.txt").exists()


def test_no_hooks_overrides_yes(tmp_path):
    root = _consent_template(tmp_path)
    dest = tmp_path / "out"
    result = runner.invoke(
        app, ["new", str(root), str(dest), "--yes", "--no-hooks"]
    )
    assert result.exit_code == 0, result.stdout
    assert not (dest / "ran.txt").exists()


def test_cli_rejects_path_traversal_template(tmp_path):
    """A template whose rendered file name escapes dest is rejected at the CLI.

    Uses a variable default carrying the traversal so the malicious name is
    produced at *render* time (cross-platform; a literal '../' in a real on-disk
    filename is not portable to Windows checkouts).
    """
    import yaml

    root = tmp_path / "evil"
    (root / "template").mkdir(parents=True)
    # File name renders to "../../../escaped.txt".
    (root / "template" / "{{ evil }}.txt").write_text("pwn", encoding="utf-8")
    (root / "scaffld.yaml").write_text(
        yaml.safe_dump(
            {"name": "evil", "variables": {"evil": {"default": "../../../escaped"}}}
        ),
        encoding="utf-8",
    )
    dest = tmp_path / "out"
    result = runner.invoke(app, ["new", str(root), str(dest), "--no-input"])
    assert result.exit_code == 1
    assert not (tmp_path / "escaped.txt").exists()


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
