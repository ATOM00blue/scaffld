"""Loading and validation of the ``scaffld.yaml`` template manifest."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml

from .errors import ManifestError

MANIFEST_NAMES = ("scaffld.yaml", "scaffld.yml")
TEMPLATE_DIR_NAME = "template"

VALID_VAR_TYPES = {"str", "string", "bool", "boolean", "int", "integer", "choice", "multichoice"}


@dataclasses.dataclass
class Variable:
    """A single template variable definition."""

    name: str
    type: str = "str"
    prompt: str | None = None
    default: Any = None
    choices: list | None = None
    help: str | None = None

    def normalized_type(self) -> str:
        aliases = {"string": "str", "boolean": "bool", "integer": "int"}
        return aliases.get(self.type, self.type)


@dataclasses.dataclass
class SkipRule:
    """A conditional rule that removes paths from the rendered output."""

    when: str
    paths: list


@dataclasses.dataclass
class Hook:
    """A post-generation command to run in the output directory."""

    name: str
    run: str
    when: str = "true"


@dataclasses.dataclass
class Manifest:
    """A fully-parsed template manifest."""

    name: str
    description: str = ""
    variables: list = dataclasses.field(default_factory=list)
    extends: list = dataclasses.field(default_factory=list)
    skip: list = dataclasses.field(default_factory=list)
    post_gen: list = dataclasses.field(default_factory=list)
    raw_globs: list = dataclasses.field(default_factory=list)
    # Filesystem location of the template root (dir containing scaffld.yaml).
    root: Path | None = None

    @property
    def template_dir(self) -> Path:
        """Directory whose contents are rendered into the destination."""
        if self.root is None:
            raise ManifestError("Manifest has no resolved root directory.")
        nested = self.root / TEMPLATE_DIR_NAME
        return nested if nested.is_dir() else self.root


def find_manifest(root: Path) -> Path:
    """Return the manifest path inside *root*, or raise :class:`ManifestError`."""
    for name in MANIFEST_NAMES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    raise ManifestError(
        f"No scaffld.yaml found in {root}. A template directory must contain a "
        f"scaffld.yaml manifest."
    )


def _parse_variables(raw: Any) -> list:
    if raw is None:
        return []
    variables: list = []
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        # Allow a list of single-key dicts to preserve order explicitly.
        items = []
        for entry in raw:
            if not isinstance(entry, dict) or len(entry) != 1:
                raise ManifestError(
                    "Each variable in a list form must be a single-key mapping."
                )
            items.append(next(iter(entry.items())))
    else:
        raise ManifestError("'variables' must be a mapping or a list of mappings.")

    for key, spec in items:
        if spec is None:
            spec = {}
        if not isinstance(spec, dict):
            # Shorthand: ``name: default_value``.
            spec = {"default": spec}
        vtype = str(spec.get("type", "str"))
        if vtype not in VALID_VAR_TYPES:
            raise ManifestError(
                f"Variable '{key}' has unknown type '{vtype}'. "
                f"Valid types: {', '.join(sorted(VALID_VAR_TYPES))}."
            )
        choices = spec.get("choices")
        if vtype in {"choice", "multichoice"} and not choices:
            raise ManifestError(f"Variable '{key}' of type '{vtype}' requires 'choices'.")
        variables.append(
            Variable(
                name=str(key),
                type=vtype,
                prompt=spec.get("prompt"),
                default=spec.get("default"),
                choices=list(choices) if choices else None,
                help=spec.get("help"),
            )
        )
    return variables


def _parse_skip(raw: Any) -> list:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ManifestError("'skip' must be a list of {when, paths} rules.")
    rules: list = []
    for rule in raw:
        if not isinstance(rule, dict) or "when" not in rule or "paths" not in rule:
            raise ManifestError("Each skip rule needs 'when' and 'paths'.")
        paths = rule["paths"]
        if isinstance(paths, str):
            paths = [paths]
        rules.append(SkipRule(when=str(rule["when"]), paths=[str(p) for p in paths]))
    return rules


def _parse_hooks(raw: Any) -> list:
    if raw is None:
        return []
    post = raw.get("post_gen", []) if isinstance(raw, dict) else raw
    if post is None:
        return []
    if not isinstance(post, list):
        raise ManifestError("'hooks.post_gen' must be a list of hook definitions.")
    hooks: list = []
    for i, hook in enumerate(post):
        if isinstance(hook, str):
            hook = {"run": hook}
        if not isinstance(hook, dict) or "run" not in hook:
            raise ManifestError("Each hook must define a 'run' command.")
        hooks.append(
            Hook(
                name=str(hook.get("name", f"hook {i + 1}")),
                run=str(hook["run"]),
                when=str(hook.get("when", "true")),
            )
        )
    return hooks


def parse_manifest_data(data: Any, root: Path | None = None) -> Manifest:
    """Parse a raw dict (from YAML) into a validated :class:`Manifest`."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ManifestError("scaffld.yaml must contain a top-level mapping.")

    name = data.get("name")
    if not name:
        name = root.name if root is not None else "template"

    extends = data.get("extends") or []
    if isinstance(extends, str):
        extends = [extends]
    if not isinstance(extends, list):
        raise ManifestError("'extends' must be a string or list of template refs.")

    raw_globs = data.get("raw_globs") or data.get("raw") or []
    if isinstance(raw_globs, str):
        raw_globs = [raw_globs]

    return Manifest(
        name=str(name),
        description=str(data.get("description", "")),
        variables=_parse_variables(data.get("variables")),
        extends=[str(e) for e in extends],
        skip=_parse_skip(data.get("skip")),
        post_gen=_parse_hooks(data.get("hooks")),
        raw_globs=[str(g) for g in raw_globs],
        root=root,
    )


def load_manifest(root: Path) -> Manifest:
    """Load and validate the manifest from a template directory *root*."""
    root = Path(root)
    manifest_path = find_manifest(root)
    try:
        text = manifest_path.read_text(encoding="utf-8")
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via tests
        raise ManifestError(f"Failed to parse {manifest_path}: {exc}") from exc
    except OSError as exc:  # pragma: no cover
        raise ManifestError(f"Failed to read {manifest_path}: {exc}") from exc
    return parse_manifest_data(data, root=root)
