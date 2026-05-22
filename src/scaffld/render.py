"""Jinja2 environment and the file-tree rendering engine."""

from __future__ import annotations

import dataclasses
import ntpath
import os
from fnmatch import fnmatch
from pathlib import Path, PurePosixPath

import jinja2
from jinja2.sandbox import SandboxedEnvironment

from .errors import PathTraversalError, RenderError

RENDER_SUFFIXES = (".jinja", ".j2")


def _safe_relative(rel: str, *, where: str) -> PurePosixPath:
    """Validate that *rel* is a safe, destination-confined relative path.

    Template authors are untrusted, so a rendered file/dir name (or skip path)
    must never escape the destination directory. This rejects:

    * absolute POSIX paths (``/etc/x``);
    * Windows drive-relative / drive-absolute paths (``C:\\x``, ``C:x``);
    * UNC paths (``\\\\host\\share``);
    * any path containing a ``..`` segment;
    * empty or ``.``-only segments.

    Returns the normalized :class:`PurePosixPath`. Raises
    :class:`PathTraversalError` otherwise. This is the single choke point for the
    ZIP-SLIP / path-traversal class of attack (CWE-22/23).
    """
    raw = str(rel)
    # Normalize separators so a Windows-style "..\\x" is caught too.
    candidate = raw.replace("\\", "/")

    # Absolute POSIX path, or Windows drive / UNC forms.
    if candidate.startswith("/") or ntpath.isabs(raw) or ntpath.splitdrive(raw)[0]:
        raise PathTraversalError(
            f"Refusing to write outside the destination: {where} resolves to an "
            f"absolute path '{raw}'."
        )

    parts = [p for p in candidate.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        raise PathTraversalError(
            f"Refusing to write outside the destination: {where} contains a '..' "
            f"segment ('{raw}')."
        )
    if not parts:
        # Nothing meaningful to write (e.g. "." or ""): treat as empty.
        return PurePosixPath()
    return PurePosixPath(*parts)


def _slugify(value: str, sep: str = "-") -> str:
    out = []
    prev_sep = False
    for ch in str(value).strip().lower():
        if ch.isalnum():
            out.append(ch)
            prev_sep = False
        elif not prev_sep:
            out.append(sep)
            prev_sep = True
    return "".join(out).strip(sep)


def _snake(value: str) -> str:
    return _slugify(value, sep="_")


def _kebab(value: str) -> str:
    return _slugify(value, sep="-")


def _pascal(value: str) -> str:
    return "".join(part.capitalize() for part in _slugify(value, sep=" ").split())


def make_environment() -> jinja2.Environment:
    """Create the shared Jinja2 environment with scaffld's custom filters.

    Uses a :class:`~jinja2.sandbox.SandboxedEnvironment` because template authors
    are untrusted (templates are fetched from arbitrary git URLs). The sandbox
    blocks the standard SSTI escape chain (``__class__``/``__mro__``/
    ``__globals__`` etc.), preventing arbitrary code execution at render time.

    ``autoescape`` is intentionally ``False``: scaffld generates source code,
    TOML/YAML/INI, Dockerfiles, etc., where HTML escaping would corrupt output.
    Autoescaping is not the injection control here — the sandbox is.
    """
    env = SandboxedEnvironment(  # nosec B701 - codegen output; sandbox is the SSTI control
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    env.filters["slugify"] = _slugify
    env.filters["snake"] = _snake
    env.filters["snake_case"] = _snake
    env.filters["kebab"] = _kebab
    env.filters["kebab_case"] = _kebab
    env.filters["pascal"] = _pascal
    env.filters["pascal_case"] = _pascal
    env.filters["camel"] = lambda v: (lambda p: p[:1].lower() + p[1:])(_pascal(v))
    return env


def render_string(env: jinja2.Environment, text: str, context: dict, *, where: str = "") -> str:
    """Render a single string template against *context*."""
    try:
        return env.from_string(text).render(**context)
    except jinja2.TemplateError as exc:
        location = f" ({where})" if where else ""
        raise RenderError(f"Template error{location}: {exc}") from exc


def evaluate_condition(env: jinja2.Environment, expr: str, context: dict) -> bool:
    """Evaluate a Jinja boolean expression like ``not use_cli``."""
    try:
        compiled = env.compile_expression(expr)
        return bool(compiled(**context))
    except jinja2.TemplateError as exc:
        raise RenderError(f"Template error (condition '{expr}'): {exc}") from exc


def _is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            chunk = fh.read(8192)
    except OSError:
        return False
    return b"\x00" in chunk


@dataclasses.dataclass
class PlannedFile:
    """A single file the engine intends to write."""

    source: Path
    rel_target: PurePosixPath  # POSIX-style relative path within the destination
    is_binary: bool
    is_raw: bool
    rendered_content: str | None = None  # text content, None for binary/raw passthrough


@dataclasses.dataclass
class RenderPlan:
    """The full set of files and directories to materialize."""

    files: list = dataclasses.field(default_factory=list)
    dirs: list = dataclasses.field(default_factory=list)  # POSIX relative dirs (incl. empty)


def _strip_render_suffix(name: str) -> str:
    for suffix in RENDER_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _matches_raw(rel_posix: str, raw_globs: list) -> bool:
    return any(fnmatch(rel_posix, pat) for pat in raw_globs)


def build_plan(
    env: jinja2.Environment,
    template_dir: Path,
    context: dict,
    *,
    raw_globs: list | None = None,
    skip_paths: set | None = None,
) -> RenderPlan:
    """Walk *template_dir* and produce a :class:`RenderPlan`.

    File and directory *names* are rendered, file *contents* are rendered (unless raw
    or binary), the ``.jinja``/``.j2`` suffix is stripped, and *skip_paths* (already
    rendered, POSIX relative) are excluded.
    """
    template_dir = Path(template_dir)
    raw_globs = raw_globs or []
    skip_paths = skip_paths or set()
    plan = RenderPlan()

    for current_root, dirnames, filenames in os.walk(template_dir):
        current = Path(current_root)
        rel_root = current.relative_to(template_dir)

        # Render this directory's path segments.
        rendered_rel_parts: list = []
        for part in rel_root.parts:
            rendered = render_string(env, part, context, where=f"dir name '{part}'")
            # A rendered dir segment must itself be a single safe segment.
            safe_seg = _safe_relative(rendered, where=f"dir name '{part}'")
            rendered_rel_parts.append(safe_seg.as_posix())
        rendered_rel = (
            _safe_relative("/".join(rendered_rel_parts), where=f"dir path '{rel_root.as_posix()}'")
            if rendered_rel_parts
            else PurePosixPath()
        )
        rendered_rel_str = rendered_rel.as_posix()

        # Drop directories whose rendered name is empty (e.g. "{{ '' }}").
        dirnames[:] = [d for d in dirnames if d]

        # Record this (possibly empty) directory unless it is the template root.
        if rendered_rel_str not in {"", "."} and rendered_rel_str not in skip_paths:
            plan.dirs.append(rendered_rel_str)

        for filename in sorted(filenames):
            source = current / filename
            rendered_name = render_string(
                env, filename, context, where=f"file name '{filename}'"
            )
            if not rendered_name:
                continue
            # A rendered file name must be a single safe segment (no traversal,
            # not absolute, no embedded separators escaping the dir).
            safe_name = _safe_relative(
                rendered_name, where=f"file name '{filename}'"
            ).as_posix()
            if not safe_name:
                continue
            target_name = _strip_render_suffix(safe_name)
            had_render_suffix = target_name != safe_name
            rel_target = (
                (rendered_rel / target_name) if rendered_rel_str not in {"", "."} else PurePosixPath(target_name)
            )
            # Final defense-in-depth: re-validate the composed relative target.
            rel_target = _safe_relative(rel_target.as_posix(), where=f"output path '{rel_target.as_posix()}'")
            rel_target_str = rel_target.as_posix()
            if rel_target_str in skip_paths:
                continue
            # Skip if any parent directory is skipped.
            if any(rel_target_str == s or rel_target_str.startswith(s + "/") for s in skip_paths):
                continue

            is_binary = _is_binary(source)
            is_raw = _matches_raw(rel_target_str, raw_globs) or _matches_raw(
                rendered_rel.joinpath(filename).as_posix() if rendered_rel_str not in {"", "."} else filename,
                raw_globs,
            )

            if is_binary or (is_raw and not had_render_suffix):
                plan.files.append(
                    PlannedFile(
                        source=source,
                        rel_target=rel_target,
                        is_binary=is_binary,
                        is_raw=True,
                        rendered_content=None,
                    )
                )
                continue

            try:
                text = source.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                plan.files.append(
                    PlannedFile(
                        source=source,
                        rel_target=rel_target,
                        is_binary=True,
                        is_raw=True,
                        rendered_content=None,
                    )
                )
                continue

            rendered_content = render_string(
                env, text, context, where=f"content of '{rel_target_str}'"
            )
            plan.files.append(
                PlannedFile(
                    source=source,
                    rel_target=rel_target,
                    is_binary=False,
                    is_raw=False,
                    rendered_content=rendered_content,
                )
            )

    return plan


def _assert_within(dest_real: str, target: Path, *, where: str) -> None:
    """Ensure *target* resolves inside *dest_real* (realpath containment)."""
    resolved = os.path.realpath(str(target))
    # commonpath raises ValueError across drives on Windows — treat as escape.
    try:
        common = os.path.commonpath([dest_real, resolved])
    except ValueError:
        common = ""
    if common != dest_real:
        raise PathTraversalError(
            f"Refusing to write outside the destination: {where} resolves to "
            f"'{resolved}', which is outside '{dest_real}'."
        )


def write_plan(plan: RenderPlan, dest: Path) -> list:
    """Write a :class:`RenderPlan` to *dest*. Returns POSIX paths written.

    Every directory and file path is re-checked with ``realpath`` to guarantee it
    stays inside *dest* (defense-in-depth on top of :func:`_safe_relative`).
    """
    dest = Path(dest)
    written: list = []
    dest.mkdir(parents=True, exist_ok=True)
    dest_real = os.path.realpath(str(dest))

    for rel_dir in plan.dirs:
        target_dir = dest / rel_dir
        _assert_within(dest_real, target_dir, where=f"directory '{rel_dir}'")
        target_dir.mkdir(parents=True, exist_ok=True)

    for pf in plan.files:
        target = dest / Path(pf.rel_target)
        _assert_within(dest_real, target, where=f"file '{pf.rel_target.as_posix()}'")
        target.parent.mkdir(parents=True, exist_ok=True)
        if pf.rendered_content is None:
            # Binary or raw passthrough: copy bytes verbatim.
            target.write_bytes(pf.source.read_bytes())
        else:
            target.write_text(pf.rendered_content, encoding="utf-8", newline="")
        written.append(pf.rel_target.as_posix())
    return written


def resolve_skip_paths(env: jinja2.Environment, skip_rules: list, context: dict) -> set:
    """Render skip rules whose ``when`` is true into a set of POSIX relative paths."""
    paths: set = set()
    for rule in skip_rules:
        if evaluate_condition(env, rule.when, context):
            for raw in rule.paths:
                rendered = render_string(env, raw, context, where=f"skip path '{raw}'")
                if rendered:
                    safe = _safe_relative(rendered, where=f"skip path '{raw}'").as_posix()
                    if safe:
                        paths.add(safe)
    return paths
