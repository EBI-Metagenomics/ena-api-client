# ena-api-client

Typed Python client for the ENA Webin Submission and Reports APIs.

Wraps the two HTTP APIs used to submit data to and query records held under a
[ENA Webin](https://www.ebi.ac.uk/ena/submit/webin/) account:

- **Webin v2 Submission API** — submit XML payloads describing studies, samples, runs, experiments and analyses
- **Webin Reports API** — list records (private and public) owned by the authenticated Webin account

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

## Endpoints covered

### Webin v2 Submission API

| Method | Endpoint | Wrapper |
|--------|----------|---------|
| POST | `/ena/submit/webin-v2/submit` | `client.submit.xml(xml_bytes)` |
| POST | `/ena/submit/webin-v2/submit/queue` | `client.submit.xml_async(xml_bytes)` |
| GET | `/ena/submit/webin-v2/submit/poll/{job_id}` | `client.submit.poll(job_id)` |

### Webin Reports API

| Method | Endpoint | Wrapper |
|--------|----------|---------|
| GET | `/ena/submit/report/projects` | `client.reports.list_projects()` |
| GET | `/ena/submit/report/samples` | `client.reports.list_samples()` |
| GET | `/ena/submit/report/runs` | `client.reports.list_runs()` |
| GET | `/ena/submit/report/experiments` | `client.reports.list_experiments()` |
| GET | `/ena/submit/report/analyses` | `client.reports.list_analyses()` |
| GET | `/ena/submit/report/files` | `client.reports.list_files()` |

## Error handling

- HTTP 4xx/5xx → `httpx.HTTPStatusError`
- Reports endpoint returning 404 → empty list (no records yet)
- Reports endpoint returning 401/403 → `PermissionError`

## Development

```bash
pip install -e ".[dev]"
pre-commit install
pytest
ruff check ena_api/ tests/
black --check ena_api/ tests/
```

## License

Apache-2.0
