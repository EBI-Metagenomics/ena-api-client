#!/usr/bin/env python
"""Fetch ENA's own API definitions into ``snapshots/``.

Two phases, like ena-api-handler's generator: **fetch** (ENA -> snapshots) and
**generate** (snapshots -> ``src/ena_api/models/``).  Only the fetch phase
exists so far; ``--generate`` is added in the next phase.

Run it from the repository root::

    uv run scripts/generate_models.py --dry-run
    uv run scripts/generate_models.py

Snapshots are committed, so ``git diff snapshots/`` is the record of what ENA
changed.  A snapshot is rewritten only when its *meaning* changed — for a spec,
the set of operations, parameters, response content types and schema names; for
report fields, the field set — so Springdoc's renumbered ``operationId``s and
other cosmetic churn don't show up as a diff.

Fetching report fields needs Webin credentials (``ENA_WEBIN``,
``ENA_WEBIN_PASSWORD``), because the Reports spec carries no response schemas:
the field set has to come from real rows.  That fetch always targets ENA's
``wwwdev`` test service, and **only key names and inferred types are written,
never values**.  Without credentials it is skipped and the committed snapshot
(seeded from this repo's test fixtures) stands.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Final

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ena_api.config import WebinConfig  # noqa: E402

log = logging.getLogger("generate_models")

ROOT: Final = Path(__file__).resolve().parents[1]
SNAPSHOTS: Final = ROOT / "snapshots"

#: The OpenAPI definitions ENA publishes for the three APIs this client wraps.
API_DOCS: Final[dict[str, str]] = {
    "webin": "https://www.ebi.ac.uk/ena/submit/webin-v2/v3/api-docs",
    "reports": "https://www.ebi.ac.uk/ena/submit/report/v3/api-docs",
    "browser": "https://www.ebi.ac.uk/ena/browser/api/v3/api-docs",
}

#: The receipt XSD, source of the receipt's entity tags.
RECEIPT_XSD_URL: Final = "https://ftp.ebi.ac.uk/pub/databases/ena/doc/xsd/sra_1_5/SRA.receipt.xsd"

#: Reports entity -> generated class-name segment.
REPORT_ENTITIES: Final[dict[str, str]] = {
    "projects": "Study",
    "samples": "Sample",
    "runs": "Run",
    "experiments": "Experiment",
    "analyses": "Analysis",
    "run-process": "RunProcess",
    "files": "File",
}

#: Hand-curated descriptions for report fields; ENA documents none.
REPORT_FIELD_DESCRIPTIONS: Final[dict[str, str]] = {}

#: Seed field sets, from this repo's recorded fixtures — so the repo has usable
#: snapshots even if nobody ever runs an authenticated fetch.  An authenticated
#: fetch only ever adds to these.
SEED_REPORT_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "projects": ("id", "studyAlias", "studyTitle", "studyAccession", "secondaryAccession", "releaseStatus"),
    "samples": ("id", "sampleAlias", "sampleTitle", "sampleAccession", "secondaryAccession", "releaseStatus"),
    "runs": (
        "id",
        "runAlias",
        "runAccession",
        "experimentAccession",
        "studyAccession",
        "sampleAccession",
        "releaseStatus",
    ),
    "experiments": (
        "id",
        "experimentAlias",
        "experimentAccession",
        "experimentTitle",
        "studyAccession",
        "sampleAccession",
        "releaseStatus",
    ),
    "analyses": ("id", "analysisAlias", "analysisAccession", "analysisTitle", "studyAccession", "releaseStatus"),
    "run-process": ("id", "processStatus", "processDate", "errorMessage"),
    "files": ("id", "runAccession", "fileName", "checksum", "checksumMethod"),
}

#: JSON value type -> snapshot type, matching ena-api-handler's vocabulary.
JSON_TYPE_MAP: Final[dict[type, str]] = {str: "text", bool: "boolean", int: "numeric", float: "numeric"}

TIMEOUT: Final = 60.0


# --------------------------------------------------------------------------- IO


def _get(url: str, **kwargs: Any) -> httpx.Response:
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True, **kwargs)
    response.raise_for_status()
    return response


def _write(path: Path, content: str | bytes, *, dry_run: bool) -> None:
    """Write ``content``, announcing it; a no-op under ``--dry-run``."""
    log.info("%s %s", "would write" if dry_run else "writing", path.relative_to(ROOT))
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


# ------------------------------------------------------------------- OpenAPI


def spec_signature(spec: dict[str, Any]) -> list[str]:
    """The parts of a spec we actually depend on, as a sorted, comparable list.

    Springdoc renumbers ``operationId`` suffixes (``_1``, ``_2``) between
    deployments, so those are excluded — this is the OpenAPI equivalent of the
    handler comparing report snapshots by ``columnId``.

    >>> spec_signature({"paths": {"/x": {"get": {"parameters": [{"name": "q"}]}}}})
    ['op GET /x params=q', 'schemas ']
    """
    lines: list[str] = []
    for path, operations in sorted(spec.get("paths", {}).items()):
        for method, operation in sorted(operations.items()):
            if not isinstance(operation, dict):
                continue
            params = sorted(p.get("name", "") for p in operation.get("parameters", []))
            content = sorted(
                ct
                for response in operation.get("responses", {}).values()
                if isinstance(response, dict)
                for ct in response.get("content", {})
            )
            line = f"op {method.upper()} {path} params={','.join(params)}"
            if content:
                line += f" content={','.join(content)}"
            lines.append(line)
    schemas = sorted(spec.get("components", {}).get("schemas", {}))
    lines.append(f"schemas {','.join(schemas)}")
    return lines


def fetch_openapi(api: str, *, dry_run: bool, skip_fetch: bool, ignore_snapshots: bool) -> None:
    """Snapshot one OpenAPI definition, rewriting it only when it means something new."""
    path = SNAPSHOTS / api / "openapi.json"
    if skip_fetch:
        log.info("%s: skipping fetch", api)
        return

    spec = _get(API_DOCS[api]).json()
    text = json.dumps(spec, indent=2, sort_keys=True) + "\n"

    if path.exists() and not ignore_snapshots:
        old = json.loads(path.read_text(encoding="utf-8"))
        if spec_signature(old) == spec_signature(spec):
            log.info("%s: unchanged (%d paths)", api, len(spec.get("paths", {})))
            return
        log.info("%s: definition changed", api)
    _write(path, text, dry_run=dry_run)


def fetch_receipt_xsd(*, dry_run: bool, skip_fetch: bool, ignore_snapshots: bool) -> None:
    """Snapshot the submission receipt XSD, rewriting it only when the bytes change."""
    path = SNAPSHOTS / "webin" / "SRA.receipt.xsd"
    if skip_fetch:
        log.info("receipt xsd: skipping fetch")
        return

    content = _get(RECEIPT_XSD_URL).content
    if path.exists() and not ignore_snapshots and path.read_bytes() == content:
        log.info("receipt xsd: unchanged")
        return
    _write(path, content, dry_run=dry_run)


# ------------------------------------------------------------- report fields


def infer_type(value: Any) -> str:
    """Map a JSON value to the snapshot's type vocabulary.

    >>> infer_type("ERS1"), infer_type(3), infer_type(True), infer_type(None)
    ('text', 'numeric', 'boolean', 'text')
    """
    return JSON_TYPE_MAP.get(type(value), "text")


def merge_fields(existing: list[dict[str, str]], found: dict[str, str]) -> list[dict[str, str]]:
    """Merge newly seen ``{columnId: type}`` into a snapshot's field list.

    Fields are added, never removed: a key absent from the sampled rows may
    simply have been empty in all of them.  Dropping a field is a deliberate
    hand edit to the snapshot.

    >>> merge_fields([{"columnId": "a", "description": "", "type": "text"}], {"b": "numeric"})
    [{'columnId': 'a', 'description': '', 'type': 'text'}, {'columnId': 'b', 'description': '', 'type': 'numeric'}]
    """
    types = {field["columnId"]: field["type"] for field in existing}
    types.update({column: kind for column, kind in found.items() if column not in types})
    return [
        {"columnId": column, "description": REPORT_FIELD_DESCRIPTIONS.get(column, ""), "type": types[column]}
        for column in sorted(types)
    ]


def load_fields(entity: str) -> list[dict[str, str]]:
    """The committed snapshot for ``entity``, or its seed when there isn't one yet."""
    path = SNAPSHOTS / "reports" / entity / "fields.json"
    if path.exists():
        fields: list[dict[str, str]] = json.loads(path.read_text(encoding="utf-8"))
        return fields
    return merge_fields([], dict.fromkeys(SEED_REPORT_FIELDS.get(entity, ()), "text"))


def sample_report_fields(entity: str, config: WebinConfig) -> dict[str, str]:
    """``{columnId: type}`` seen across up to 100 real rows from ``wwwdev``.

    Only key names and inferred types leave this function — no values.
    """
    response = httpx.get(
        f"{config.reports_url}/{entity}",
        params={"format": "json", "max-results": 100},
        auth=config.basic_auth(),
        timeout=TIMEOUT,
        follow_redirects=True,
    )
    if response.status_code == 404:
        log.warning("%s: no such report endpoint (404)", entity)
        return {}
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return {}

    found: dict[str, str] = {}
    for entry in payload:
        report = entry.get("report") if isinstance(entry, dict) else None
        if not isinstance(report, dict):
            continue
        for column, value in report.items():
            if value in (None, "") and column in found:
                continue
            found[column] = infer_type(value)
    return found


def fetch_report_fields(entity: str, *, dry_run: bool, skip_fetch: bool, ignore_snapshots: bool) -> None:
    """Snapshot one report entity's field set, from live rows when credentials allow."""
    path = SNAPSHOTS / "reports" / entity / "fields.json"
    existing = [] if ignore_snapshots else load_fields(entity)

    found: dict[str, str] = {}
    if skip_fetch:
        log.info("%s: skipping fetch", entity)
    else:
        config = report_credentials()
        if config is None:
            log.info("%s: skipping report fields (no ENA_WEBIN credentials)", entity)
        else:
            found = sample_report_fields(entity, config)

    fields = merge_fields(existing, found)
    text = json.dumps(fields, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        log.info("%s: unchanged (%d fields)", entity, len(fields))
        return
    _write(path, text, dry_run=dry_run)


def report_credentials() -> WebinConfig | None:
    """Webin credentials forced at the ``wwwdev`` test service, or ``None``."""
    try:
        config = WebinConfig()  # type: ignore[call-arg]  # values come from the environment
    except Exception:
        return None
    # Never sample the production account's rows: field names are all we want,
    # and wwwdev serves the same schema.
    return config.model_copy(update={"test": True})


# ------------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="report the writes without making them")
    parser.add_argument("--skip-fetch", action="store_true", help="use the committed snapshots, contact nothing")
    parser.add_argument("--ignore-snapshots", action="store_true", help="rewrite snapshots from scratch")
    parser.add_argument("--apis", default=",".join(API_DOCS), help=f"comma-separated: {','.join(API_DOCS)}")
    parser.add_argument("--entities", default=",".join(REPORT_ENTITIES), help="comma-separated report entities")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    flags = {"dry_run": args.dry_run, "skip_fetch": args.skip_fetch, "ignore_snapshots": args.ignore_snapshots}

    apis = [a for a in args.apis.split(",") if a]
    unknown = sorted(set(apis) - set(API_DOCS)) + sorted(set(args.entities.split(",")) - set(REPORT_ENTITIES) - {""})
    if unknown:
        parser.error(f"unknown api/entity: {', '.join(unknown)}")

    for api in apis:
        fetch_openapi(api, **flags)
    if "webin" in apis:
        fetch_receipt_xsd(**flags)
    for entity in (e for e in args.entities.split(",") if e):
        fetch_report_fields(entity, **flags)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
