# Drift fixture cases (LD-347)

Regression fixtures for source-documentation comparison. Each folder is one Pull Request that
changes one file; `tests/test_drift_cases.py` runs it twice (analyzer results / diff only) and
requires the findings to match `case.json` **exactly**: a missing finding is a regression, an
extra one is a false positive.

| File | Content |
|---|---|
| `before.py`, `after.py` | the changed file at the base and head commit |
| `before.json`, `after.json` | the analyzer's result for each (generated, see below) |
| `docs/` | the documentation at the head commit (`README.md`, `docs/api.md`, ...) |
| `case.json` | `description`, `path`, `status` (`modified`, `renamed`...), `previous_path`, `expected` = list of `[type, kind, entity, document]`, optional `expected_patch` (diff-only mode) and `warnings` |

Folder names start with the category: `referential_`, `signature_`, `semantic_`,
`unchanged_docs_` (documentation that is up to date or unrelated: no finding) and `no_change_`
(Pull Requests that change nothing documented: no finding).

## Add a case

1. Create a folder with `before.py`, `after.py`, `docs/...` and `case.json`.
2. From the repository root, generate the analyzer results:

   ```bash
   python ai-service/scripts/capture_drift_cases.py
   ```

3. Run `pytest -q tests/test_drift_cases.py` in `ai-service/`.
