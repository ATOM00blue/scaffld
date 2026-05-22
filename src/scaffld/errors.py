"""Exception hierarchy for scaffld.

All user-facing errors derive from :class:`ScaffldError` so the CLI can present
them cleanly without a traceback.
"""

from __future__ import annotations


class ScaffldError(Exception):
    """Base class for all expected, user-facing scaffld errors."""


class TemplateNotFoundError(ScaffldError):
    """A template reference could not be resolved to a usable template."""


class ManifestError(ScaffldError):
    """The ``scaffld.yaml`` manifest is missing, invalid, or malformed."""


class VariableError(ScaffldError):
    """A variable definition or supplied value is invalid."""


class RenderError(ScaffldError):
    """A Jinja2 template (file name or content) failed to render."""


class PathTraversalError(ScaffldError):
    """A rendered output path tried to escape the destination directory.

    Raised when a template file/dir name (or skip path) resolves to an absolute
    path, contains a ``..`` segment, or otherwise points outside the destination
    (the ZIP-SLIP / path-traversal class of attack).
    """


class HookError(ScaffldError):
    """A post-generation hook failed to run."""


class OutputExistsError(ScaffldError):
    """The destination already contains files and ``--force`` was not given."""
