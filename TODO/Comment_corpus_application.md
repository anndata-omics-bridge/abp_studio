# Comment on TODO_corpus_application.md

*Reviewer: Claude — 2026-07-22. Opinion only; plan not authorized.*

## Verdict

Sound plan, worth doing. The core move — make APB's parsing-rule JSONs (via
`available_targets()`) the *only* capability authority and delete
`MULTI_LEVEL_VENDORS` / `SINGLE_LEVEL_VENDOR_LEVELS` / per-dataset `level` — is a
genuine simplification, not a rewrite for its own sake. It replaces two hand-maintained
vendor tables (which will drift from APB) with the function APB already exposes. Ship it.

I verified the load-bearing claims: `available_targets()` exists and already appends
MuData when any level resolves (`apb/.../converters/pipeline.py:106`); the cached
header/version/targets path already exists in `testdata.py:144-180` (so extracting it is
real reuse, not new code); APB has both peptide FASTA *validation* and protein FASTA
*annotation*, so "FASTA for all levels, no `N/A`" is actually supported.

## One thing to weigh before implementing

**Scope honesty.** This is a large multi-file refactor (Target gains branch identity,
   provenance keying changes, Snakefile output routing, full `dashboard.py` rebuild). The
   doc is already structured as plan-then-approve, which is right. Just don't let the
   "compact monitor" framing hide that the pipeline core and provenance model change
   underneath — those are the risky parts, the UI is the easy part.

## Smaller notes

- Branch-qualified filenames (`ion.h5ad`, `ion.annotated.h5ad`, …) + one sidecar per
  artifact is the right call over a shared provenance store keyed by stage name; it makes
  collisions structurally impossible instead of relying on correct keying.
- "Missing resource → visible static FAILED cell, not a DAG-construction failure" is the
  single most important robustness requirement here. Make sure a module with no annotation
  TOML still lets every other module's branches into the Snakemake invocation. Test this
  explicitly (the plan does — good).
- Keep the deferred summary-field set genuinely small on first pass. The "always rather
  less" rule is easy to write and hard to hold; resist adding metrics during
  implementation review.

## Bottom line

No objections to the direction. Just go in aware that this touches the pipeline core,
not only the dashboard.
