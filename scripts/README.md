# Model generation

`generate_models.py` has two phases, like `ena-api-handler`'s generator:

| Phase | Direction | State |
|---|---|---|
| **fetch** | ENA → `snapshots/` | implemented |
| **generate** | `snapshots/` → `src/ena_api/models/` | implemented |

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

## Generated code

Everything under `src/ena_api/models/` starts with an `AUTO-GENERATED`
header and is never edited by hand — change the generator or a snapshot and
re-run. CI regenerates with `--skip-fetch` and fails on any diff.

| Module | From |
|---|---|
| `models/reports/<entity>.py` | that entity's `fields.json` plus `REPORT_MODEL_FIELDS` and `REPORT_FIELD_ALIASES` |
| `models/__init__.py` | `ReportEntity`, `REPORT_MODELS`, `XML_ENTITIES` (entities the Reports spec serves XML for), `RECEIPT_ENTITY_TAGS` (the receipt XSD's `RECEIPT` children) |
| `models/endpoints.py` | the allow-listed `OPERATIONS`, with each one's query parameters as the spec lists them |
| `models/webin.py` | the `EntityModelWebinSubmission` schema |

Generation **fails** when an `OPERATIONS` entry, or a query parameter one of
the proxies passes, is missing from its snapshot. That failure is the drift
alarm. A declared model field whose aliases match nothing in the snapshot is a
warning, not an error: a key can be missing from a snapshot simply because it
was empty in every sampled row.

`models/__init__.py` also re-exports `types.py`'s handwritten receipt models,
so `from ena_api.models import …` still resolves every name it used to.

## Usage

```bash
uv run scripts/generate_models.py --dry-run     # report the writes, make none
uv run scripts/generate_models.py               # fetch and update snapshots
uv run scripts/generate_models.py --skip-fetch  # generate from committed snapshots, contact nothing
uv run scripts/generate_models.py --skip-generate  # update snapshots only
uv run scripts/generate_models.py --ignore-snapshots          # rewrite from scratch
uv run scripts/generate_models.py --apis reports --entities runs,experiments
```

Always run `--dry-run` before a real fetch. Commit changed snapshots together
with the code regenerated from them.

## Hand-curated config

Constants at the top of the script, not derived from ENA:
`API_DOCS`, `RECEIPT_XSD_URL`, `REPORT_ENTITIES` (entity → class-name segment),
`REPORT_FIELD_DESCRIPTIONS`, `SEED_REPORT_FIELDS`, `JSON_TYPE_MAP`,
`REPORT_FIELD_ALIASES` (normalised name → raw report keys),
`REPORT_MODEL_FIELDS` (the fields each model declares), `FIELD_DEFAULTS`,
`ENA_TYPE_MAP`, `OPERATIONS`, `PACKAGE`.

`REPORT_MODEL_FIELDS` is not derivable from the alias table: a
`/report/projects` row carries `studyAccession` as the record's *own*
accession, not as a foreign key, so `StudyReport` declares `accession` and not
`study_accession`. Every raw key no declared field maps stays an
`extra="allow"` passthrough, which is what keeps `model_dump()` compatible.

## Known drift

`GET /report/files` answers **404** on `wwwdev` (checked 2026-09-18) and is not
in the spec; `_fetch` turned that 404 into `[]`, so `list_files()` had been
silently returning nothing. It now calls `/run-files`, which is in the spec, as
are `/analysis-files` and `/unsubmitted-files` — neither is wrapped yet. The
`run-files` snapshot is still the seeded field set, because the test account has
no run files to sample.
