# Model generation

`generate_models.py` has two phases, like `ena-api-handler`'s generator:

| Phase | Direction | State |
|---|---|---|
| **fetch** | ENA → `snapshots/` | implemented |
| **generate** | `snapshots/` → `src/ena_api/models/` | not yet |

## Snapshots

`snapshots/` is committed, so `git diff snapshots/` is the record of what ENA
changed.

| Path | Source |
|---|---|
| `snapshots/{webin,reports,browser}/openapi.json` | ENA's own `v3/api-docs`, normalised (`indent=2`, `sort_keys=True`) |
| `snapshots/webin/SRA.receipt.xsd` | the SRA receipt schema |
| `snapshots/reports/<entity>/fields.json` | `[{columnId, description, type}]`, sorted by `columnId` |

A snapshot is rewritten only when its *meaning* changes — for a spec, the set of
operations, parameter names, response content types and schema names; for report
fields, the field set. Springdoc renumbers `operationId` suffixes (`_1`, `_2`)
between deployments, so those are excluded and don't show up as diffs.

## Report fields need credentials

The Reports spec has **no response schemas**, so a report's field set has to come
from real rows. With `ENA_WEBIN` and `ENA_WEBIN_PASSWORD` set, the script reads
up to 100 rows per entity and records **only key names and inferred types —
never values**. It forces ENA's `wwwdev` test service regardless of
`ENA_WEBIN_TEST`.

Fields are **added, never removed**: a key absent from the sampled rows may
simply have been empty in all of them. Dropping a field is a deliberate hand
edit to the snapshot.

Without credentials that fetch is skipped and the committed snapshot stands. The
first snapshots were seeded from this repo's test fixtures (`SEED_REPORT_FIELDS`),
so the repo works even if nobody ever runs an authenticated fetch.

## Usage

```bash
uv run scripts/generate_models.py --dry-run     # report the writes, make none
uv run scripts/generate_models.py               # fetch and update snapshots
uv run scripts/generate_models.py --skip-fetch  # use committed snapshots, contact nothing
uv run scripts/generate_models.py --ignore-snapshots          # rewrite from scratch
uv run scripts/generate_models.py --apis reports --entities runs,experiments
```

Always run `--dry-run` before a real fetch. Commit changed snapshots together
with the code regenerated from them.

## Hand-curated config

Constants at the top of the script, not derived from ENA:
`API_DOCS`, `RECEIPT_XSD_URL`, `REPORT_ENTITIES` (entity → class-name segment),
`REPORT_FIELD_DESCRIPTIONS`, `SEED_REPORT_FIELDS`, `JSON_TYPE_MAP`.

## Known drift

`GET /report/files` answers **404** on `wwwdev`, while `list_files()` calls it
and `_fetch` turns a 404 into `[]`. The spec has `/run-files`,
`/analysis-files` and `/unsubmitted-files` instead. Settled in Phase 4 of
`CODEGEN_PLAN.md`; the `files` snapshot is the seeded field set for now.
