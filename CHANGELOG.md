# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
