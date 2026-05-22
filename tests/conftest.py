"""Shared pytest fixtures for the scaffld test suite."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


@pytest.fixture
def make_template(tmp_path):
    """Factory: build a template directory with a manifest and files.

    Usage::

        tdir = make_template(
            manifest="name: t\\nvariables:\\n  x: hi\\n",
            files={"template/{{ x }}.txt": "value={{ x }}"},
        )
    """

    def _make(manifest: str, files: dict, name: str = "tmpl") -> Path:
        root = tmp_path / name
        write(root / "scaffld.yaml", manifest)
        for rel, content in files.items():
            write(root / rel, content)
        return root

    return _make
