# Software-version JSON rules and configuration viewer

> Store every existing software-version rule family in one self-contained JSON document containing
> a shared base and its quantification levels, then present those sections in a simple Studio viewer.

## Requirements

- Preserve the software-version coverage and conversion behavior that APB has now. This refactor
  changes document structure, not supported vendor versions, columns, layers, or calculations.
- Use exactly one parsing-rule JSON document per existing software-version grouping.
  - DIA-NN 1.x contains `ion`, `fragment`, and `protein`.
  - DIA-NN 2.x contains `ion` and `protein`.
  - The DIA-NN base and ion configuration are duplicated into both self-contained documents.
  - Spectronaut keeps its current `^(19|20)\\..*` grouping.
  - FragPipe, MaxQuant, PEAKS, and WOMBAT keep their current version patterns.
- Give every software document the same structure, including tools that currently expose only one
  level: top-level identity, `base`, and `levels`.
- Remove cross-file `$extends` inheritance. A level inherits only from `base` in the same document.
- Keep configuration schemas Pydantic-only:
  - the source document and its partial base/level fragments are validated by Pydantic;
  - every merged level is validated as the existing effective `ParseRule`;
  - operational paths, editor state, and catalog entries are not configuration schemas.
- Keep the existing merge behavior: nested objects merge, scalar values and scalar arrays replace,
  and arrays of rule objects append in base-to-level order.
- Make `--rule-config` accept the same document format as packaged rules. With `LEVEL`, it converts
  that level; without `LEVEL`, it converts every matching level and emits MuData when appropriate.
- Observation annotation tables are external resources; this document format applies only to parsing rules.
- Make Studio primarily a configuration viewer:
  - compact catalog containing software and version documents, not one row per level;
  - selecting a document shows its `Base` section;
  - `Base` and available levels are separate editor tabs;
  - tabs show raw source sections only—no separate Effective JSON view;
  - editors are read-only until the user explicitly chooses **Edit**;
  - editing `base` validates every level; editing one level validates that merged level;
  - invalid or stale content cannot be saved.
- Keep the test-data File / Submission JSON / Parameters detail panel inside the Data tab so it is
  not visible below Configuration.

Acceptance means all migrated effective rules produce the same conversion behavior, both package
test suites and Ruff pass, `apb validate` validates every document and level, the old `$extends`
format is absent, and Studio starts with the simplified viewer.

## Design

### Source document

Each file is self-contained. Existing version folders remain useful organization; for example,
`diann/v1/rules.json`, `diann/v2/rules.json`, and `spectronaut/rules.json`.

```json
{
  "schema_version": "0.1",
  "file_version": "1",
  "software_name": "DIA-NN",
  "software_version": "^1\\\\..*",
  "base": {
    "input_shape": "long",
    "axis": {
      "obs_keys": ["Run"],
      "duplicates": {"mode": "error"}
    },
    "columns": {
      "obs": {"select": {"Run": "Run"}}
    },
    "modifications": {}
  },
  "levels": {
    "ion": {
      "axis": {
        "var_keys": ["ProForma_ion"],
        "x_layer": "Precursor_Normalised"
      },
      "columns": {},
      "layers": []
    },
    "fragment": {},
    "protein": {}
  }
}
```

The `levels` key is the quantification level; level blocks do not repeat
`quantification_level`. Document identity fields remain at the top and cannot be overridden by a
level.

### Pydantic models and resolution

- Add strict partial models for axis, columns, and rule fragments. They forbid unknown keys while
  allowing fields that become required only after merging.
- Add `ParseRuleDocument` with top-level identity, `base`, and a non-empty mapping from the existing
  `QuantificationLevel` literal to fragments.
- `ParseRuleDocument.effective_rule(level)` merges the base and selected fragment, injects the
  top-level identity plus the level key, and calls `ParseRule.model_validate(...)`.
- Document validation resolves every declared level immediately, so a source file cannot be valid
  while containing an invalid effective rule.
- The existing `ParseRule` remains the only model consumed by converters.

### Registry and CLI

- Discover `rules.json` documents rather than `parse_*.json` leaves and bases.
- Represent a runnable packaged rule by document path plus level. This locator is operational data,
  not another configuration model.
- Resolve the existing version groups without altering their version regex coverage.
- Update recognition, listing, validation, schema export, and tests to iterate effective levels from
  each document.
- Replace the single-level external override path with bundle-aware selection while preserving the
  normal output behavior.

### Studio

- The catalog groups one entry per software-version document and uses small typography with no wide
  path/version columns. The path is available as secondary text or a tooltip.
- Loading a document creates `Base` plus one tab per level. Each tab contains the raw fragment JSON,
  not a merged rule.
- One section can enter edit mode at a time. **Cancel/Revert** restores its on-disk value. **Save**
  reconstructs and validates the complete source document, checks the original content hash, and
  atomically replaces the file while preserving permissions.
- Validation errors name the affected level and JSON path. Effective rules remain an internal
  validation result rather than another visible editor.

## Implementation plan

- [x] Add strict partial Pydantic models and `ParseRuleDocument`; retain `ParseRule` as the effective
  converter contract.
- [x] Replace `$extends` resolution with same-document base/level resolution.
- [x] Migrate all packaged rules to `rules.json` documents and prove behavior parity for every
  previous effective leaf.
- [x] Refactor registry, recognition, conversion selection, `--rule-config`, validation, listing,
  and JSON Schema export around document-plus-level locators.
- [x] Rewrite APB tests and documentation for the new canonical structure.
- [x] Refactor Studio's backend to load, validate, and atomically save individual sections within a
  complete document.
- [x] Replace the wide catalog and dual-editor layout with the compact document catalog and
  read-only Base/level tabs; move Data details into the Data tab.
- [x] Update Studio tests and documentation.
- [x] Run Ruff, both complete pytest suites, `apb validate`, CLI smoke tests, and a live Dash HTTP
  startup check.

## Open questions

None. Implementation details such as exact helper names and visual spacing do not change the agreed
behavior and are left to implementation.
