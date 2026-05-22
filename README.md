# scaffld

> Scaffold projects from composable templates with variables and post-generation hooks.

[![CI](https://github.com/ATOM00blue/scaffld/actions/workflows/ci.yml/badge.svg)](https://github.com/ATOM00blue/scaffld/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/scaffld.svg)](https://pypi.org/project/scaffld/)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/style-ruff-261230.svg)](https://github.com/astral-sh/ruff)

**scaffld** is a small, fast project scaffolder. Point it at a template — a built-in
one, a local folder, or a git repo — answer a few prompts, and get a ready-to-go
project. Templates are just a directory of files plus a single `scaffld.yaml`. No magic
directory names, no JSON, no ceremony.

```bash
uvx scaffld new python-package my-lib
```

```
╭─ Generated (python-package) ──────────╮
│ my-lib/                               │
│ ├── .github/workflows/                │
│ │   └── ci.yml                        │
│ ├── src/my_lib/                       │
│ │   ├── __init__.py                   │
│ │   └── core.py                       │
│ ├── tests/test_core.py                │
│ ├── .gitignore                        │
│ ├── LICENSE                           │
│ ├── README.md                         │
│ └── pyproject.toml                    │
╰───────────────────────────────────────╯
✓ Created my-lib from python-package
```

## Why scaffld?

| | scaffld | cookiecutter | copier | degit |
|---|:---:|:---:|:---:|:---:|
| Single-file manifest (no magic dir) | ✅ | ❌ | ✅ | n/a |
| Compose multiple templates (layers) | ✅ | ❌ | ❌ | ❌ |
| Interactive prompts + `--var` flags | ✅ | ✅ | ✅ | ❌ |
| `--dry-run` preview tree | ✅ | ❌ | ✅ | ❌ |
| Cross-platform hooks with conditions | ✅ | partial | ✅ | ❌ |
| Local **and** git templates | ✅ | ✅ | ✅ | ✅ |
| Zero-install (`uvx scaffld`) | ✅ | — | — | — |

scaffld isn't trying to manage your project's whole lifecycle like copier — it's the
nicest possible way to *start* one.

## Install

Run it without installing (recommended):

```bash
uvx scaffld --help          # uv
pipx run scaffld --help     # pipx
```

Or install it permanently:

```bash
uv tool install scaffld
# or
pipx install scaffld
# or
pip install scaffld
```

## Quickstart

```bash
# See what ships out of the box
scaffld list

# Generate interactively
scaffld new python-package ./my-lib

# Non-interactive (CI-friendly): supply variables and skip prompts
scaffld new cli-app ./todo \
  --var app_name="Todo" --var command=todo --no-input

# Preview without writing anything
scaffld new static-site ./site --dry-run

# Use a template from GitHub
scaffld new gh:youruser/your-template ./out
scaffld new https://github.com/youruser/your-template#templates/service --ref v2
```

`scaffld <template>` is shorthand for `scaffld new <template>`.

## Built-in templates

| Name | Description |
|---|---|
| `python-package` | src-layout package, `pyproject.toml`, pytest, ruff, CI, optional Typer CLI |
| `cli-app` | Typer + rich command-line app, packaged with a console entry point and tests |
| `static-site` | Semantic HTML + modern CSS site, optional GitHub Pages deploy workflow |

Inspect any of them:

```bash
scaffld info python-package
```

## Authoring a template

A template is **any directory** with a `scaffld.yaml` manifest. Files to generate live
in a `template/` subdirectory (or directly alongside the manifest if you omit it).

```
my-template/
├── scaffld.yaml
└── template/
    ├── {{ package_name }}/
    │   └── __init__.py.jinja
    └── README.md.jinja
```

### The manifest

```yaml
name: python-package
description: A modern Python package.

# Variables become the Jinja context. They are prompted interactively
# or supplied with --var. Defaults can reference earlier variables.
variables:
  project_name:
    type: str
    prompt: "Project name"
    default: "My Project"
  package_name:
    type: str
    default: "{{ project_name | snake }}"   # computed default
  license:
    type: choice
    prompt: "License"
    choices: [MIT, Apache-2.0, None]
    default: MIT
  use_cli:
    type: bool
    prompt: "Add a Typer CLI?"
    default: false

# Compose other templates first (built-in name, path, or git URL).
extends: []

# Conditionally drop files when an expression is true.
skip:
  - when: "not use_cli"
    paths: ["src/{{ package_name }}/cli.py"]

# Files copied verbatim (no Jinja) — useful for files with literal {{ }}.
raw_globs: ["docs/*.tmpl"]

# Commands run in the generated directory after rendering.
hooks:
  post_gen:
    - name: "Initialize git"
      run: "git init -q && git add -A"
      when: "true"
```

### Variable types

| Type | Prompt widget | `--var` example |
|---|---|---|
| `str` | text | `--var name=demo` |
| `int` | text (coerced) | `--var port=8080` |
| `bool` | yes/no confirm | `--var use_cli=true` |
| `choice` | single select | `--var license=MIT` |
| `multichoice` | checkbox | `--var extras=ruff,mypy` |

Shorthand: `name: "default value"` is the same as a `str` variable with that default.

### Rendering rules

- **File contents** are rendered with Jinja2 using the variable context.
- **File and directory names** are rendered too, so `{{ package_name }}/` works as a path.
- A trailing **`.jinja`** or **`.j2`** suffix is stripped after rendering — name a file
  `pyproject.toml.jinja` so editors still treat the source as a template.
- **Binary files** are copied byte-for-byte (auto-detected).
- **Empty directories** are preserved.
- Use `raw_globs` for files that contain literal `{{` / `}}` you don't want rendered.

### Built-in Jinja filters

`slugify`, `snake` / `snake_case`, `kebab` / `kebab_case`, `pascal` / `pascal_case`,
`camel` — plus everything Jinja2 ships with.

```jinja
{{ project_name | snake }}     →  my_project
{{ project_name | kebab }}     →  my-project
{{ project_name | pascal }}    →  MyProject
```

### Composable layers

`extends` lets one template build on others. Layers are rendered in order into the same
destination with one shared variable context, so a later layer can override files from an
earlier one:

```yaml
name: service
extends: [python-package]   # render python-package first, then this on top
```

### Hooks

Hooks run **after** rendering, in the generated directory, through your platform shell
(so the same `run:` line works on Windows, macOS and Linux for common commands). Each
hook has an optional `when:` Jinja condition. They always show up in `--dry-run` so you
can see what *would* run.

Because hooks execute **arbitrary commands defined by the template author**, scaffld
**asks for your explicit consent** before running them and shows you the exact commands
first. Decline and the project is still generated — only the commands are skipped.

- `--yes` / `-y` — consent to run hooks without the prompt (use only for templates you trust).
- `--no-hooks` — never run hooks (wins over `--yes`).
- `--no-input` (CI) — hooks are **not** run unless you also pass `--yes`.

See [Security & trust model](#security--trust-model) below.

## Security & trust model

**A template is code.** scaffld can fetch templates from arbitrary git URLs and a
template author controls file contents, file/directory *names*, and post-generation
*commands*. Treat any template you did not write like any other untrusted code: only
run templates from sources you trust.

scaffld defends you with three layers:

1. **Sandboxed rendering.** Templates render in a Jinja2 `SandboxedEnvironment`, which
   blocks the standard template-injection escapes (`__class__`, `__globals__`, …). A
   malicious template cannot execute Python through rendering alone.
2. **Destination confinement (no path traversal / ZIP-SLIP).** Every rendered output
   path is validated to stay **inside** the destination directory. Absolute paths,
   Windows drive/UNC paths, and any `..` traversal are rejected before anything is
   written — a template can never write outside the folder you chose.
3. **Explicit consent for hooks.** Post-generation hooks run arbitrary shell commands.
   scaffld shows them and requires your confirmation (or an explicit `--yes`) before
   running any. In non-interactive/CI mode, hooks are skipped unless you opt in with
   `--yes`. Use `--no-hooks` to disable them entirely.

**`extends` inherits trust.** Composing a template via `extends` pulls in (and may clone)
its base templates; you are trusting the *entire* chain, not just the top-level template.

To report a security issue, please open a private advisory on the GitHub repository.

## CLI reference

```text
scaffld new <template> [dest]   Generate a project (alias: scaffld <template>)
scaffld list                    List built-in templates
scaffld info <template>         Show a template's variables and hooks
scaffld --version               Print the version
```

Options for `new`:

| Option | Description |
|---|---|
| `--var KEY=VALUE`, `-v` | Set a variable (repeatable) |
| `--no-input` | Never prompt; use defaults + `--var` (CI mode) |
| `--dry-run` | Preview the tree and hooks; write nothing |
| `--force`, `-f` | Overwrite existing files |
| `--no-hooks` | Skip post-generation hooks (wins over `--yes`) |
| `--yes`, `-y` | Consent to run hooks without prompting (trusted templates) |
| `--ref REF` | Git branch/tag/commit for git URL templates |

## Examples

```bash
# A package with a CLI, fully non-interactive
scaffld new python-package ./acme \
  --var project_name="Acme" --var use_cli=true --var license=Apache-2.0 --no-input

# A static site without the Pages workflow
scaffld new static-site ./blog --var deploy_pages=false --no-input

# Preview a GitHub template before committing to it
scaffld new gh:octocat/python-template ./demo --dry-run
```

## FAQ

**How is this different from cookiecutter?**
No magic `{{cookiecutter.x}}/` directory and no JSON — just a `template/` folder and one
YAML file. scaffld also composes multiple templates, previews with `--dry-run`, and runs
without installing via `uvx`.

**Does it update existing projects like copier?**
No. scaffld is focused on *creating* projects. If you need to keep a project in sync with
an evolving template over time, copier is the right tool.

**Where do hooks run?**
In the freshly generated directory, through your shell — but only after you approve the
exact commands (or pass `--yes`). Use `--no-hooks` to skip them entirely. See
[Security & trust model](#security--trust-model).

**Can I use a private git template?**
Yes — if your `git` is configured with credentials/SSH for that repo, scaffld clones it
the same way you would.

**It didn't overwrite my files.**
By design. Pass `--force` to overwrite an existing destination.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md). In short:

```bash
git clone https://github.com/ATOM00blue/scaffld
cd scaffld
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
ruff check .
```

## License

[MIT](LICENSE) © 2026 ATOM00blue
