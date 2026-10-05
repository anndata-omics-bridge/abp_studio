# Development

Install the locked development and documentation environment:

```bash
uv sync --frozen --extra dev --group docs
```

The `aggregate` workflow runs the private `apb-aggregate` command, which APB Studio does not install. Install it once with `uv tool install --editable ../apb-aggregate`, or pass `--aggregate-executable`; every other workflow runs without it.

The local hooks are the source of truth for GitHub Actions.

## Every commit

```bash
uv run pre-commit run --hook-stage pre-commit --all-files
```

This runs Ruff, strict Pyright, dependency validation, and the
type-checker-ignore guard.

## Every push

```bash
uv run pre-commit run --hook-stage pre-push --all-files
```

This runs tests with line and branch coverage, changed-line coverage, wheel
inspection, and a strict documentation build.

## Dependency audit

```bash
uv run pre-commit run dependency-audit --hook-stage manual --all-files
```

GitHub Actions runs the same audit weekly.
