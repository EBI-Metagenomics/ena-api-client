"""Golden compatibility tests for report coercion and submission receipts.

These expected dictionaries record the public ``model_dump()`` contract before
the report models and receipt parsing move to generated code.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from ena_api.models import AnalysisReport, ExperimentReport, RunProcessReport, RunReport, SampleReport, StudyReport
from ena_api.reports import _coerce
from ena_api.submit import parse_receipt

from .conftest import (
    EXPERIMENTS_REPORT_JSON,
    PROJECTS_REPORT_JSON,
    RECEIPT_FAILURE_XML,
    RECEIPT_SUCCESS_XML,
    RECEIPT_WARNING_FAILURE_XML,
    RUN_PROCESS_REPORT_JSON,
    RUNS_REPORT_JSON,
    SAMPLES_REPORT_JSON,
)

REPORT_GOLDENS = [
    pytest.param(
        PROJECTS_REPORT_JSON[0]["report"],
        StudyReport,
        {
            "alias": "study-alpha",
            "accession": "ERP000001",
            "secondary_accession": "PRJEB10001",
            "status": "PRIVATE",
            "title": "Alpha study",
            "id": "ERP000001",
        },
        id="project-with-secondary-accession",
    ),
    pytest.param(
        PROJECTS_REPORT_JSON[1]["report"],
        StudyReport,
        {
            "alias": "study-beta",
            "accession": "ERP000002",
            "secondary_accession": "",
            "status": "PUBLIC",
            "title": "Beta study",
            "id": "ERP000002",
        },
        id="project-without-secondary-accession",
    ),
    pytest.param(
        SAMPLES_REPORT_JSON[0]["report"],
        SampleReport,
        {
            "alias": "sample-1",
            "accession": "ERS9000001",
            "secondary_accession": "",
            "status": "PRIVATE",
            "title": "Sample one",
        },
        id="sample",
    ),
    pytest.param(
        RUNS_REPORT_JSON[0]["report"],
        RunReport,
        {
            "alias": "run-1",
            "accession": "ERR9000001",
            "secondary_accession": "",
            "status": "PRIVATE",
            "experiment_accession": "ERX9000001",
            "study_accession": "",
            "sample_accession": "",
        },
        id="run",
    ),
    pytest.param(
        EXPERIMENTS_REPORT_JSON[0]["report"],
        ExperimentReport,
        {
            "alias": "run-1",
            "accession": "ERX9000001",
            "secondary_accession": "",
            "status": "PRIVATE",
            "title": "Experiment one",
            "study_accession": "ERP000001",
            "sample_accession": "ERS9000001",
        },
        id="experiment",
    ),
    pytest.param(
        RUN_PROCESS_REPORT_JSON[0]["report"],
        RunProcessReport,
        {
            "run_accession": "ERR9000001",
            "process_status": "COMPLETED",
            "process_date": "2026-01-02T03:04:05",
            "error_message": "",
        },
        id="run-process-completed",
    ),
    pytest.param(
        RUN_PROCESS_REPORT_JSON[1]["report"],
        RunProcessReport,
        {
            "run_accession": "ERR9000002",
            "process_status": "ERROR",
            "process_date": "2026-01-02T03:04:05",
            "error_message": "File checksum mismatch",
        },
        id="run-process-error",
    ),
    # Rows copied from mimicc-ena-submission-assistant's
    # tests/test_records_enrichment.py. Keep them local so this contract test
    # does not depend on that repository being checked out alongside this one.
    pytest.param(
        {"runAccession": "ERR111", "experimentAccession": "ERX111", "releaseStatus": "PRIVATE"},
        RunReport,
        {
            "alias": "",
            "accession": "ERR111",
            "secondary_accession": "",
            "status": "PRIVATE",
            "experiment_accession": "ERX111",
            "study_accession": "",
            "sample_accession": "",
        },
        id="mimicc-run-accession-keys",
    ),
    pytest.param(
        {"accession": "ERR111", "experimentId": "ERX111", "studyId": "ERP111", "sampleId": "ERS111"},
        RunReport,
        {
            "alias": "",
            "accession": "ERR111",
            "secondary_accession": "",
            "status": "UNKNOWN",
            "experiment_accession": "ERX111",
            "study_accession": "ERP111",
            "sample_accession": "ERS111",
        },
        id="mimicc-run-id-keys",
    ),
    pytest.param(
        {"accession": "ERX111", "studyAccession": "ERP111", "sampleAccession": "ERS111"},
        ExperimentReport,
        {
            "alias": "",
            "accession": "ERX111",
            "secondary_accession": "",
            "status": "UNKNOWN",
            "title": "",
            "study_accession": "ERP111",
            "sample_accession": "ERS111",
        },
        id="mimicc-experiment-accession-keys",
    ),
    pytest.param(
        {"accession": "ERR111", "totallyUnexpectedKey": "mystery-value"},
        RunReport,
        {
            "alias": "",
            "accession": "ERR111",
            "secondary_accession": "",
            "status": "UNKNOWN",
            "experiment_accession": "",
            "study_accession": "",
            "sample_accession": "",
            "totallyUnexpectedKey": "mystery-value",
        },
        id="mimicc-unrecognised-key",
    ),
    pytest.param(
        {
            "accession": "ERR111",
            "alias": "runA",
            "experiment_accession": "ERX111",
            "study_accession": "ERP111",
            "sample_accession": "ERS111",
            "status": "PRIVATE",
        },
        RunReport,
        {
            "alias": "runA",
            "accession": "ERR111",
            "secondary_accession": "",
            "status": "PRIVATE",
            "experiment_accession": "ERX111",
            "study_accession": "ERP111",
            "sample_accession": "ERS111",
        },
        id="mimicc-normalised-run-keys",
    ),
    # Field names captured from the ENA wwwdev test service on 2026-09-18.
    # Every API value is replaced with a fixed placeholder before it is stored.
    pytest.param(
        {
            "alias": "<TEST_ACCOUNT_VALUE>",
            "firstCreated": "<TEST_ACCOUNT_VALUE>",
            "firstPublic": "<TEST_ACCOUNT_VALUE>",
            "holdDate": "<TEST_ACCOUNT_VALUE>",
            "id": "<TEST_ACCOUNT_VALUE>",
            "releaseStatus": "<TEST_ACCOUNT_VALUE>",
            "secondaryId": "<TEST_ACCOUNT_VALUE>",
            "submissionAccountId": "<TEST_ACCOUNT_VALUE>",
            "title": "<TEST_ACCOUNT_VALUE>",
        },
        StudyReport,
        {
            "alias": "<TEST_ACCOUNT_VALUE>",
            "accession": "<TEST_ACCOUNT_VALUE>",
            "secondary_accession": "<TEST_ACCOUNT_VALUE>",
            "status": "<TEST_ACCOUNT_VALUE>",
            "title": "<TEST_ACCOUNT_VALUE>",
            "firstCreated": "<TEST_ACCOUNT_VALUE>",
            "firstPublic": "<TEST_ACCOUNT_VALUE>",
            "holdDate": "<TEST_ACCOUNT_VALUE>",
            "submissionAccountId": "<TEST_ACCOUNT_VALUE>",
        },
        id="wwwdev-project-sanitised",
    ),
    pytest.param(
        {
            "alias": "<TEST_ACCOUNT_VALUE>",
            "commonName": "<TEST_ACCOUNT_VALUE>",
            "firstCreated": "<TEST_ACCOUNT_VALUE>",
            "firstPublic": "<TEST_ACCOUNT_VALUE>",
            "id": "<TEST_ACCOUNT_VALUE>",
            "releaseStatus": "<TEST_ACCOUNT_VALUE>",
            "scientificName": "<TEST_ACCOUNT_VALUE>",
            "secondaryId": "<TEST_ACCOUNT_VALUE>",
            "submissionAccountId": "<TEST_ACCOUNT_VALUE>",
            "taxId": "<TEST_ACCOUNT_VALUE>",
            "title": "<TEST_ACCOUNT_VALUE>",
        },
        SampleReport,
        {
            "alias": "<TEST_ACCOUNT_VALUE>",
            "accession": "<TEST_ACCOUNT_VALUE>",
            "secondary_accession": "<TEST_ACCOUNT_VALUE>",
            "status": "<TEST_ACCOUNT_VALUE>",
            "title": "<TEST_ACCOUNT_VALUE>",
            "commonName": "<TEST_ACCOUNT_VALUE>",
            "firstCreated": "<TEST_ACCOUNT_VALUE>",
            "firstPublic": "<TEST_ACCOUNT_VALUE>",
            "scientificName": "<TEST_ACCOUNT_VALUE>",
            "submissionAccountId": "<TEST_ACCOUNT_VALUE>",
            "taxId": "<TEST_ACCOUNT_VALUE>",
        },
        id="wwwdev-sample-sanitised",
    ),
    pytest.param(
        {
            "alias": "<TEST_ACCOUNT_VALUE>",
            "analysisType": "<TEST_ACCOUNT_VALUE>",
            "analysisTypeDescription": "<TEST_ACCOUNT_VALUE>",
            "firstCreated": "<TEST_ACCOUNT_VALUE>",
            "firstPublic": "<TEST_ACCOUNT_VALUE>",
            "id": "<TEST_ACCOUNT_VALUE>",
            "projectId": "<TEST_ACCOUNT_VALUE>",
            "releaseStatus": "<TEST_ACCOUNT_VALUE>",
            "sampleId": "<TEST_ACCOUNT_VALUE>",
            "studyId": "<TEST_ACCOUNT_VALUE>",
            "submissionAccountId": "<TEST_ACCOUNT_VALUE>",
        },
        AnalysisReport,
        {
            "alias": "<TEST_ACCOUNT_VALUE>",
            "accession": "<TEST_ACCOUNT_VALUE>",
            "secondary_accession": "",
            "status": "<TEST_ACCOUNT_VALUE>",
            "title": "",
            "study_accession": "<TEST_ACCOUNT_VALUE>",
            "analysisType": "<TEST_ACCOUNT_VALUE>",
            "analysisTypeDescription": "<TEST_ACCOUNT_VALUE>",
            "firstCreated": "<TEST_ACCOUNT_VALUE>",
            "firstPublic": "<TEST_ACCOUNT_VALUE>",
            "projectId": "<TEST_ACCOUNT_VALUE>",
            "sampleId": "<TEST_ACCOUNT_VALUE>",
            "submissionAccountId": "<TEST_ACCOUNT_VALUE>",
        },
        id="wwwdev-analysis-sanitised",
    ),
]


RECEIPT_GOLDENS = [
    pytest.param(
        RECEIPT_SUCCESS_XML,
        {
            "success": True,
            "accessions": [
                {
                    "alias": "sample-1",
                    "accession": "ERS9000001",
                    "status": "PRIVATE",
                    "hold_until_date": "",
                    "external_accession": "SAMEA00000001",
                    "external_type": "biosample",
                    "entity_type": "SAMPLE",
                },
                {
                    "alias": "sub-1",
                    "accession": "ERA9000001",
                    "status": "",
                    "hold_until_date": "",
                    "external_accession": "",
                    "external_type": "",
                    "entity_type": "SUBMISSION",
                },
            ],
            "messages": ["INFO: This submission is a TEST."],
            "warnings": [],
            "errors": [],
        },
        id="success",
    ),
    pytest.param(
        RECEIPT_FAILURE_XML,
        {
            "success": False,
            "accessions": [],
            "messages": [],
            "warnings": [],
            "errors": ["ERROR: Sample alias 'sample-1' already exists."],
        },
        id="failure",
    ),
    pytest.param(
        RECEIPT_WARNING_FAILURE_XML,
        {
            "success": False,
            "accessions": [],
            "messages": [],
            "warnings": ["WARNING: Study title 'MIMICC' is not sufficiently unique."],
            "errors": [],
        },
        id="warning-only-failure",
    ),
]


@pytest.mark.parametrize(("record", "model_cls", "expected"), REPORT_GOLDENS)
def test_report_model_dumps_remain_compatible(
    record: dict[str, Any], model_cls: type[BaseModel], expected: dict[str, Any]
) -> None:
    """Preserve the report model-dump contract through code generation."""
    assert _coerce(record, model_cls).model_dump() == expected


@pytest.mark.parametrize(("xml_bytes", "expected"), RECEIPT_GOLDENS)
def test_receipt_model_dumps_remain_compatible(xml_bytes: bytes, expected: dict[str, Any]) -> None:
    """Preserve the receipt model-dump contract through code generation."""
    assert parse_receipt(xml_bytes).model_dump() == expected
