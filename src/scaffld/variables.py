"""Variable resolution: defaults, --var parsing, type coercion and prompting."""

from __future__ import annotations

from typing import Any

import jinja2

from .errors import VariableError
from .manifest import Variable
from .render import render_string

TRUE_STRINGS = {"1", "true", "yes", "y", "on"}
FALSE_STRINGS = {"0", "false", "no", "n", "off"}


def parse_var_flags(pairs: list | None) -> dict:
    """Parse ``["key=value", ...]`` CLI flags into a dict of raw strings."""
    result: dict = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise VariableError(
                f"Invalid --var '{pair}'. Expected key=value (e.g. --var name=demo)."
            )
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise VariableError(f"Invalid --var '{pair}': empty key.")
        result[key] = value
    return result


def coerce(var: Variable, value: Any) -> Any:
    """Coerce a raw value to the variable's declared type."""
    vtype = var.normalized_type()
    if vtype == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in TRUE_STRINGS:
            return True
        if text in FALSE_STRINGS:
            return False
        raise VariableError(f"Variable '{var.name}' expects a boolean, got '{value}'.")
    if vtype == "int":
        try:
            return int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise VariableError(
                f"Variable '{var.name}' expects an integer, got '{value}'."
            ) from exc
    if vtype == "choice":
        choices = [str(c) for c in (var.choices or [])]
        text = str(value)
        if text not in choices:
            raise VariableError(
                f"Variable '{var.name}'='{value}' not in choices {choices}."
            )
        return text
    if vtype == "multichoice":
        choices = [str(c) for c in (var.choices or [])]
        if isinstance(value, str):
            items = [v.strip() for v in value.split(",") if v.strip()]
        else:
            items = [str(v) for v in value]
        for item in items:
            if item not in choices:
                raise VariableError(
                    f"Variable '{var.name}' value '{item}' not in choices {choices}."
                )
        return items
    return str(value)


def _render_default(env: jinja2.Environment, var: Variable, context: dict) -> Any:
    default = var.default
    if isinstance(default, str) and ("{{" in default or "{%" in default):
        rendered = render_string(env, default, context, where=f"default for '{var.name}'")
        return rendered
    return default


def resolve_context(
    env: jinja2.Environment,
    variables: list,
    *,
    overrides: dict | None = None,
    prompter: Prompter | None = None,
    no_input: bool = False,
) -> dict:
    """Build the rendering context.

    Order of precedence for each variable:
      1. value from *overrides* (--var flags), coerced to type;
      2. interactive prompt (if a *prompter* is given and not *no_input*);
      3. the (possibly Jinja-rendered) default.

    Earlier variables are available to later defaults/prompts.
    """
    overrides = overrides or {}
    context: dict = {}
    unknown = set(overrides) - {v.name for v in variables}

    for var in variables:
        if var.name in overrides:
            value = coerce(var, overrides[var.name])
        elif prompter is not None and not no_input:
            default = _coerce_default(env, var, context)
            value = prompter.ask(var, default)
        else:
            value = _coerce_default(env, var, context)
        context[var.name] = value

    # Pass through unknown overrides so power users can inject extra context.
    for key in unknown:
        context[key] = overrides[key]

    return context


def _coerce_default(env: jinja2.Environment, var: Variable, context: dict) -> Any:
    raw_default = _render_default(env, var, context)
    if raw_default is None:
        vtype = var.normalized_type()
        if vtype == "bool":
            return False
        if vtype == "int":
            return 0
        if vtype == "multichoice":
            return []
        if vtype == "choice":
            return str(var.choices[0]) if var.choices else ""
        return ""
    return coerce(var, raw_default)


class Prompter:
    """Interactive prompts via questionary (lazily imported for testability)."""

    def ask(self, var: Variable, default: Any) -> Any:  # pragma: no cover - interactive
        import questionary

        label = var.prompt or var.name
        vtype = var.normalized_type()

        if vtype == "bool":
            return bool(
                questionary.confirm(label, default=bool(default)).unsafe_ask()
            )
        if vtype == "choice":
            choices = [str(c) for c in (var.choices or [])]
            default_choice = str(default) if str(default) in choices else (choices[0] if choices else None)
            answer = questionary.select(
                label, choices=choices, default=default_choice
            ).unsafe_ask()
            return coerce(var, answer)
        if vtype == "multichoice":
            choices = [str(c) for c in (var.choices or [])]
            selected = default if isinstance(default, list) else []
            answer = questionary.checkbox(
                label,
                choices=[
                    questionary.Choice(c, checked=c in selected) for c in choices
                ],
            ).unsafe_ask()
            return coerce(var, answer or [])
        # str / int
        answer = questionary.text(label, default=str(default)).unsafe_ask()
        if answer is None:
            answer = str(default)
        return coerce(var, answer)
