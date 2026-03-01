# GitHub Actions: CI + Publish to PyPI (Trusted Publishing / OIDC)

## TL;DR
> **Summary**: Add GitHub Actions workflows to run CI on PRs/pushes and publish `uitrace` to PyPI when a `v*` tag is pushed, using PyPI Trusted Publishing (OIDC) and `uv`.
> **Deliverables**:
> - `.github/workflows/ci.yml`
> - `.github/workflows/publish.yml`
> - `README.md` release notes (how to tag + PyPI publisher setup)
> **Effort**: Short
> **Parallel**: YES — 2 waves
> **Critical Path**: Add workflows → local verification → (PyPI pending publisher) → first tag publish

## Context
### Original Request
- “实现 github action , 发布到 pypi”

### Interview Summary
- Auth: **PyPI Trusted Publishing (OIDC)**
- Release trigger: **push tag `v*`**
- Also add a standard **CI workflow** for push/PR

### Repo Facts (grounded)
- Repo: `mkdir700/uitrace` (default branch: `main`)
- Packaging: `pyproject.toml` uses PEP 621 + `hatchling` backend; src-layout (`src/uitrace`)
- Console script: `[project.scripts] uitrace = "uitrace.cli:main"`
- Tooling: `uv.lock` present; dev commands documented in `README.md`
- Important: version is **static** in `pyproject.toml` (`[project].version = "0.1.0"`) → must guard tag/version mismatch

### Metis Review (gaps addressed)
- Add **tag ↔ pyproject version** validation before building/publishing
- Run CI on **`macos-latest`** (tests expect darwin platform behavior)
- Make `uv sync` explicit: `uv sync --group dev --frozen`
- Publish workflow uses **build artifacts** (upload/download) so the published dists are exactly what was tested
- Add concurrency guard to avoid simultaneous publish races

## Work Objectives
### Core Objective
- Automated, repeatable CI and PyPI publishing via GitHub Actions.

### Deliverables
- CI workflow that runs `ruff`, `mypy`, `pytest` on PR/push.
- Publish workflow that (a) runs the same checks, (b) builds `sdist` + `wheel`, (c) smoke-tests the built wheel, (d) publishes to PyPI via OIDC on tag push `v*`.
- README release section documenting the exact steps and guardrails.

### Definition of Done (verifiable)
- `uv run ruff check .` passes locally.
- `uv run mypy src` passes locally.
- `uv run pytest -q` passes locally.
- Workflow files exist and contain:
  - `ci.yml`: `on: push` + `pull_request` (branch `main`), `runs-on: macos-latest`, runs ruff/mypy/pytest.
  - `publish.yml`: `on: push` tags `v*`, build+publish jobs, `permissions: id-token: write`, version/tag check, `uv build`, `uv publish --trusted-publishing always`.
- With PyPI trusted publisher configured, pushing tag `vX.Y.Z` matching `pyproject.toml` version results in a successful publish run.

### Must Have
- Trusted Publishing (OIDC) — no long-lived PyPI token in GitHub secrets.
- Version guard: fail workflow if tag version doesn’t match `pyproject.toml`.
- Publish uses `dist/` artifacts from the build job.

### Must NOT Have
- No packaging refactors (no dynamic versioning migrations like hatch-vcs).
- No auto-bump of version.
- No TestPyPI support unless explicitly requested.
- No additional tooling (tox/nox) added.

## External Prerequisites (human / outside repo)
These cannot be automated fully by the agent and must be done once:

1) **Create PyPI project via “pending publisher” (recommended for first release)**
- PyPI docs: https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/
- Configure a GitHub Actions trusted publisher with:
  - Owner: `mkdir700`
  - Repository: `uitrace`
  - Workflow filename: `publish.yml`
  - Environment: (leave blank; this plan does not use a GitHub Environment)
  - Project name: `uitrace`

2) (Optional hardening) **GitHub tag protections**
- Add a tag protection rule for `v*` so only maintainers can create release tags.

## Verification Strategy
- Test decision: **tests-after** (existing tests + checks)
- Pre-publish gates: ruff + mypy + pytest + version-tag match + wheel smoke test
- Evidence: save outputs under `.sisyphus/evidence/` as referenced in each task

## Execution Strategy
### Parallel Execution Waves
Wave 1 (foundation): repo preflight + CI workflow
Wave 2 (dependent): publish workflow + docs

### Dependency Matrix
- Publish workflow depends on CI command parity + version guard decision (already decided: static version + check).
- Docs depends on workflow filenames (must match PyPI publisher config).

## TODOs
> Implementation + Test = ONE task.
> Every task includes QA scenarios and evidence paths.

- [x] 1. Preflight: verify package name + local build commands

  **What to do**:
  - Confirm `uitrace` name availability on PyPI (best-effort).
  - Confirm local commands for checks/build match README and work on this repo.
  - Record exact commands and outputs as evidence for later.

  **Must NOT do**:
  - Do not change version numbers.
  - Do not publish anything.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: small preflight commands only
  - Skills: `[]`

  **Parallelization**: Can Parallel: NO | Wave 1 | Blocks: 2, 3 | Blocked By: none

  **References**:
  - Packaging: `pyproject.toml`
  - Dev commands: `README.md:116`

  **Acceptance Criteria**:
  - [x] `python -m pip index versions uitrace` returns “No matching distribution found” (or otherwise document the conflict)
  - [x] `uv build` completes locally and produces `dist/*.whl` + `dist/*.tar.gz`

  **QA Scenarios**:
  ```
  Scenario: Build succeeds locally
    Tool: Bash
    Steps:
      - Run: uv build
      - Run: ls dist/
    Expected:
      - 1 wheel and 1 sdist exist
    Evidence: .sisyphus/evidence/task-1-preflight-build.txt

  Scenario: Package name conflict (edge)
    Tool: Bash
    Steps:
      - Run: python -m pip index versions uitrace
    Expected:
      - If versions exist, record conflict; publishing plan must change package name
    Evidence: .sisyphus/evidence/task-1-preflight-pypi-name.txt
  ```

  **Commit**: NO

- [x] 2. Add CI workflow (`ci.yml`) for push/PR

  **What to do**:
  - Create `.github/workflows/ci.yml`.
  - Trigger on `push` and `pull_request` to `main`.
  - Run on `macos-latest`.
  - Use this exact workflow skeleton (copy/paste and adjust only if needed):

    ```yaml
    name: CI

    on:
      push:
        branches: [main]
      pull_request:
        branches: [main]

    permissions:
      contents: read

    jobs:
      test:
        runs-on: macos-latest

        steps:
          - name: Checkout
            uses: actions/checkout@v4

          - name: Setup Python
            uses: actions/setup-python@v5
            with:
              python-version-file: .python-version

          - name: Setup uv
            uses: astral-sh/setup-uv@v7
            with:
              enable-cache: true

          - name: Sync
            run: uv sync --group dev --frozen

          - name: Ruff
            run: uv run ruff check . --output-format github

          - name: Mypy
            run: uv run mypy src

          - name: Pytest
            run: uv run pytest -q

          - name: Build (sdist+wheel)
            run: uv build --no-sources
    ```

  **Must NOT do**:
  - No publishing steps.
  - Do not add secrets.

  **Recommended Agent Profile**:
  - Category: `quick` — Reason: new workflow YAML file + simple local checks
  - Skills: `[]`

  **Parallelization**: Can Parallel: YES | Wave 1 | Blocks: 3 | Blocked By: 1

  **References**:
  - Commands: `README.md:116`
  - Python version: `.python-version`
  - Dev deps: `pyproject.toml:17`

  **Acceptance Criteria**:
  - [x] `.github/workflows/ci.yml` exists
  - [x] Grep confirms triggers include `push` and `pull_request` to `main`
  - [x] Grep confirms `runs-on: macos-latest`
  - [x] Grep confirms it runs ruff/mypy/pytest via `uv run`

  **QA Scenarios**:
  ```
  Scenario: Workflow contains required gates
    Tool: Bash
    Steps:
      - Run: rg -n "on:|pull_request:|push:|branches:" .github/workflows/ci.yml
      - Run: rg -n "runs-on: macos-latest" .github/workflows/ci.yml
      - Run: rg -n "uv sync" .github/workflows/ci.yml
      - Run: rg -n "ruff check" .github/workflows/ci.yml
      - Run: rg -n "mypy src" .github/workflows/ci.yml
      - Run: rg -n "pytest" .github/workflows/ci.yml
    Expected:
      - All patterns found exactly once in appropriate sections
    Evidence: .sisyphus/evidence/task-2-ci-workflow-grep.txt

  Scenario: CI fails if lockfile missing (edge)
    Tool: Bash
    Steps:
      - Verify ci.yml uses --frozen
    Expected:
      - CI would fail fast rather than silently generating a new lock
    Evidence: .sisyphus/evidence/task-2-ci-frozen-check.txt
  ```

  **Commit**: NO

- [x] 3. Add publish workflow (`publish.yml`) for tag `v*` using OIDC

  **What to do**:
  - Create `.github/workflows/publish.yml`.
  - Trigger on `push` tags matching `v*`.
  - Use two jobs:
    1) `build` job: run the same checks as CI, verify tag version matches `pyproject.toml`, build dists, smoke-test the wheel, upload `dist/` artifact.
    2) `publish` job: download artifact and run `uv publish` via OIDC.
  - Set `permissions` only on publish job: `id-token: write` + `contents: read`.
  - Add `concurrency` to prevent overlapping publishes.
  - Use this exact workflow skeleton (copy/paste and adjust only if needed):

    ```yaml
    name: Publish to PyPI

    on:
      push:
        tags:
          - "v*"

    concurrency:
      group: publish-${{ github.ref }}
      cancel-in-progress: false

    jobs:
      build:
        runs-on: macos-latest
        permissions:
          contents: read

        steps:
          - name: Checkout
            uses: actions/checkout@v4

          - name: Setup Python
            uses: actions/setup-python@v5
            with:
              python-version-file: .python-version

          - name: Setup uv
            uses: astral-sh/setup-uv@v7
            with:
              enable-cache: true

          - name: Verify tag matches pyproject.toml version
            shell: bash
            run: |
              set -euo pipefail
              TAG_VERSION="${GITHUB_REF_NAME#v}"
              PYPROJECT_VERSION="$(python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
              if [[ "$TAG_VERSION" != "$PYPROJECT_VERSION" ]]; then
                echo "::error::Tag version v${TAG_VERSION} does not match pyproject.toml version ${PYPROJECT_VERSION}"
                exit 1
              fi

          - name: Sync
            run: uv sync --group dev --frozen

          - name: Ruff
            run: uv run ruff check . --output-format github

          - name: Mypy
            run: uv run mypy src

          - name: Pytest
            run: uv run pytest -q

          - name: Build (sdist+wheel)
            run: uv build --no-sources

          - name: Smoke test wheel
            shell: bash
            run: |
              set -euo pipefail
              shopt -s nullglob
              wheels=(dist/*.whl)
              if [ ${#wheels[@]} -ne 1 ]; then
                echo "Expected exactly 1 wheel in dist/, found: ${wheels[*]}"
                exit 1
              fi
              uvx --from "${wheels[0]}" uitrace --help
              uvx --from "${wheels[0]}" uitrace play --dry-run tests/fixtures/trace_v1_valid.jsonl

          - name: Upload dists
            uses: actions/upload-artifact@v4
            with:
              name: release-dists
              path: dist/
              if-no-files-found: error

      publish:
        runs-on: macos-latest
        needs: build
        permissions:
          id-token: write
          contents: read

        steps:
          - name: Download dists
            uses: actions/download-artifact@v4
            with:
              name: release-dists
              path: dist/

          - name: Setup uv
            uses: astral-sh/setup-uv@v7

          - name: Publish
            run: uv publish --trusted-publishing always dist/*
    ```

  **Must NOT do**:
  - Do not publish from the build job.
  - Do not use API tokens or secrets.
  - Do not remove/relax the version-tag guard.

  **Recommended Agent Profile**:
  - Category: `unspecified-high` — Reason: release automation + external integration constraints
  - Skills: `[]`

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: 4 | Blocked By: 2

  **References**:
  - Version source: `pyproject.toml:3`
  - Publish CLI: `uv publish --help` (local)
  - Trusted publishing docs: https://docs.pypi.org/trusted-publishers/using-a-publisher/
  - Pending publisher docs: https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/

  **Acceptance Criteria**:
  - [x] `.github/workflows/publish.yml` exists
  - [x] Grep confirms tag trigger `v*`
  - [x] Grep confirms publish job has `id-token: write`
  - [x] Grep confirms presence of tag/version validation step
  - [x] Grep confirms `uv build` and `uv publish --trusted-publishing always`

  **QA Scenarios**:
  ```
  Scenario: Version-tag validation is present
    Tool: Bash
    Steps:
      - Run: rg -n "Verify tag matches" .github/workflows/publish.yml
      - Run: rg -n "tomllib" .github/workflows/publish.yml
    Expected:
      - publish.yml contains a step that compares tag version to pyproject version and fails on mismatch
    Evidence: .sisyphus/evidence/task-3-publish-version-guard.txt

  Scenario: Smoke test command is robust (edge)
    Tool: Bash
    Steps:
      - Run: rg -n "uvx --from" .github/workflows/publish.yml
      - Ensure workflow selects exactly one wheel (array/count check) before running uvx
    Expected:
      - No bare unguarded `dist/*.whl` passed directly to uvx
    Evidence: .sisyphus/evidence/task-3-publish-smoke-test-guard.txt
  ```

  **Commit**: NO

- [x] 4. Document release process + PyPI setup in `README.md`

  **What to do**:
  - Add a “Release” section describing:
    - Bump `[project].version` in `pyproject.toml`
    - Run local checks (`ruff/mypy/pytest`) and `uv build`
    - Create and push tag `vX.Y.Z` (must match `pyproject.toml`)
    - One-time PyPI Trusted Publisher setup (pending publisher) values: owner/repo/workflow

  **Must NOT do**:
  - Do not add long tutorials; keep it short and actionable.

  **Recommended Agent Profile**:
  - Category: `writing` — Reason: README update
  - Skills: `[]`

  **Parallelization**: Can Parallel: YES | Wave 2 | Blocks: none | Blocked By: 3

  **References**:
  - Existing dev section: `README.md:114`
  - Version field: `pyproject.toml:3`
  - Publisher docs: https://docs.pypi.org/trusted-publishers/

  **Acceptance Criteria**:
  - [x] `README.md` includes a “Release” section mentioning tag/version match + `publish.yml`

  **QA Scenarios**:
  ```
  Scenario: Release docs are discoverable
    Tool: Bash
    Steps:
      - Run: rg -n "Release" README.md
      - Run: rg -n "publish.yml" README.md
      - Run: rg -n "Trusted" README.md
    Expected:
      - README contains clear, minimal release steps and links
    Evidence: .sisyphus/evidence/task-4-readme-release-grep.txt

  Scenario: Docs mention the version guard (edge)
    Tool: Bash
    Steps:
      - Run: rg -n "pyproject" README.md
      - Run: rg -n "vX\.Y\.Z" README.md
    Expected:
      - README instructs that tag version must match `pyproject.toml`
    Evidence: .sisyphus/evidence/task-4-readme-version-guard.txt
  ```

  **Commit**: NO

## Final Verification Wave (4 parallel agents, ALL must APPROVE)
- [x] F1. Plan Compliance Audit — oracle
- [x] F2. Code Quality Review — unspecified-high
- [x] F3. Workflow Safety Review — unspecified-high
- [x] F4. Scope Fidelity Check — deep

## Commit Strategy
- Default: leave changes uncommitted unless explicitly requested.
- If committing:
  - Commit 1: `ci: add GitHub Actions workflow` (English message)
  - Commit 2: `release: publish to PyPI via OIDC` (English message)
  - Commit 3: `docs: document release process` (English message)

## Success Criteria
- CI workflow runs on PRs and blocks regressions.
- Publish workflow is ready for first tag release once PyPI pending publisher is configured.
