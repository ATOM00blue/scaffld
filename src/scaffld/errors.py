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


class HookError(ScaffldError):
    """A post-generation hook failed to run."""


class OutputExistsError(ScaffldError):
    """The destination already contains files and ``--force`` was not given."""
