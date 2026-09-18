# ena-api-client

Typed Python client for the ENA Webin Submission, Reports, and Browser APIs.
The public import name is `ena_api` and must remain stable for downstream
projects such as `ena-submission-toolkit`.

## Package layout

- `src/ena_api/` contains the installable package.
- `tests/` contains unit, golden-compatibility, and future integration tests.

The current package code is handwritten. Once the generator is introduced,
generated files will have an `AUTO-GENERATED` header and must not be edited by
hand. Handwritten client, configuration, proxy, processing, type, and exception
modules remain the place for behaviour that is not derived from ENA definitions.

Keep the compatibility contract intact during the transition:

- Preserve the public names in `ena_api.__all__`.
- Preserve existing `model_dump()` keys and values, including raw extra report
  fields.
- Keep exceptions compatible with callers that catch `PermissionError`,
  `LookupError`, `ValueError`, and `httpx.HTTPStatusError`.
- Keep `ENA_WEBIN`, `ENA_WEBIN_PASSWORD`, and `ENA_WEBIN_TEST` as the
  configuration environment variables.

## Commands

```bash
uv sync
uv run pytest
uv run pytest -m integration
uv run mypy src tests
uv run ruff check .
uv run ruff format --check .
```

Integration tests require suitable ENA credentials and are deselected by
default. `ENA_WEBIN_TEST=1` or `ENA_WEBIN_TEST=true` targets ENA's `wwwdev`
test service.

## Regenerating models

`scripts/generate_models.py` has both phases: fetch (ENA's API definitions and
report field sets into the committed `snapshots/` tree) and generate (snapshots
into `src/ena_api/_generated/`, which moves to `models/` once the handwritten
`models.py` it would shadow is gone). Nothing imports the generated code yet.
See `scripts/README.md`.

Do not edit snapshots to add fields; run the script. Use `--dry-run` before a
fetch, commit changed snapshots with their regenerated code, and keep outputs
deterministic — a second run must change nothing.
