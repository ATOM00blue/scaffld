# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- **Path traversal / ZIP-SLIP (Critical):** rendered file and directory names, and
  `skip` paths, are now confined to the destination directory. Absolute paths,
  Windows drive/UNC paths, and any `..` traversal are rejected before writing, with a
  defense-in-depth `realpath` containment check in the writer. A malicious template
  can no longer write outside the chosen output directory.
- **Template injection / SSTI (Critical):** rendering now uses a Jinja2
  `SandboxedEnvironment`, blocking the standard `__class__`/`__globals__` escape chain
  so untrusted templates cannot execute code at render time.
- **Hook RCE without consent (Critical):** post-generation hooks (arbitrary shell
  commands from the template) now require **explicit consent**. The CLI shows the exact
  commands and prompts before running; non-interactive/CI runs skip hooks unless
  `--yes` is given. Added `--yes`/`-y`. `--no-hooks` still wins.
- **git argument injection hardening (Medium):** `git clone` now uses a `--`
  end-of-options separator and rejects URLs/refs/subdirs beginning with `-` or
  containing `..`.
- Replaced a bare `assert` (stripped under `python -O`) with an explicit error.

### Added

- New `--yes`/`-y` flag and an interactive hook-consent prompt.
- Prominent "Security & trust model" section in the README.
- Regression tests for path-traversal rejection, SSTI sandboxing, hook consent, and
  git argument-injection hardening; `SECURITY_REVIEW.md` documenting the audit.

## [0.1.0] - 2026-05-22

### Added

- Initial release.
- `scaffld new` to generate projects from a template (built-in name, local path, or git URL).
- Template resolution from built-in templates, local directories, and git URLs
  (`https`, `ssh`, `gh:user/repo`, and `user/repo` GitHub shorthand) with `#subdir` and `--ref`.
- Single-file `scaffld.yaml` manifest with `variables`, `extends`, `skip`, `raw_globs`, and `hooks`.
- Variable types: `str`, `int`, `bool`, `choice`, `multichoice`, with Jinja-computed defaults.
- Interactive prompts (questionary), `--var key=value` overrides, and `--no-input` CI mode.
- Jinja2 rendering of file contents and file/directory names; `.jinja`/`.j2` suffix stripping;
  binary-file passthrough; preserved empty directories.
- Custom Jinja filters: `slugify`, `snake`, `kebab`, `pascal`, `camel`.
- Composable layers via `extends` (multiple templates rendered into one destination).
- Conditional `skip` rules and cross-platform post-generation `hooks` with `when` conditions.
- `--dry-run` preview of the output tree and the hooks that would run.
- `--force` overwrite protection and `--no-hooks`.
- `scaffld list` and `scaffld info` commands.
- Three built-in templates: `python-package`, `cli-app`, `static-site`.

[Unreleased]: https://github.com/ATOM00blue/scaffld/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ATOM00blue/scaffld/releases/tag/v0.1.0
