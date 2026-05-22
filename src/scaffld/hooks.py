"""Cross-platform execution of post-generation hooks."""

from __future__ import annotations

import dataclasses
import subprocess
from pathlib import Path

import jinja2

from .errors import HookError
from .render import evaluate_condition, render_string


@dataclasses.dataclass
class PlannedHook:
    """A hook that has been resolved (command rendered, condition evaluated)."""

    name: str
    command: str
    will_run: bool


def plan_hooks(env: jinja2.Environment, hooks: list, context: dict) -> list:
    """Render each hook command and evaluate its ``when`` condition."""
    planned: list = []
    for hook in hooks:
        command = render_string(env, hook.run, context, where=f"hook '{hook.name}'")
        will_run = evaluate_condition(env, hook.when, context)
        planned.append(PlannedHook(name=hook.name, command=command, will_run=will_run))
    return planned


def run_hooks(planned: list, cwd: Path, *, echo=None) -> None:
    """Run planned hooks (those with ``will_run``) in *cwd*.

    Each command is executed through the platform shell so that user-authored
    hooks behave the same way they would when typed into a terminal (so a single
    ``run:`` line with ``&&``/pipes works across platforms). We rely on the shell
    only for parsing; commands run with ``cwd`` set to the output dir.

    SECURITY: hook commands come from an *untrusted* template manifest and are
    arbitrary code. The protection boundary is **explicit user consent** enforced
    by the caller (the CLI prompts before this function is ever reached) — not
    argument parsing. Never call this with hooks the user has not approved.
    """
    cwd = Path(cwd)
    for hook in planned:
        if not hook.will_run:
            continue
        if echo is not None:
            echo(hook)
        try:
            result = subprocess.run(  # nosec B602 - by design; gated behind explicit consent
                hook.command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                text=True,
            )
        except OSError as exc:  # pragma: no cover - platform dependent
            raise HookError(f"Hook '{hook.name}' could not start: {exc}") from exc
        if result.returncode != 0:
            stderr = (result.stderr or result.stdout or "").strip()
            raise HookError(
                f"Hook '{hook.name}' failed (exit {result.returncode}): "
                f"{hook.command}\n{stderr}"
            )


def hooks_from(env: jinja2.Environment, hooks: list, context: dict) -> list | None:
    """Convenience wrapper returning planned hooks or ``None`` when empty."""
    if not hooks:
        return None
    return plan_hooks(env, hooks, context)
