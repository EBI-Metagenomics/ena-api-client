# ena-api-client

Typed Python client for the ENA Webin Submission and Reports APIs.

Wraps the two HTTP APIs used to submit data to and query records held under a
[ENA Webin](https://www.ebi.ac.uk/ena/submit/webin/) account:

- **Webin v2 Submission API** — submit XML payloads describing studies, samples, runs, experiments and analyses
- **Webin Reports API** — list records (private and public) owned by the authenticated Webin account
- **Run processing status** — `/report/run-process`: whether ENA has finished validating
  and archiving a run's read files, which the run report itself does not say.
- **Record XML** — `reports.xml(entity, accessions)`: the account's own records as submitted,
  checklist attributes and all, private ones included. This is the source a MODIFY patches.
- **ENA Browser API** — the current XML of a *released* record, whoever submitted it. It answers
  404 for a private record with or without credentials, which is why `reports.xml` exists.

## Installation

```bash
pip install ena-api-client
```

For local development:

```bash
git clone https://github.com/timrozday/ena-api-client
cd ena-api-client
pip install -e ".[dev]"
```

## Configuration

Credentials are read from environment variables (never from CLI args, to keep
secrets out of shell history and process listings):

| Variable | Description |
|----------|-------------|
| `ENA_WEBIN` | Webin account ID (e.g. `Webin-12345`) |
| `ENA_WEBIN_PASSWORD` | Webin account password |
| `ENA_WEBIN_TEST` | `true` to target the test environment (`wwwdev.ebi.ac.uk`); default `false` |

You can also pass a `WebinConfig` explicitly:

```python
from ena_api import WebinClient, WebinConfig

config = WebinConfig(webin_id="Webin-12345", password="secret", test=True)
client = WebinClient(config=config)
```

## Usage

### Submitting XML

```python
from ena_api import WebinClient

client = WebinClient()  # reads env vars

with open("samples.xml", "rb") as fh:
    receipt = client.submit.xml(fh.read())

print(receipt.success)
for acc in receipt.accessions:
    print(acc.alias, acc.accession, acc.status)
```

For payloads larger than ~15 MB, use the async queue:

```python
job_id = client.submit.xml_async(large_xml_bytes)

while (receipt := client.submit.poll(job_id)) is None:
    time.sleep(5)

print(receipt.success)
```

### Submission actions

Cancel, suppress, kill, hold, and release existing objects without
hand-building the action XML:

```python
receipt = client.submit.cancel("ERZ1234567")  # remove a private object
receipt = client.submit.suppress("ERS9000001")  # hide a public object
receipt = client.submit.hold("ERS9000001", "2026-12-31")  # (re)set the release date
receipt = client.submit.release("ERS9000001")  # make a private object public
receipt = client.submit.kill("ERZ1234567")  # admin-only, irreversible
```

Each accepts an optional `alias` keyword for the generated submission
envelope; one is auto-generated if omitted.

### Listing records

```python
projects = client.reports.list_projects()
samples = client.reports.list_samples(max_results=100)
runs = client.reports.list_runs()
experiments = client.reports.list_experiments()
analyses = client.reports.list_analyses()
files = client.reports.list_files()
```

Each method returns a list of typed Pydantic models with fields such as
`alias`, `accession`, `title`, and `status`. Records include both private
(held) and public (released) entries owned by the Webin account.

### Fetching a record's XML

```python
xml_bytes = client.browser.xml("ERS9000001")
```

The Browser API serves the *current* XML document of a registered object;
Webin Basic auth is what makes a private (held) record readable. This is the
first half of a safe MODIFY — an ENA MODIFY replaces the whole object, so a
one-field change means fetch, patch, resubmit. The patching half lives in
[`ena-submission-toolkit`](https://github.com/timrozday-mgnify/ena-submission-toolkit)
(`records.modify_records`).

## Endpoints covered

### Webin v2 Submission API

| Method | Endpoint | Wrapper |
|--------|----------|---------|
| POST | `/ena/submit/webin-v2/submit` | `client.submit.xml(xml_bytes)` |
| POST | `/ena/submit/webin-v2/submit/queue` | `client.submit.xml_async(xml_bytes)` |
| GET | `/ena/submit/webin-v2/submit/poll/{job_id}` | `client.submit.poll(job_id)` |

`cancel`, `suppress`, `kill`, `hold`, and `release` (see [Submission
actions](#submission-actions)) all build a small action XML document and
POST it to `/ena/submit/webin-v2/submit` as well.

### Webin Reports API

| Method | Endpoint | Wrapper |
|--------|----------|---------|
| GET | `/ena/submit/report/projects` | `client.reports.list_projects()` |
| GET | `/ena/submit/report/samples` | `client.reports.list_samples()` |
| GET | `/ena/submit/report/runs` | `client.reports.list_runs()` |
| GET | `/ena/submit/report/experiments` | `client.reports.list_experiments()` |
| GET | `/ena/submit/report/analyses` | `client.reports.list_analyses()` |
| GET | `/ena/submit/report/run-process` | `client.reports.list_run_processes()` |
| GET | `/ena/submit/report/run-files` | `client.reports.list_files()` |
| GET | `/ena/submit/report/{entity}/xml/{ids}` | `client.reports.xml(entity, accessions)` |

### ENA Browser API

| Method | Endpoint | Wrapper |
|--------|----------|---------|
| GET | `/ena/browser/api/xml/{accession}` | `client.browser.xml(accession)` |
| GET | `/ena/browser/api/xml/{accessions}` | `client.browser.xml_many(accessions)` |

Every path above is checked against ENA's own OpenAPI definitions: it is the
`OPERATIONS` allow-list in `scripts/generate_models.py`, and generation fails
if ENA stops serving one of them or drops a parameter this client passes.

## Regenerating models

Report row models, the endpoint table, the report-entity lookups and the
receipt's entity tags all live under `src/ena_api/models/` and are **generated**
from committed snapshots of ENA's definitions:

```bash
uv run scripts/generate_models.py --dry-run     # report the writes, make none
uv run scripts/generate_models.py --skip-fetch  # regenerate from the snapshots
uv run scripts/generate_models.py               # refresh the snapshots too
```

Don't edit anything with an `AUTO-GENERATED` header. See
[`scripts/README.md`](scripts/README.md) for the snapshot format, what needs
credentials, and the hand-curated configuration.

## Error handling

- HTTP 4xx/5xx → `httpx.HTTPStatusError`
- Reports endpoint returning 404 → empty list (no records yet)
- Reports endpoint returning 401/403 → `ENAAuthError`
- Browser endpoint returning 401/403 → `ENAAuthError`; 404 or an empty body → `ENANotFoundError`
- An implausible accession (anything outside `[A-Za-z0-9._-]{3,64}`), or an unknown
  entity → `ENAInvalidAccessionError`, before any request is made

The three subclass `ENAClientError` and, respectively, `PermissionError`,
`LookupError` and `ValueError` — so code that catches the built-ins keeps
working.

## Development

```bash
uv sync
uv run pytest
uv run pytest -m integration   # talks to ENA; report calls need credentials
uv run mypy src tests
uv run ruff check .
uv run ruff format --check .
```

## License

Apache-2.0
