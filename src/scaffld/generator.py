"""High-level orchestration: resolve, compose, render, write, run hooks."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Callable

from .errors import OutputExistsError, ScaffldError
from .hooks import plan_hooks, run_hooks
from .manifest import Manifest, load_manifest
from .render import (
    RenderPlan,
    build_plan,
    make_environment,
    resolve_skip_paths,
    write_plan,
)
from .resolver import ResolvedTemplate, resolve_template
from .variables import Prompter, resolve_context


@dataclasses.dataclass
class GenerationResult:
    """The outcome of a (dry-run or real) generation."""

    dest: Path
    template_name: str
    context: dict
    files: list  # POSIX relative paths
    dirs: list
    hooks: list  # list[PlannedHook]
    dry_run: bool


@dataclasses.dataclass
class _Layer:
    manifest: Manifest
    resolved: ResolvedTemplate


def _collect_layers(
    ref: str,
    *,
    git_ref: str | None,
    _seen: set | None = None,
) -> list:
    """Resolve *ref* and its ``extends`` chain into ordered layers.

    Base layers (from ``extends``) come first, the named template last, so the
    named template can override base files. Cycles are guarded against.
    """
    _seen = _seen if _seen is not None else set()
    if ref in _seen:
        raise ScaffldError(f"Circular template composition detected at '{ref}'.")
    _seen.add(ref)

    resolved = resolve_template(ref, git_ref=git_ref)
    manifest = load_manifest(resolved.root)

    layers: list = []
    for parent_ref in manifest.extends:
        layers.extend(_collect_layers(parent_ref, git_ref=git_ref, _seen=_seen))
    layers.append(_Layer(manifest=manifest, resolved=resolved))
    return layers


def _merge_variables(layers: list) -> list:
    """Merge variable definitions across layers (later layers win, order kept)."""
    merged: dict = {}
    for layer in layers:
        for var in layer.manifest.variables:
            merged[var.name] = var  # later layer overrides earlier definition
    return list(merged.values())


def generate(
    ref: str,
    dest: Path,
    *,
    overrides: dict | None = None,
    no_input: bool = False,
    dry_run: bool = False,
    force: bool = False,
    run_post_hooks: bool = True,
    git_ref: str | None = None,
    prompter: Prompter | None = None,
    hook_echo: Callable | None = None,
    hook_consent: Callable | None = None,
) -> GenerationResult:
    """Generate a project from *ref* into *dest*.

    Composition: every template in the ``extends`` chain is rendered in order
    into the same destination, sharing one variable context.

    SECURITY — post-generation hooks run arbitrary shell commands from the
    (untrusted) template manifest. They run only when *both* ``run_post_hooks``
    is true *and* ``hook_consent`` (if provided) returns truthy for the planned
    hooks. ``hook_consent`` is called as ``hook_consent(planned_hooks)`` after the
    project is written but before any command executes. If ``hook_consent`` is
    ``None`` the legacy behavior (run when ``run_post_hooks``) applies — callers
    that handle untrusted input MUST pass a consent callback (the shipped CLI
    always does).
    """
    dest = Path(dest)
    env = make_environment()
    layers = _collect_layers(ref, git_ref=git_ref)
    try:
        variables = _merge_variables(layers)
        context = resolve_context(
            env,
            variables,
            overrides=overrides,
            prompter=prompter,
            no_input=no_input,
        )
        context.setdefault("dest_name", dest.name)

        # Build a combined plan across all layers.
        combined = RenderPlan()
        seen_files: dict = {}
        seen_dirs: set = set()
        for layer in layers:
            skip_paths = resolve_skip_paths(env, layer.manifest.skip, context)
            plan = build_plan(
                env,
                layer.manifest.template_dir,
                context,
                raw_globs=layer.manifest.raw_globs,
                skip_paths=skip_paths,
            )
            for d in plan.dirs:
                if d not in seen_dirs:
                    seen_dirs.add(d)
                    combined.dirs.append(d)
            for pf in plan.files:
                key = pf.rel_target.as_posix()
                if key in seen_files:
                    combined.files[seen_files[key]] = pf  # later layer overrides
                else:
                    seen_files[key] = len(combined.files)
                    combined.files.append(pf)

        # Collect hooks from all layers, planned in order.
        all_hooks = []
        for layer in layers:
            all_hooks.extend(layer.manifest.post_gen)
        planned_hooks: list = plan_hooks(env, all_hooks, context)

        template_name = layers[-1].manifest.name
        rel_files = [pf.rel_target.as_posix() for pf in combined.files]

        if dry_run:
            return GenerationResult(
                dest=dest,
                template_name=template_name,
                context=context,
                files=sorted(rel_files),
                dirs=sorted(combined.dirs),
                hooks=planned_hooks,
                dry_run=True,
            )

        _check_collisions(dest, rel_files, force)
        write_plan(combined, dest)

        if run_post_hooks and planned_hooks:
            runnable = [h for h in planned_hooks if h.will_run]
            consented = True
            if runnable and hook_consent is not None:
                consented = bool(hook_consent(runnable))
            if consented:
                run_hooks(planned_hooks, dest, echo=hook_echo)

        return GenerationResult(
            dest=dest,
            template_name=template_name,
            context=context,
            files=sorted(rel_files),
            dirs=sorted(combined.dirs),
            hooks=planned_hooks,
            dry_run=False,
        )
    finally:
        for layer in layers:
            layer.resolved.cleanup()


def _check_collisions(dest: Path, rel_files: list, force: bool) -> None:
    if force:
        return
    existing = [rel for rel in rel_files if (dest / Path(rel)).exists()]
    if existing:
        sample = ", ".join(sorted(existing)[:5])
        more = "" if len(existing) <= 5 else f" (+{len(existing) - 5} more)"
        raise OutputExistsError(
            f"{len(existing)} file(s) already exist in {dest}: {sample}{more}. "
            f"Use --force to overwrite."
        )


def describe(ref: str, *, git_ref: str | None = None) -> Manifest:
    """Resolve and load a template's manifest (for ``scaffld info``)."""
    resolved = resolve_template(ref, git_ref=git_ref)
    try:
        return load_manifest(resolved.root)
    finally:
        resolved.cleanup()
