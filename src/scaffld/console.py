"""Shared rich console and small styling helpers."""

from __future__ import annotations

import sys

from rich.console import Console
from rich.theme import Theme


def _reconfigure_utf8() -> None:
    """Best-effort: switch stdio to UTF-8 so unicode glyphs don't crash on Windows.

    Legacy Windows terminals default to cp1252, which cannot encode characters
    like the box-drawing/arrow glyphs rich emits. ``reconfigure`` is available
    on Python 3.7+ TextIO streams; we ignore failures silently.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # pragma: no cover - platform dependent
                pass


_reconfigure_utf8()

THEME = Theme(
    {
        "scaffld.title": "bold cyan",
        "scaffld.accent": "cyan",
        "scaffld.success": "bold green",
        "scaffld.error": "bold red",
        "scaffld.warn": "yellow",
        "scaffld.dim": "dim",
        "scaffld.path": "magenta",
        "scaffld.add": "green",
        "scaffld.skip": "yellow",
    }
)

console = Console(theme=THEME)
err_console = Console(theme=THEME, stderr=True)


def _supports_unicode() -> bool:
    enc = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        "✓→⚠✗".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


_UNICODE = _supports_unicode()

SYMBOLS = {
    "ok": "✓" if _UNICODE else "+",
    "arrow": "→" if _UNICODE else "->",
    "warn": "⚠" if _UNICODE else "!",
    "cross": "✗" if _UNICODE else "x",
    "bullet": "•" if _UNICODE else "-",
}


def success(message: str) -> None:
    console.print(f"[scaffld.success]{SYMBOLS['ok']}[/] {message}")


def info(message: str) -> None:
    console.print(message)


def warn(message: str) -> None:
    console.print(f"[scaffld.warn]{SYMBOLS['warn']}[/] {message}")


def error(message: str) -> None:
    err_console.print(f"[scaffld.error]{SYMBOLS['cross']}[/] {message}")
