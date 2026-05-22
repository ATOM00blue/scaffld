# Security & Quality Review — scaffld

**Date:** 2026-05-22
**Reviewer:** application-security engineering pass
**Scope:** full source tree under `src/scaffld`, tests, packaging, docs, CI.
**Version reviewed:** 0.1.0 (commit `c10c3e1`)

scaffld fetches templates from arbitrary git URLs, renders them with Jinja2, and
runs post-generation shell commands declared in the template manifest. The
template author is therefore an **untrusted** party for any non-local template.
This review treats template content (file names, file bodies, `scaffld.yaml`,
hooks) as attacker-controlled.

Severity scale: **Critical** (unauthenticated RCE / trivial escape),
**High** (RCE or out-of-tree write requiring a plausible precondition),
**Medium** (hardening / defense-in-depth / correctness affecting safety),
**Low** (quality / informational).

---

## Findings

### C1 — Path traversal / ZIP-SLIP in rendered output paths — **Critical** — FIXED
**File:** `src/scaffld/render.py` (`build_plan`, `write_plan`, `resolve_skip_paths`);
`src/scaffld/generator.py` (`write_plan` call site).

**Impact.** File and directory *names* are rendered from the template
(`render_string(env, filename, …)`), and a literal name like `../../evil` or a
rendered name such as `{{ '../../../etc/cron.d/x' }}` is joined directly onto the
destination with **no confinement check**. `write_plan` does
`target = dest / Path(pf.rel_target)` and `target.parent.mkdir(parents=True)` —
so a malicious template (local, or cloned from a git URL) can create/overwrite
files **anywhere the process can write**, outside the destination directory.
This is the classic ZIP-SLIP class of bug (CWE-22 / CWE-23).

**Proof (pre-fix).** A template file named `{{ name }}.txt` rendered with
`name = "../../../escaped"` produced `rel_target = "../../../escaped.txt"`, which
joined to `dest = /tmp/dest` normalizes to `/escaped.txt` (filesystem root).
Verified empirically. A literal `../../x` file/dir name in a cloned repo behaves
identically.

**Fix.** Added a single choke point `_safe_relative(rel, *, where)` in
`render.py` that:
- rejects absolute paths, drive-letter / UNC paths (`C:\…`, `\\host\share`),
- rejects any path containing a `..` segment or empty/`.`-only segments,
- normalizes and re-verifies the POSIX form before use.

Every rendered directory name, file name, and skip path now passes through it
(`build_plan` and `resolve_skip_paths`). `write_plan` additionally performs a
**belt-and-braces** `os.path.realpath` containment check: each resolved target
must live inside `realpath(dest)` or it raises `PathTraversalError`. Rejection
raises a new `PathTraversalError(ScaffldError)` so the CLI prints a clean message
and exits non-zero.

---

### C2 — Server-Side Template Injection (SSTI) → RCE via unsandboxed Jinja2 — **Critical** — FIXED
**File:** `src/scaffld/render.py` (`make_environment`).

**Impact.** The environment was a plain `jinja2.Environment`. Because template
authors are untrusted, template content (or even a Jinja-computed *default* /
`when` condition / hook command) can use the standard Python sandbox-escape
chain to reach arbitrary callables and execute code at **render time** — i.e.
RCE that fires *before* and *independently of* hooks, so `--no-hooks` does **not**
mitigate it.

**Proof (pre-fix).** `{{ ''.__class__.__mro__ }}` returned the real MRO and
`{{ cycler.__init__.__globals__ }}` returned a 13 KB globals dump — both the
building blocks of a full escape to `os.system`. Verified empirically.

**Fix.** `make_environment()` now builds a
`jinja2.sandbox.SandboxedEnvironment`, which blocks access to underscore/dunder
attributes and unsafe callables. All rendering paths (`render_string`,
`evaluate_condition`, computed defaults, file/dir names, hook commands, skip
rules) share this one environment, so the sandbox covers every author-controlled
expression. `autoescape` is intentionally left `False` (see N1) — that is
correct for code generation and is **not** the SSTI control; the sandbox is.

---

### C3 — Post-gen hooks: arbitrary command execution with no consent gate — **Critical** — FIXED
**File:** `src/scaffld/hooks.py` (`run_hooks`), `src/scaffld/generator.py`
(`generate`, default `run_post_hooks=True`), `src/scaffld/cli.py` (`new`).

**Impact.** Hooks run **by default** (`run_post_hooks=True`) and are executed
with `shell=True` on the rendered command string. Pointing scaffld at an
untrusted git template (`scaffld new gh:attacker/repo ./out`) therefore runs
attacker-authored shell commands on the user's machine with **no warning and no
opt-in** — textbook RCE (CWE-78). `--no-hooks` existed but was opt-*out*, which
is the wrong default for an untrusted-input tool.

**Fix (trust model: explicit consent).**
- The CLI now **gates hook execution behind an explicit interactive consent
  prompt**. Before any hook runs, scaffld prints the exact commands and asks the
  user to confirm; declining proceeds without running hooks. The generated
  project is still written — only the commands are withheld.
- New `--yes/-y` flag grants consent non-interactively (documented as "I trust
  this template"). `--no-hooks` still force-disables hooks and wins over `--yes`.
- In `--no-input` (CI) mode, hooks are **not** run unless `--yes` is *also*
  given. This makes the safe path the default for automation: no TTY, no
  implicit code execution.
- The consent decision is threaded through `generate()` via a
  `hook_consent` callback so the core stays UI-agnostic and testable; the
  library default for `generate()` remains backward-compatible for embedders who
  pass an explicit callback, but the **shipped CLI never runs hooks without
  consent**.
- `shell=True` is retained *by design* (documented): hook strings are
  free-form shell one-liners that authors expect to behave like a terminal, and
  the protection boundary is **consent**, not argument-vector parsing. We do
  **not** pass untrusted strings to `shell=True` silently — the user has seen and
  approved the exact command. This is documented in the README trust model and
  in `SECURITY` notes. See N2 for the residual-risk rationale.

---

### H1 — `extends` composition resolves untrusted git refs transitively — **High** — MITIGATED
**File:** `src/scaffld/generator.py` (`_collect_layers`), `resolver.py`.

**Impact.** A template's `extends:` list can reference further git URLs, each of
which is cloned and whose hooks/templates are then combined. A user who vetted
the top-level template can still be exposed to code (hooks) and traversal
(C1/C2) from transitively-pulled bases.

**Mitigation.** C1 (path confinement) and C2 (sandbox) now apply uniformly to
*every* layer regardless of origin, and C3's consent prompt lists hooks from all
layers before any run. The trust-model documentation explicitly states that
`extends` inherits the trust of the *whole* chain. Cycle detection already
existed and is retained. Deeper supply-chain controls (pinning, allowlists) are
documented as out of scope for 0.1.x — see "Intentionally not changed".

---

### M1 — git clone of untrusted URL/ref: argument-injection hardening — **Medium** — FIXED
**File:** `src/scaffld/resolver.py` (`_resolve_git`, `_normalize_git_url`).

**Status.** The clone already used an **argument list** (no `shell=True`), so OS
command injection was not possible. However a URL or `--ref` beginning with `-`
(e.g. `--upload-pack=…`, or a ref like `--output=…`) could be misinterpreted by
git as an **option** rather than a value (argument injection, CWE-88).

**Fix.** Added `--` end-of-options separators and explicit rejection of
URL/ref/subdir values that begin with `-`. The clone now runs
`git clone --depth 1 [--branch <ref>] -- <url> <dir>` and `git_ref` is validated
to not start with `-`. URL scheme is restricted to the already-supported set
(`https`, `ssh://`, `git@`, `git://`, plus `gh:`/shorthand → https).

---

### M2 — `.git` directory could be overwritten/escaped by a layer — **Medium** — ADDRESSED via C1
A template file path resolving to `.git/...` inside the destination is now still
*inside* dest (allowed), but the C1 traversal guard prevents writing to a parent
project's `.git`. No separate change required; noted for completeness.

---

### L1 — `setuptools 65.5.0` vulnerable in the dev/venv environment — **Low** — NOTED
**Source:** `pip-audit` (PYSEC-2022-43012, PYSEC-2025-49, CVE-2024-6345).

`setuptools` is **not** a declared runtime dependency of scaffld (deps are
typer, jinja2, questionary, rich, PyYAML). The vulnerable copy is the one
pre-seeded into the local `.venv`. End users installing scaffld via
`pip/uvx/pipx` resolve a current `setuptools` (or none, since the build backend
is hatchling). Action: upgraded `setuptools` in the working venv so the audit is
clean; no packaging change needed because scaffld does not pin or ship it.

---

### L2 — YAML parsing — **Low** — ALREADY SAFE (verified)
`manifest.py` uses `yaml.safe_load` (no `Loader=` / `full_load`). No change
needed. Confirmed there is no other YAML entry point.

---

### L3 — `bandit` informational items — **Low** — RESOLVED / ANNOTATED
- B602 (`shell=True`) at `hooks.py` — see C3; retained by design behind consent,
  annotated `# nosec B602` with rationale.
- B701 (`autoescape=False`) at `render.py` — intentional for code generation
  (see N1); the SSTI control is the sandbox (C2), annotated `# nosec B701`.
- B404 (subprocess import) / B603 (clone subprocess) — expected; B603 is a list
  call with `--` hardening (M1).
- B101 (`assert` in `manifest.template_dir`) — replaced the bare `assert` with an
  explicit `ManifestError` so it is not stripped under `python -O`.

---

## Robustness / quality observations (addressed)

- **Cross-platform paths:** the traversal guard explicitly handles Windows drive
  letters and UNC paths in addition to POSIX `..`, so confinement holds on
  Windows where `Path("C:/x")` and `Path("/x")` semantics differ.
- **Error surface:** new `PathTraversalError` derives from `ScaffldError`, so the
  CLI presents it cleanly (no traceback) and exits 1, consistent with the rest.
- **Tests:** added regression tests for path-traversal rejection (literal `..`,
  rendered `..`, absolute, drive-letter, UNC, traversal in skip paths and dir
  names), SSTI sandboxing (`__class__`/`__globals__` blocked), and hook-consent
  behavior (declined → not run; `--yes` → run; `--no-input` without `--yes` →
  not run; `--no-hooks` wins).

---

## Intentionally not changed (residual risk, documented)

### N1 — `autoescape=False`
scaffld generates source code, TOML, YAML, INI, Dockerfiles, etc., where HTML
escaping would corrupt output. Autoescaping is the wrong tool here and is **not**
the injection control. The injection control is the **sandbox** (C2). Left as-is
by design; bandit B701 annotated.

### N2 — Hooks run via the platform shell (`shell=True`)
Hook commands are intentionally free-form shell one-liners (e.g.
`git init -q && git add -A`) so one `run:` line works across platforms for common
cases. Converting to `shlex`-split argv would break documented behavior (shell
operators `&&`, `|`, redirection) and provides little benefit once the *consent*
boundary (C3) is in place: the user is shown and must approve the literal command
before it runs. We therefore keep `shell=True` but make execution **opt-in with
informed consent**, which is the appropriate control for an arbitrary-command
feature. Residual risk: a user who approves a hook they did not read. Documented
prominently in README "Security & trust model".

### N3 — Supply-chain pinning of `extends` / git templates
Pinning bases by commit, allowlisting hosts, or signature verification are
valuable hardening but out of scope for 0.1.x and would change the UX
contract. Documented as future work; the consent + sandbox + confinement
controls reduce the blast radius in the meantime.

---

## Verification summary

See CHANGELOG and the final report. All Critical/High/Medium items above are
fixed or mitigated; `ruff check .` clean, `pytest` green (incl. new regression
tests), `bandit -r src` reports only the two annotated by-design items, and
`pip-audit` is clean after upgrading the venv's `setuptools` (a non-shipped
build artifact).
