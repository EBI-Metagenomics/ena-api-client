#!/usr/bin/env python
"""Generate ``ena_api``'s models from ENA's own API definitions.

Two phases, like ena-api-handler's generator: **fetch** (ENA -> snapshots) and
**generate** (snapshots -> ``src/ena_api/models/``).  Both run by default;
``--skip-fetch`` runs the generate phase alone, off the committed snapshots.

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
import importlib.util
import json
import logging
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import httpx

# Loaded straight from its file rather than imported as ``ena_api.config``:
# importing the package would import the very code this script writes, which
# need not exist yet.
_CONFIG_SPEC = importlib.util.spec_from_file_location(
    "_ena_api_config", Path(__file__).resolve().parents[1] / "src" / "ena_api" / "config.py"
)
assert _CONFIG_SPEC is not None and _CONFIG_SPEC.loader is not None
_config = importlib.util.module_from_spec(_CONFIG_SPEC)
# Registered before it runs, so pydantic can resolve the module's own
# annotations (``from __future__ import annotations`` makes them strings).
sys.modules[_CONFIG_SPEC.name] = _config
_CONFIG_SPEC.loader.exec_module(_config)

if TYPE_CHECKING:
    from ena_api.config import WebinConfig
else:
    WebinConfig = _config.WebinConfig

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
    "run-files": "File",
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
    "run-files": ("id", "runAccession", "fileName", "checksum", "checksumMethod"),
}

#: JSON value type -> snapshot type, matching ena-api-handler's vocabulary.
JSON_TYPE_MAP: Final[dict[type, str]] = {str: "text", bool: "boolean", int: "numeric", float: "numeric"}

TIMEOUT: Final = 60.0

# ------------------------------------------------------- generate-phase config

#: The package the generated code lives in.  The merge into ena-api-handler
#: changes this one line (see CODEGEN_PLAN.md §1.2.1); generated code itself
#: only ever uses relative imports.
PACKAGE: Final = "ena_api"

#: Where the generated modules are written.
OUTPUT: Final = ROOT / "src" / PACKAGE.replace(".", "/") / "models"

HEADER: Final = f"# AUTO-GENERATED by scripts/{Path(__file__).name} — do not edit manually.\n"

#: ``(str, Enum)`` rather than ``StrEnum``: the same form ena-api-handler
#: generates, so the two generators stay one copy when they merge.
ENUM_HEADER: Final = HEADER + "# ruff: noqa: UP042\n"

#: Snapshot type -> Python type, with the default value a report field gets.
ENA_TYPE_MAP: Final[dict[str, tuple[str, str]]] = {
    "text": ("str", '""'),
    "numeric": ("float", "0.0"),
    "boolean": ("bool", "False"),
}

#: Normalised field name -> the raw report keys that may carry it.  Moved
#: verbatim from ``reports.py``; hand-curated, ENA documents none of this.
REPORT_FIELD_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "alias": ("alias", "studyAlias", "sampleAlias", "runAlias", "experimentAlias", "analysisAlias"),
    "accession": (
        "accession",
        "studyAccession",
        "sampleAccession",
        "runAccession",
        "experimentAccession",
        "analysisAccession",
        "id",
    ),
    "secondary_accession": ("secondaryAccession", "secondaryId"),
    "title": ("title", "studyTitle", "sampleTitle", "experimentTitle", "analysisTitle"),
    "status": ("releaseStatus", "status"),
    "experiment_accession": ("experimentAccession", "experimentId"),
    "study_accession": ("studyAccession", "studyId"),
    "sample_accession": ("sampleAccession", "sampleId"),
    "run_accession": ("runAccession", "runId", "id"),
    "process_status": ("processStatus", "process_status"),
    "process_date": ("processDate", "process_date"),
    "error_message": ("errorMessage", "error_message", "errorMessages"),
    "filename": ("filename", "fileName", "name"),
    "checksum": ("checksum", "md5"),
    "checksum_method": ("checksumMethod", "checksum_method"),
}

#: The normalised fields each report model declares, in declaration order.
#: Not derivable from the alias table: ``/report/projects`` rows carry
#: ``studyAccession`` as the record's *own* accession, not as a foreign key, so
#: ``StudyReport`` declares ``accession`` and not ``study_accession``.  A field
#: here whose aliases match nothing in the entity's snapshot is a drift alarm.
#: Every other raw key stays an ``extra="allow"`` passthrough, which is what
#: keeps ``model_dump()`` compatible (CODEGEN_PLAN.md §0.4).
REPORT_MODEL_FIELDS: Final[dict[str, tuple[str, ...]]] = {
    "projects": ("alias", "accession", "secondary_accession", "status", "title"),
    "samples": ("alias", "accession", "secondary_accession", "status", "title"),
    "runs": (
        "alias",
        "accession",
        "secondary_accession",
        "status",
        "experiment_accession",
        "study_accession",
        "sample_accession",
    ),
    "experiments": (
        "alias",
        "accession",
        "secondary_accession",
        "status",
        "title",
        "study_accession",
        "sample_accession",
    ),
    "analyses": ("alias", "accession", "secondary_accession", "status", "title", "study_accession"),
    "run-process": ("run_accession", "process_status", "process_date", "error_message"),
    "run-files": ("accession", "run_accession", "filename", "checksum", "checksum_method"),
}

#: Field defaults that aren't their type's default.
FIELD_DEFAULTS: Final[dict[str, str]] = {"status": '"UNKNOWN"'}

#: The operations the handwritten proxies actually call: ``(constant, api,
#: method, path, params the proxy passes)``.  Generation **fails** when one of
#: these, or one of its parameters, is missing from the snapshot — that failure
#: is the drift alarm.
OPERATIONS: Final[tuple[tuple[str, str, str, str, tuple[str, ...]], ...]] = (
    ("SUBMIT", "webin", "POST", "/submit", ()),
    ("SUBMIT_QUEUE", "webin", "POST", "/submit/queue", ()),
    ("SUBMIT_POLL", "webin", "GET", "/submit/poll/{submissionId}", ()),
    ("BROWSER_XML", "browser", "GET", "/xml/{accession}", ()),
    ("REPORT_PROJECTS", "reports", "GET", "/projects", ("format", "max-results")),
    ("REPORT_SAMPLES", "reports", "GET", "/samples", ("format", "max-results")),
    ("REPORT_RUNS", "reports", "GET", "/runs", ("format", "max-results")),
    ("REPORT_EXPERIMENTS", "reports", "GET", "/experiments", ("format", "max-results")),
    ("REPORT_ANALYSES", "reports", "GET", "/analyses", ("format", "max-results")),
    ("REPORT_RUN_PROCESS", "reports", "GET", "/run-process", ("format", "max-results", "process-status")),
    ("REPORT_RUN_FILES", "reports", "GET", "/run-files", ("format", "max-results")),
    ("REPORT_PROJECTS_XML", "reports", "GET", "/projects/xml/{ids}", ()),
    ("REPORT_SAMPLES_XML", "reports", "GET", "/samples/xml/{ids}", ()),
    ("REPORT_RUNS_XML", "reports", "GET", "/runs/xml/{ids}", ()),
    ("REPORT_EXPERIMENTS_XML", "reports", "GET", "/experiments/xml/{ids}", ()),
    ("REPORT_ANALYSES_XML", "reports", "GET", "/analyses/xml/{ids}", ()),
)

#: Children of the receipt's ``RECEIPT`` element that carry no accession.
RECEIPT_NON_ENTITY_TAGS: Final = frozenset({"MESSAGES", "ACTIONS"})

#: Handwritten names ``models/__init__.py`` re-exports, so a caller's
#: ``from ena_api.models import …`` keeps working for every name it had.
RE_EXPORTED: Final = ("AccessionRecord", "SubmissionReceipt")


# --------------------------------------------------------------------------- IO


def _get(url: str, **kwargs: Any) -> httpx.Response:
    response = httpx.get(url, timeout=TIMEOUT, follow_redirects=True, **kwargs)
    response.raise_for_status()
    return response


def _write(path: Path, content: str | bytes, *, dry_run: bool) -> None:
    """Write ``content``, announcing it; a no-op under ``--dry-run``."""
    log.info(
        "%s %s", "would write" if dry_run else "writing", path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    )
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


# --------------------------------------------------------------- code writing


def snake(name: str) -> str:
    """Normalise an ENA name to ``snake_case``.

    >>> snake("experimentAccession"), snake("run-process"), snake("id")
    ('experiment_accession', 'run_process', 'id')
    """
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name.replace("-", "_")).lower()


def py_type(ena_type: str) -> tuple[str, str]:
    """Snapshot type -> ``(python type, default literal)``, unknown types as text.

    >>> py_type("text"), py_type("numeric"), py_type("colour")
    (('str', '""'), ('float', '0.0'), ('str', '""'))
    """
    return ENA_TYPE_MAP.get(ena_type, ENA_TYPE_MAP["text"])


def load_spec(api: str) -> dict[str, Any]:
    """The committed OpenAPI snapshot for ``api``."""
    spec: dict[str, Any] = json.loads((SNAPSHOTS / api / "openapi.json").read_text(encoding="utf-8"))
    return spec


def docstring(text: str) -> str:
    return f'"""{text}"""'


def render_report_module(entity: str, fields: list[dict[str, str]]) -> str:
    """The source of one ``models/reports/<entity>.py``."""
    segment = REPORT_ENTITIES[entity]
    columns = {field["columnId"]: field["type"] for field in fields}

    lines = [
        ENUM_HEADER,
        docstring(f"The ``/report/{entity}`` row model, generated from its field snapshot."),
        "",
        "from __future__ import annotations",
        "",
        "from enum import Enum",
        "from typing import ClassVar",
        "",
        "from pydantic import BaseModel, ConfigDict",
        "",
        "",
        f"class {segment}ReportFields(str, Enum):",
        f'    """The raw field names ENA serves in a ``/report/{entity}`` row."""',
        "",
    ]
    for column in fields:
        comment = f"  # {column['description']}" if column["description"] else ""
        lines.append(f'    {snake(column["columnId"]).upper()} = "{column["columnId"]}"{comment}')

    lines += [
        "",
        "",
        f"class {segment}Report(BaseModel):",
        f'    """A record from ``/report/{entity}``."""',
        "",
        '    model_config = ConfigDict(extra="allow", populate_by_name=True)',
        "",
        "    #: Normalised field name -> the raw keys that may carry it.",
        "    ALIASES: ClassVar[dict[str, tuple[str, ...]]] = {",
    ]
    for field in REPORT_MODEL_FIELDS[entity]:
        aliases = REPORT_FIELD_ALIASES[field]
        lines.append(f'        "{field}": {aliases!r},')
    lines += ["    }", ""]

    for field in REPORT_MODEL_FIELDS[entity]:
        matched = [key for key in REPORT_FIELD_ALIASES[field] if key in columns]
        if not matched:
            log.warning("%s: no snapshot field feeds %s.%s", entity, segment, field)
        kind, default = py_type(columns[matched[0]]) if matched else ENA_TYPE_MAP["text"]
        lines.append(f"    {field}: {kind} = {FIELD_DEFAULTS.get(field, default)}")

    return "\n".join(lines) + "\n"


def render_reports_init(entities: list[str]) -> str:
    """The source of ``models/reports/__init__.py``."""
    lines = [HEADER, docstring("Generated report row models, one module per Reports API entity."), ""]
    names: list[str] = []
    for entity in entities:
        segment = REPORT_ENTITIES[entity]
        names += [f"{segment}Report", f"{segment}ReportFields"]
        lines.append(f"from .{snake(entity)} import {segment}Report, {segment}ReportFields")
    lines += ["", f"__all__ = {sorted(names)!r}"]
    return "\n".join(lines) + "\n"


def render_endpoints() -> str:
    """The source of ``models/endpoints.py``, checked against the snapshots.

    Raises:
        ValueError: An allow-listed operation, or a parameter a proxy passes,
            is missing from its snapshot — the drift alarm.
    """
    specs = {api: load_spec(api) for api in API_DOCS}
    lines = [
        HEADER,
        docstring("The ENA operations this client calls, as taken from ENA's own definitions."),
        "",
        "from __future__ import annotations",
        "",
        "from typing import Final, NamedTuple",
        "",
        "",
        "class Endpoint(NamedTuple):",
        '    """One ENA operation: its method, path template and query parameters."""',
        "",
        "    method: str",
        "    path: str",
        "    params: tuple[str, ...]",
        "",
    ]
    for name, api, method, path, required in OPERATIONS:
        operation = specs[api].get("paths", {}).get(path, {}).get(method.lower())
        if operation is None:
            raise ValueError(f"{api}: {method} {path} is not in the snapshot — ENA moved or removed it")
        params = sorted(p["name"] for p in operation.get("parameters", []) if p.get("in") == "query" and "name" in p)
        missing = sorted(set(required) - set(params))
        if missing:
            raise ValueError(f"{api}: {method} {path} no longer takes {', '.join(missing)}")
        lines.append(f"\n{name}: Final = Endpoint({method!r}, {path!r}, {tuple(params)!r})")

    for label, suffix in (("REPORT_LIST", ""), ("REPORT_XML", "_XML")):
        entries = [
            f'    "{entity}": REPORT_{snake(entity).upper()}{suffix},'
            for entity in REPORT_ENTITIES
            if f"REPORT_{snake(entity).upper()}{suffix}" in {op[0] for op in OPERATIONS}
        ]
        lines += ["", "", f"{label}: Final[dict[str, Endpoint]] = {{", *entries, "}"]
    return "\n".join(lines) + "\n"


def render_webin() -> str:
    """The source of ``models/webin.py``: the async-queue submission job."""
    schema = load_spec("webin")["components"]["schemas"]["EntityModelWebinSubmission"]
    lines = [
        HEADER,
        docstring("The Webin Submission API's own response models."),
        "",
        "from __future__ import annotations",
        "",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        "",
        "class SubmissionJob(BaseModel):",
        '    """The queued submission ``POST /submit/queue`` answers with."""',
        "",
        '    model_config = ConfigDict(extra="allow", populate_by_name=True)',
        "",
    ]
    # ``links`` is HATEOAS navigation; this client builds its own URLs.
    for name, prop in sorted(schema.get("properties", {}).items()):
        if name == "links":
            continue
        kind, default = py_type(
            {"string": "text", "integer": "numeric", "boolean": "boolean"}.get(prop.get("type", ""), "text")
        )
        lines.append(f"    {snake(name)}: {kind} = Field({default}, alias={name!r})")
    return "\n".join(lines) + "\n"


def receipt_entity_tags(xsd: str) -> tuple[str, ...]:
    """The receipt's accession-carrying child tags, in document order.

    >>> receipt_entity_tags('<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
    ...     '<xs:element name="RECEIPT"><xs:complexType><xs:sequence>'
    ...     '<xs:element name="DATASET"/><xs:element name="MESSAGES"/>'
    ...     '</xs:sequence></xs:complexType></xs:element></xs:schema>')
    ('DATASET',)
    """
    ns = {"xs": "http://www.w3.org/2001/XMLSchema"}
    receipt = ET.fromstring(xsd).find('.//xs:element[@name="RECEIPT"]/xs:complexType/xs:sequence', ns)
    if receipt is None:
        raise ValueError("no RECEIPT element in the receipt XSD")
    # Direct children only: MESSAGES' own ERROR/INFO elements are not entities.
    tags = (child.get("name", "") for child in receipt.iterfind("xs:element", ns))
    return tuple(tag for tag in tags if tag and tag not in RECEIPT_NON_ENTITY_TAGS)


def render_init(entities: list[str], xml_entities: tuple[str, ...], tags: tuple[str, ...]) -> str:
    """The source of ``models/__init__.py``: the lookup tables.

    It also re-exports the handwritten receipt models, so ``ena_api.models.X``
    keeps working for every name it had before the split (CODEGEN_PLAN.md §0.4).
    """
    models = [f"{REPORT_ENTITIES[entity]}Report" for entity in entities]
    lines = [
        ENUM_HEADER,
        docstring("Generated lookup tables and models — the handwritten proxies' vocabulary."),
        "",
        "from __future__ import annotations",
        "",
        "from enum import Enum",
        "from typing import Final",
        "",
        "from pydantic import BaseModel",
        "",
        "from ..types import AccessionRecord, SubmissionReceipt",
        f"from .reports import {', '.join(sorted(models))}",
        "",
        "",
        "class ReportEntity(str, Enum):",
        '    """The Reports API entities this client lists."""',
        "",
        *(f'    {snake(entity).upper()} = "{entity}"' for entity in entities),
        "",
        "",
        "REPORT_MODELS: Final[dict[ReportEntity, type[BaseModel]]] = {",
        *(f"    ReportEntity.{snake(entity).upper()}: {REPORT_ENTITIES[entity]}Report," for entity in entities),
        "}",
        "",
        "#: Entities whose submitted XML the Reports API serves at ``/{entity}/xml/…``.",
        f"XML_ENTITIES: Final = {xml_entities!r}",
        "",
        "#: Receipt child tags that may carry accession info.",
        f"RECEIPT_ENTITY_TAGS: Final = {tags!r}",
        "",
        f"__all__ = {sorted([*models, *RE_EXPORTED, 'REPORT_MODELS', 'RECEIPT_ENTITY_TAGS', 'ReportEntity', 'XML_ENTITIES'])!r}",
    ]
    return "\n".join(lines) + "\n"


def run_ruff(paths: list[Path]) -> None:
    """Fix and format the generated files, so they match the handwritten ones."""
    for command in (["ruff", "check", "--fix", "--quiet"], ["ruff", "format", "--quiet"]):
        subprocess.run([*command, *(str(p) for p in paths)], check=True)


def generate(*, dry_run: bool, entities: list[str]) -> None:
    """Write every generated module from the committed snapshots."""
    reports_spec = load_spec("reports")
    xml_entities = tuple(e for e in entities if f"/{e}/xml/{{ids}}" in reports_spec.get("paths", {}))
    tags = receipt_entity_tags((SNAPSHOTS / "webin" / "SRA.receipt.xsd").read_text(encoding="utf-8"))

    written = [
        (OUTPUT / "endpoints.py", render_endpoints()),
        (OUTPUT / "webin.py", render_webin()),
        (OUTPUT / "reports" / "__init__.py", render_reports_init(entities)),
        (OUTPUT / "__init__.py", render_init(entities, xml_entities, tags)),
    ]
    written += [
        (OUTPUT / "reports" / f"{snake(entity)}.py", render_report_module(entity, load_fields(entity)))
        for entity in entities
    ]
    for path, text in written:
        _write(path, text, dry_run=dry_run)
    if not dry_run:
        run_ruff([path for path, _ in written])


# ------------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="report the writes without making them")
    parser.add_argument("--skip-fetch", action="store_true", help="use the committed snapshots, contact nothing")
    parser.add_argument("--ignore-snapshots", action="store_true", help="rewrite snapshots from scratch")
    parser.add_argument("--skip-generate", action="store_true", help="update the snapshots, write no code")
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
    entities = [e for e in args.entities.split(",") if e]
    for entity in entities:
        fetch_report_fields(entity, **flags)

    if not args.skip_generate:
        generate(dry_run=args.dry_run, entities=entities)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
