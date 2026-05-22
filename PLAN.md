# scaffld — Plan & Spec

> Scaffold projects from composable templates with variables and post-generation hooks.

## 1. Positioning & Research Summary

Competitors:
- **cookiecutter** — mature, huge ecosystem, but "dated": JSON config + a magic
  `{{cookiecutter.project_slug}}/` directory, no composition, one-shot only.
- **copier** — modern, YAML, supports *updates* (re-sync with template). Powerful but
  heavier; update/lifecycle focus.
- **degit** — just downloads a git subtree, no templating.
- **yeoman/plop/hygen** — JS ecosystem.

**Gap scaffld fills:** a *small, fast, lovable* Python scaffolder that is dead-simple to
author (one `scaffld.yaml` next to your files — no magic-named directory), that can
**compose multiple templates** (layers) in a single run, has **beautiful prompts**,
**dry-run preview**, and **cross-platform hooks**. Runnable with `uvx scaffld` — nothing
to install. Not trying to do lifecycle/update like copier; trying to be the nicest way to
*start* a project.

## 2. Template Format

A template is a directory containing:

```
my-template/
  scaffld.yaml        # manifest (required)
  template/           # files to render (root of generated output)
    {{ project_slug }}/
      __init__.py
    README.md.jinja    # ".jinja" suffix is stripped after rendering (optional)
```

`scaffld.yaml`:

```yaml
name: python-package
description: A modern Python package with pyproject + pytest.
# Variables prompted (interactive) or supplied via --var key=value.
variables:
  project_name:
    type: str
    prompt: "Project name"
    default: "My Project"
  project_slug:
    type: str
    default: "{{ project_name | lower | replace(' ', '_') | replace('-', '_') }}"
  description:
    type: str
    default: "A short description."
  license:
    type: choice
    prompt: "License"
    choices: [MIT, Apache-2.0, None]
    default: MIT
  use_cli:
    type: bool
    prompt: "Add a Typer CLI?"
    default: false
# Optional: another template applied *before* this one (composition).
extends: []          # list of template refs (built-in name / path / git url)
# Files to skip when a condition is false (Jinja expr over variables).
skip:
  - when: "not use_cli"
    paths: ["{{ project_slug }}/cli.py"]
# Post-generation hooks; run in the output dir, cross-platform.
hooks:
  post_gen:
    - name: "Initialize git"
      run: "git init -q"
      when: "true"
    - name: "Create venv"
      run: "python -m venv .venv"
      when: "false"
```

### Rendering rules
- All file **contents** are rendered with Jinja2 using the variable context.
- File and directory **names** are rendered too (so `{{ project_slug }}` works in paths).
- A trailing `.jinja` (or `.j2`) suffix on a filename is stripped after render
  (lets you template files that would otherwise be invalid, e.g. `pyproject.toml.jinja`).
- A `__raw__` marker: files matching `raw_globs` in the manifest are copied verbatim
  (no Jinja), useful for files containing literal `{{ }}`.
- Empty directories are preserved.
- Binary files are copied byte-for-byte (detected by null-byte sniff).

### Variable types
`str`, `bool`, `int`, `choice`, `multichoice`. Defaults may themselves be Jinja
expressions referencing earlier variables (computed lazily, top-to-bottom).

## 3. CLI Design (Typer)

```
scaffld new <template> [dest] [options]      # generate (alias: scaffld <template>)
scaffld list                                  # list built-in + registered templates
scaffld info <template>                       # show manifest, variables, hooks
scaffld version
```

Options for `new`:
- `--var key=value` (repeatable) — set a variable non-interactively.
- `--no-input` — never prompt; use defaults / --var (CI mode).
- `--dry-run` — print the tree + which hooks would run, write nothing.
- `--force` / `-f` — overwrite existing files.
- `--no-hooks` — skip post-gen hooks.
- `--yes / -y` — accept defaults for unset prompts.
- `--ref <git-ref>` — branch/tag/commit for git templates.

`<template>` resolution order:
1. built-in template name (shipped in package).
2. local filesystem path to a template dir.
3. git URL (`https://…`, `git@…`, `gh:user/repo`, `user/repo` shorthand on GitHub),
   optional `#subdir` and `--ref`.

## 4. Built-in Templates (shipped)
1. **python-package** — src layout, pyproject.toml, pytest, ruff, GitHub Actions CI,
   optional Typer CLI, MIT/Apache/none license.
2. **cli-app** — Typer + rich CLI app, packaged, console_scripts entry, tests.
3. **static-site** — minimal static site (index.html, style.css, justfile/Makefile),
   optional GitHub Pages workflow.

## 5. Package Layout

```
scaffld/
  pyproject.toml
  README.md  LICENSE  CONTRIBUTING.md  CHANGELOG.md  PLAN.md  .gitignore
  .github/workflows/ci.yml
  src/scaffld/
    __init__.py          # __version__
    __main__.py          # python -m scaffld
    cli.py               # Typer app
    manifest.py          # load/validate scaffld.yaml -> Manifest dataclasses
    variables.py         # resolve defaults, prompt (questionary), --var parse, types
    render.py            # Jinja env, render tree (names+content), binary/raw handling
    generator.py         # orchestrates: resolve template -> ctx -> render -> hooks
    resolver.py          # resolve template ref (builtin/path/git) -> local dir
    hooks.py             # run post_gen hooks cross-platform, when-conditions
    errors.py            # ScaffldError hierarchy
    console.py           # rich console + theming helpers
    templates/           # built-in templates (package data)
      python-package/...
      cli-app/...
      static-site/...
  tests/
    test_manifest.py test_variables.py test_render.py
    test_generator.py test_hooks.py test_resolver.py
    test_cli.py test_builtin_templates.py
```

## 6. Tech Choices
- **typer** (CLI), **jinja2** (templating), **questionary** (prompts),
  **rich** (output), **pyyaml** (manifest). Stdlib for everything else.
- Python 3.9+. Use `importlib.resources` for shipped templates.
- Hooks run via `subprocess` with `shell=True` is avoided; we split safely and run with
  the platform shell only when needed. Cross-platform: resolve commands, run in dest cwd.

## 7. Testing
- pytest, generate into `tmp_path`, assert output tree + rendered content + skips.
- hooks tested with a harmless echo/file-touch command.
- CLI tested via Typer's `CliRunner`.
- End-to-end smoke: invoke real CLI to scaffold `python-package` into a temp dir.
- CI matrix: ubuntu + windows + macos, py 3.9–3.12.

## 8. Done = green tests in venv + working CLI smoke + public GitHub repo pushed.
