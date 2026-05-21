"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from ena_api import WebinClient, WebinConfig


@pytest.fixture
def webin_config() -> WebinConfig:
    """A non-test-environment WebinConfig with dummy credentials."""
    return WebinConfig(webin_id="Webin-1", password="secret", test=False)


@pytest.fixture
def webin_test_config() -> WebinConfig:
    """A test-environment WebinConfig with dummy credentials."""
    return WebinConfig(webin_id="Webin-1", password="secret", test=True)


@pytest.fixture
def webin_client(webin_config: WebinConfig) -> WebinClient:
    """A WebinClient pointed at the production environment with dummy creds."""
    client = WebinClient(config=webin_config)
    yield client
    client.close()


RECEIPT_SUCCESS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<RECEIPT receiptDate="2025-01-01T00:00:00.000Z" submissionFile="sub.xml" success="true">
  <SAMPLE alias="sample-1" accession="ERS9000001" status="PRIVATE">
    <EXT_ID accession="SAMEA00000001" type="biosample"/>
  </SAMPLE>
  <SUBMISSION alias="sub-1" accession="ERA9000001"/>
  <MESSAGES>
    <INFO>This submission is a TEST.</INFO>
  </MESSAGES>
  <ACTIONS>ADD</ACTIONS>
</RECEIPT>
"""

RECEIPT_FAILURE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<RECEIPT receiptDate="2025-01-01T00:00:00.000Z" submissionFile="sub.xml" success="false">
  <MESSAGES>
    <ERROR>Sample alias 'sample-1' already exists.</ERROR>
  </MESSAGES>
</RECEIPT>
"""

PROJECTS_REPORT_JSON = [
    {
        "report": {
            "id": "ERP000001",
            "studyAlias": "study-alpha",
            "studyTitle": "Alpha study",
            "studyAccession": "ERP000001",
            "secondaryAccession": "PRJEB10001",
            "releaseStatus": "PRIVATE",
        }
    },
    {
        "report": {
            "id": "ERP000002",
            "studyAlias": "study-beta",
            "studyTitle": "Beta study",
            "studyAccession": "ERP000002",
            "releaseStatus": "PUBLIC",
        }
    },
]

SAMPLES_REPORT_JSON = [
    {
        "report": {
            "sampleAlias": "sample-1",
            "sampleTitle": "Sample one",
            "sampleAccession": "ERS9000001",
            "releaseStatus": "PRIVATE",
        }
    }
]

RUNS_REPORT_JSON = [
    {
        "report": {
            "runAlias": "run-1",
            "runAccession": "ERR9000001",
            "experimentAccession": "ERX9000001",
            "releaseStatus": "PRIVATE",
        }
    }
]
