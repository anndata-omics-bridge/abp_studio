<!-- Managed by agent: keep commands and file references verified -->
<!-- Last updated: 2026-07-23 | Last verified: 2026-07-23 -->

# AGENTS.md - GitHub workflows

## Overview

Applies to GitHub Actions workflows in this directory.

## Files

| File | Purpose |
| --- | --- |
| `ci.yml` | Pull-request and main-branch quality gate |
| `pages.yml` | Strict documentation build and Pages deployment |
| `security.yml` | Weekly and manual dependency audit |

## Setup

GitHub runners install Python through uv and sync only from `uv.lock`. CI and
security jobs recreate the local sibling workspace by checking out the pinned
APB revision at `../apb`.

## Build/Tests

Run the pre-commit and pre-push stages from the repository root before changing
workflow commands. `.pre-commit-config.yaml` is the command source of truth.

## Code style

- Preserve full Git history for changed-line coverage.
- Keep permissions minimal and action versions explicit.

## Security

- Do not add secrets or `secrets: inherit`.
- Add a local hook before adding a blocking CI-only command.

## Checklist

- Parse workflow YAML.
- Run both hook stages locally.
- Confirm the scheduled audit invokes the manual local hook.

## Examples

Use `ci.yml` for mirrored local gates and `security.yml` for scheduled manual
hooks.

## When stuck

Compare workflow commands with `.pre-commit-config.yaml`; the hook definition is
the command source of truth.
