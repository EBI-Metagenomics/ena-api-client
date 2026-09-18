"""Unit tests for the model generator.

No network: every test builds tiny snapshots under ``tmp_path`` and points the
generator at them.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]

RECEIPT_XSD = """<?xml version="1.0"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="RECEIPT">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="SAMPLE" type="ID"/>
        <xs:element name="DATASET" type="ID"/>
        <xs:element name="MESSAGES">
          <xs:complexType><xs:sequence><xs:element name="ERROR" type="xs:string"/></xs:sequence></xs:complexType>
        </xs:element>
        <xs:element name="ACTIONS"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

RUN_FIELDS = [
    {"columnId": "id", "description": "", "type": "text"},
    {"columnId": "releaseStatus", "description": "ENA's release state", "type": "text"},
    {"columnId": "runAlias", "description": "", "type": "text"},
    {"columnId": "studyAccession", "description": "", "type": "text"},
]


def _spec(paths: dict[str, Any], schemas: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"paths": paths, "components": {"schemas": schemas or {}}}


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    """The generator, imported from ``scripts/`` (which is not a package)."""
    spec = importlib.util.spec_from_file_location("generate_models", ROOT / "scripts" / "generate_models.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def snapshots(gen: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A minimal snapshot tree, just enough for one run of ``generate()``."""
    (tmp_path / "webin").mkdir()
    (tmp_path / "webin" / "SRA.receipt.xsd").write_text(RECEIPT_XSD)
    submission = {"properties": {"links": {"type": "array"}, "submissionId": {"type": "string"}}}
    (tmp_path / "webin" / "openapi.json").write_text(
        json.dumps(_spec({"/submit": {"post": {}}}, {"EntityModelWebinSubmission": submission}))
    )
    (tmp_path / "browser").mkdir()
    (tmp_path / "browser" / "openapi.json").write_text(json.dumps(_spec({"/xml/{accession}": {"get": {}}})))
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "openapi.json").write_text(
        json.dumps(
            _spec(
                {
                    "/runs": {"get": {"parameters": [{"name": "format", "in": "query"}]}},
                    "/runs/xml/{ids}": {"get": {}},
                }
            )
        )
    )
    (tmp_path / "reports" / "runs").mkdir()
    (tmp_path / "reports" / "runs" / "fields.json").write_text(json.dumps(RUN_FIELDS))

    monkeypatch.setattr(gen, "SNAPSHOTS", tmp_path)
    monkeypatch.setattr(
        gen,
        "OPERATIONS",
        (
            ("SUBMIT", "webin", "POST", "/submit", ()),
            ("BROWSER_XML", "browser", "GET", "/xml/{accession}", ()),
            ("REPORT_RUNS", "reports", "GET", "/runs", ("format",)),
            ("REPORT_RUNS_XML", "reports", "GET", "/runs/xml/{ids}", ()),
        ),
    )
    monkeypatch.setattr(gen, "REPORT_ENTITIES", {"runs": "Run"})
    return tmp_path


def test_report_model_source(gen: ModuleType, snapshots: Path) -> None:
    source = gen.render_report_module("runs", RUN_FIELDS)

    assert source.startswith("# AUTO-GENERATED")
    assert "class RunReportFields(str, Enum):" in source
    assert '    RELEASE_STATUS = "releaseStatus"  # ENA\'s release state' in source
    assert "class RunReport(BaseModel):" in source
    assert 'model_config = ConfigDict(extra="allow", populate_by_name=True)' in source
    # Declared fields are the curated set, and every alias survives — a raw key
    # the snapshot has never seen must still be coerced at runtime.
    assert '"accession": (' in source
    assert '    accession: str = ""' in source
    assert '    status: str = "UNKNOWN"' in source
    # "studyAccession" is this row's own accession here, not a foreign key.
    assert "study_accession" not in source.split("ALIASES")[0]


def test_generate_writes_importable_modules(
    gen: ModuleType, snapshots: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "_generated"
    monkeypatch.setattr(gen, "OUTPUT", out)
    gen.generate(dry_run=False, entities=["runs"])

    written = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.py"))
    assert written == ["__init__.py", "endpoints.py", "reports/__init__.py", "reports/runs.py", "webin.py"]
    for path in out.rglob("*.py"):
        compile(path.read_text(), str(path), "exec")

    index = (out / "__init__.py").read_text()
    assert 'RUNS = "runs"' in index
    assert "ReportEntity.RUNS: RunReport" in index
    assert 'XML_ENTITIES: Final = ("runs",)' in index
    assert 'RECEIPT_ENTITY_TAGS: Final = ("SAMPLE", "DATASET")' in index
    # ``links`` is HATEOAS navigation, not part of the job identity.
    assert "links" not in (out / "webin.py").read_text()


def test_endpoints_record_the_snapshot_params(gen: ModuleType, snapshots: Path) -> None:
    source = gen.render_endpoints()

    assert "REPORT_RUNS: Final = Endpoint('GET', '/runs', ('format',))" in source
    assert '"runs": REPORT_RUNS,' in source
    assert '"runs": REPORT_RUNS_XML,' in source


def test_missing_operation_fails_generation(gen: ModuleType, snapshots: Path) -> None:
    spec = json.loads((snapshots / "reports" / "openapi.json").read_text())
    del spec["paths"]["/runs"]
    (snapshots / "reports" / "openapi.json").write_text(json.dumps(spec))

    with pytest.raises(ValueError, match="GET /runs is not in the snapshot"):
        gen.render_endpoints()


def test_missing_query_param_fails_generation(gen: ModuleType, snapshots: Path) -> None:
    spec = json.loads((snapshots / "reports" / "openapi.json").read_text())
    spec["paths"]["/runs"]["get"]["parameters"] = []
    (snapshots / "reports" / "openapi.json").write_text(json.dumps(spec))

    with pytest.raises(ValueError, match="no longer takes format"):
        gen.render_endpoints()


def test_fields_snapshot_round_trip(gen: ModuleType, snapshots: Path) -> None:
    """A snapshot reloads unchanged, and a newly seen key is added, not replaced."""
    assert gen.load_fields("runs") == RUN_FIELDS
    merged = gen.merge_fields(RUN_FIELDS, {"runAccession": "text", "releaseStatus": "numeric"})
    assert [f["columnId"] for f in merged] == ["id", "releaseStatus", "runAccession", "runAlias", "studyAccession"]
    assert merged[1]["type"] == "text"
