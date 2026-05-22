"""Resolve a template reference to a local template directory.

Resolution order:
  1. Built-in template name shipped with the package.
  2. Local filesystem path to a template directory.
  3. Git URL (https / ssh / ``gh:user/repo`` / ``user/repo`` GitHub shorthand),
     with an optional ``#subdir`` and a git ref.
"""

from __future__ import annotations

import dataclasses
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

try:  # Python 3.9+: importlib.resources.files
    from importlib.resources import as_file, files
except ImportError:  # pragma: no cover
    from importlib_resources import as_file, files  # type: ignore

from .errors import TemplateNotFoundError
from .manifest import MANIFEST_NAMES

_GITHUB_SHORTHAND = re.compile(r"^[\w.-]+/[\w.-]+$")
_GIT_URL = re.compile(r"^(https?://|git@|ssh://|git://)")


@dataclasses.dataclass
class ResolvedTemplate:
    """A template resolved to a local directory, plus cleanup bookkeeping."""

    root: Path
    ref: str  # original reference string
    source: str  # "builtin" | "path" | "git"
    _cleanup: Path | None = None  # temp dir to remove when done

    def cleanup(self) -> None:
        if self._cleanup and self._cleanup.exists():
            shutil.rmtree(self._cleanup, ignore_errors=True)


def builtin_templates_root() -> Path:
    """Return the directory that holds shipped templates (filesystem path)."""
    resource = files("scaffld") / "templates"
    with as_file(resource) as path:
        return Path(path)


def list_builtin_templates() -> list:
    """Return the sorted names of built-in templates."""
    root = builtin_templates_root()
    if not root.is_dir():
        return []
    names = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and any((child / m).is_file() for m in MANIFEST_NAMES):
            names.append(child.name)
    return names


def _has_manifest(path: Path) -> bool:
    return any((path / m).is_file() for m in MANIFEST_NAMES)


def _is_bare_name(ref: str) -> bool:
    """True if *ref* looks like a plain built-in name (no path/URL separators)."""
    if not ref or ref in {".", ".."}:
        return False
    if any(sep in ref for sep in ("/", "\\")):
        return False
    if ":" in ref:  # drive letters (C:) or schemes (gh:)
        return False
    return True


def _resolve_builtin(ref: str) -> ResolvedTemplate | None:
    if not _is_bare_name(ref):
        return None
    candidate = builtin_templates_root() / ref
    if candidate.is_dir() and _has_manifest(candidate):
        return ResolvedTemplate(root=candidate, ref=ref, source="builtin")
    return None


def _resolve_path(ref: str) -> ResolvedTemplate | None:
    path = Path(ref).expanduser()
    if path.is_dir() and _has_manifest(path):
        return ResolvedTemplate(root=path.resolve(), ref=ref, source="path")
    return None


def _split_subdir(ref: str) -> tuple:
    if "#" in ref:
        url, subdir = ref.split("#", 1)
        return url, subdir
    return ref, ""


def _normalize_git_url(ref: str) -> str | None:
    if ref.startswith("gh:"):
        return f"https://github.com/{ref[3:]}"
    if _GIT_URL.match(ref):
        return ref
    if _GITHUB_SHORTHAND.match(ref) and not Path(ref).exists():
        return f"https://github.com/{ref}"
    return None


def _resolve_git(ref: str, git_ref: str | None) -> ResolvedTemplate:
    url_part, subdir = _split_subdir(ref)
    url = _normalize_git_url(url_part)
    if url is None:  # pragma: no cover - guarded by caller
        raise TemplateNotFoundError(f"'{ref}' is not a recognizable git URL.")
    if shutil.which("git") is None:
        raise TemplateNotFoundError(
            "git is required to fetch templates from a URL but was not found on PATH."
        )

    # Argument-injection hardening (CWE-88): a URL/ref/subdir starting with '-'
    # could be misread by git as an option. Reject those, and use '--' to end
    # option parsing so positionals can never be treated as flags.
    if url.startswith("-"):
        raise TemplateNotFoundError(f"Refusing to clone a URL that starts with '-': {url}")
    if git_ref is not None and git_ref.startswith("-"):
        raise TemplateNotFoundError(
            f"Refusing to use a git ref that starts with '-': {git_ref}"
        )
    if subdir.startswith("-") or subdir.startswith("/") or ".." in subdir.split("/"):
        raise TemplateNotFoundError(
            f"Refusing to use an unsafe subdir reference: '{subdir}'"
        )

    tmp = Path(tempfile.mkdtemp(prefix="scaffld-"))
    cmd = ["git", "clone", "--depth", "1"]
    if git_ref:
        cmd += ["--branch", git_ref]
    cmd += ["--", url, str(tmp)]
    try:
        subprocess.run(  # nosec B603 - argv list (no shell); inputs validated above
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        detail = (exc.stderr or "").strip().splitlines()
        msg = detail[-1] if detail else str(exc)
        raise TemplateNotFoundError(f"Failed to clone {url}: {msg}") from exc

    root = tmp / subdir if subdir else tmp
    if not root.is_dir() or not _has_manifest(root):
        shutil.rmtree(tmp, ignore_errors=True)
        where = f" (subdir '{subdir}')" if subdir else ""
        raise TemplateNotFoundError(
            f"No scaffld.yaml found in cloned repository{where}: {url}"
        )
    return ResolvedTemplate(root=root.resolve(), ref=ref, source="git", _cleanup=tmp)


def resolve_template(ref: str, *, git_ref: str | None = None) -> ResolvedTemplate:
    """Resolve *ref* to a local template directory."""
    builtin = _resolve_builtin(ref)
    if builtin is not None:
        return builtin

    local = _resolve_path(ref)
    if local is not None:
        return local

    if _normalize_git_url(_split_subdir(ref)[0]) is not None:
        return _resolve_git(ref, git_ref)

    available = ", ".join(list_builtin_templates()) or "(none)"
    raise TemplateNotFoundError(
        f"Could not resolve template '{ref}'. It is not a built-in template, "
        f"an existing local path, or a git URL.\nBuilt-in templates: {available}."
    )
