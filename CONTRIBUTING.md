# Contributing to scaffld

Thanks for your interest in improving scaffld! Contributions of all kinds are welcome —
bug reports, docs, new built-in templates, and code.

## Development setup

```bash
git clone https://github.com/ATOM00blue/scaffld
cd scaffld
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Running the checks

```bash
pytest              # the full test suite
ruff check .        # lint
ruff format .       # format (optional)
```

Please make sure `pytest` is green and `ruff check .` is clean before opening a PR. CI
runs the suite on Linux and Windows across Python 3.9–3.12.

## Project layout

```
src/scaffld/
  cli.py          Typer CLI
  generator.py    orchestration (resolve → context → render → hooks)
  resolver.py     template resolution (built-in / path / git)
  manifest.py     scaffld.yaml parsing & validation
  variables.py    variable resolution, coercion, prompting
  render.py       Jinja env + file-tree rendering engine
  hooks.py        cross-platform hook execution
  templates/      shipped built-in templates
tests/            pytest suite
```

## Adding a built-in template

1. Create `src/scaffld/templates/<name>/scaffld.yaml`.
2. Put the files to generate under `src/scaffld/templates/<name>/template/`.
3. Add a test in `tests/test_builtin_templates.py` that generates it and asserts the tree.

## Guidelines

- Keep it small and fast. scaffld's value is being lightweight.
- Everything must be cross-platform. Use POSIX-style relative paths internally and be
  careful with path separators and shell commands in hooks.
- Add or update tests for any behavior change.
- Conventional, descriptive commit messages are appreciated.

## Reporting bugs

Open an issue with the command you ran, what you expected, what happened, and your OS /
Python version. A minimal template that reproduces the problem is gold.
