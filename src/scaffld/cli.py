"""The ``scaffld`` command-line interface (Typer)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from . import __version__
from .console import SYMBOLS, console, error, success
from .errors import ScaffldError
from .generator import GenerationResult, describe, generate
from .resolver import list_builtin_templates
from .variables import Prompter, parse_var_flags

app = typer.Typer(
    name="scaffld",
    help="Scaffold projects from composable templates with variables and hooks.",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"scaffld {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show the version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """scaffld — scaffold projects from composable templates."""


def _build_tree(result: GenerationResult) -> Tree:
    root_label = f"[scaffld.path]{result.dest.name or result.dest}/[/]"
    tree = Tree(root_label, guide_style="scaffld.dim")
    nodes: dict = {(): tree}

    def ensure_dir(parts: tuple) -> Tree:
        if parts in nodes:
            return nodes[parts]
        parent = ensure_dir(parts[:-1])
        node = parent.add(f"[scaffld.path]{parts[-1]}/[/]")
        nodes[parts] = node
        return node

    for rel in sorted(set(result.dirs) | {str(Path(f).parent).replace("\\", "/") for f in result.files}):
        if rel in {"", "."}:
            continue
        ensure_dir(tuple(rel.split("/")))

    for rel in sorted(result.files):
        parts = tuple(rel.split("/"))
        parent = ensure_dir(parts[:-1]) if len(parts) > 1 else tree
        parent.add(f"[scaffld.add]{parts[-1]}[/]")
    return tree


def _print_result(result: GenerationResult, *, dry_run: bool) -> None:
    title = "Dry run — nothing was written" if dry_run else "Generated"
    console.print()
    console.print(
        Panel(
            _build_tree(result),
            title=f"[scaffld.title]{title}[/] [scaffld.dim]({result.template_name})[/]",
            border_style="scaffld.accent",
            expand=False,
        )
    )
    if result.hooks:
        console.print("[scaffld.title]Hooks:[/]")
        for hook in result.hooks:
            marker = "[scaffld.add]run[/]" if hook.will_run else "[scaffld.skip]skip[/]"
            verb = "would run" if dry_run and hook.will_run else ""
            console.print(
                f"  [{marker}] {hook.name} [scaffld.dim]{SYMBOLS['arrow']} {hook.command}[/] {verb}".rstrip()
            )
    console.print()


def _hook_echo(hook) -> None:
    console.print(
        f"  [scaffld.accent]{SYMBOLS['arrow']}[/] {hook.name}: [scaffld.dim]{hook.command}[/]"
    )


def _make_hook_consent(*, assume_yes: bool, no_input: bool):
    """Build the consent callback the generator calls before running hooks.

    SECURITY: post-gen hooks are arbitrary shell commands from an untrusted
    template, so they require explicit consent.

    * ``--yes`` grants consent non-interactively.
    * ``--no-input`` (CI) WITHOUT ``--yes`` declines — automation never runs
      untrusted commands implicitly.
    * Otherwise, the exact commands are shown and the user is asked to confirm
      (declining still writes the project, just skips the commands).
    """

    def consent(runnable: list) -> bool:
        console.print()
        console.print(
            f"[scaffld.warn]{SYMBOLS['warn']}[/] This template wants to run "
            f"{len(runnable)} post-generation command(s) on your machine:"
        )
        for hook in runnable:
            console.print(
                f"  [scaffld.accent]{SYMBOLS['arrow']}[/] {hook.name}: "
                f"[scaffld.dim]{hook.command}[/]"
            )
        if assume_yes:
            return True
        if no_input:
            console.print(
                "[scaffld.warn]Skipping hooks[/] (non-interactive; pass "
                "[scaffld.accent]--yes[/] to run them)."
            )
            return False
        console.print(
            "[scaffld.dim]Only run hooks from templates you trust.[/]"
        )
        try:
            return typer.confirm("Run these commands?", default=False)
        except (EOFError, KeyboardInterrupt):  # pragma: no cover - interactive
            return False

    return consent


@app.command()
def new(
    template: str = typer.Argument(
        ..., help="Built-in name, local path, or git URL (gh:user/repo, user/repo, https://…)."
    ),
    dest: Path | None = typer.Argument(
        None, help="Destination directory (default: current directory)."
    ),
    var: list[str] = typer.Option(
        None, "--var", "-v", help="Set a variable, e.g. --var name=demo. Repeatable.", metavar="KEY=VALUE"
    ),
    no_input: bool = typer.Option(
        False, "--no-input", help="Never prompt; use defaults and --var (CI mode)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview the output tree and hooks without writing."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite files that already exist."
    ),
    no_hooks: bool = typer.Option(
        False, "--no-hooks", help="Do not run post-generation hooks."
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Consent to run post-generation hooks without prompting (I trust this template).",
    ),
    ref: str | None = typer.Option(
        None, "--ref", help="Git branch/tag for git URL templates."
    ),
) -> None:
    """Generate a project from a template."""
    destination = Path(dest) if dest is not None else Path.cwd()
    try:
        overrides = parse_var_flags(var)
        result = generate(
            template,
            destination,
            overrides=overrides,
            no_input=no_input,
            dry_run=dry_run,
            force=force,
            run_post_hooks=not no_hooks,
            git_ref=ref,
            prompter=None if no_input else Prompter(),
            hook_echo=_hook_echo,
            hook_consent=_make_hook_consent(assume_yes=yes, no_input=no_input),
        )
    except ScaffldError as exc:
        error(str(exc))
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:  # pragma: no cover
        error("Aborted.")
        raise typer.Exit(code=130) from None

    _print_result(result, dry_run=dry_run)
    if not dry_run:
        success(f"Created [scaffld.path]{result.dest}[/] from [scaffld.accent]{result.template_name}[/]")


@app.command("list")
def list_templates() -> None:
    """List the built-in templates."""
    names = list_builtin_templates()
    if not names:
        console.print("[scaffld.warn]No built-in templates found.[/]")
        return
    table = Table(title="Built-in templates", border_style="scaffld.accent", title_style="scaffld.title")
    table.add_column("Name", style="scaffld.accent", no_wrap=True)
    table.add_column("Description")
    for name in names:
        try:
            manifest = describe(name)
            desc = manifest.description
        except ScaffldError:
            desc = ""
        table.add_row(name, desc)
    console.print(table)


@app.command()
def info(
    template: str = typer.Argument(..., help="Template name, path, or git URL."),
    ref: str | None = typer.Option(None, "--ref", help="Git branch/tag for git templates."),
) -> None:
    """Show a template's variables and hooks."""
    try:
        manifest = describe(template, git_ref=ref)
    except ScaffldError as exc:
        error(str(exc))
        raise typer.Exit(code=1) from exc

    console.print(
        Panel(
            manifest.description or "[scaffld.dim](no description)[/]",
            title=f"[scaffld.title]{manifest.name}[/]",
            border_style="scaffld.accent",
            expand=False,
        )
    )

    if manifest.variables:
        table = Table(title="Variables", border_style="scaffld.accent", title_style="scaffld.title")
        table.add_column("Name", style="scaffld.accent", no_wrap=True)
        table.add_column("Type")
        table.add_column("Default")
        table.add_column("Choices")
        for v in manifest.variables:
            table.add_row(
                v.name,
                v.normalized_type(),
                "" if v.default is None else str(v.default),
                ", ".join(str(c) for c in v.choices) if v.choices else "",
            )
        console.print(table)
    else:
        console.print("[scaffld.dim]No variables.[/]")

    if manifest.extends:
        console.print(f"[scaffld.title]Extends:[/] {', '.join(manifest.extends)}")

    if manifest.post_gen:
        console.print("[scaffld.title]Post-gen hooks:[/]")
        for hook in manifest.post_gen:
            cond = "" if hook.when in {"true", "True"} else f" [scaffld.dim](when: {hook.when})[/]"
            console.print(f"  {SYMBOLS['bullet']} {hook.name}: [scaffld.dim]{hook.run}[/]{cond}")


if __name__ == "__main__":  # pragma: no cover
    app()
