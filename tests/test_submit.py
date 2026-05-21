"""Tests for ena_api.submit."""

from __future__ import annotations

import httpx
import pytest

from ena_api import SubmissionReceipt, WebinClient, parse_receipt

from .conftest import RECEIPT_FAILURE_XML, RECEIPT_SUCCESS_XML


class TestParseReceipt:
    def test_success_receipt(self):
        r = parse_receipt(RECEIPT_SUCCESS_XML)
        assert r.success is True
        assert len(r.accessions) == 2  # SAMPLE + SUBMISSION
        sample = r.accessions[0]
        assert sample.alias == "sample-1"
        assert sample.accession == "ERS9000001"
        assert sample.status == "PRIVATE"
        assert sample.external_accession == "SAMEA00000001"
        assert sample.external_type == "biosample"
        assert r.messages == ["INFO: This submission is a TEST."]
        assert r.errors == []

    def test_failure_receipt(self):
        r = parse_receipt(RECEIPT_FAILURE_XML)
        assert r.success is False
        assert r.accessions == []
        assert r.messages == []
        assert r.errors == ["ERROR: Sample alias 'sample-1' already exists."]

    def test_missing_success_attribute_defaults_false(self):
        xml = b"<?xml version='1.0'?><RECEIPT/>"
        assert parse_receipt(xml).success is False

    def test_project_receipt(self):
        xml = b'<?xml version="1.0"?><RECEIPT success="true"><PROJECT alias="p1" accession="ERP1" status="PRIVATE"/></RECEIPT>'
        r = parse_receipt(xml)
        assert r.success is True
        assert r.accessions[0].accession == "ERP1"


class TestSubmitXml:
    def test_success(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="POST",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit",
            content=RECEIPT_SUCCESS_XML,
        )
        receipt = webin_client.submit.xml(b"<WEBIN/>")
        assert isinstance(receipt, SubmissionReceipt)
        assert receipt.success is True
        assert receipt.accessions[0].accession == "ERS9000001"

    def test_failure_receipt_is_parsed(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="POST",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit",
            content=RECEIPT_FAILURE_XML,
        )
        receipt = webin_client.submit.xml(b"<WEBIN/>")
        assert receipt.success is False
        assert receipt.errors

    def test_raises_on_401(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="POST",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit",
            status_code=401,
        )
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.submit.xml(b"<WEBIN/>")

    def test_raises_on_500(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="POST",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit",
            status_code=500,
        )
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.submit.xml(b"<WEBIN/>")

    def test_uses_test_url_when_configured(self, httpx_mock, webin_test_config):
        httpx_mock.add_response(
            method="POST",
            url="https://wwwdev.ebi.ac.uk/ena/submit/webin-v2/submit",
            content=RECEIPT_SUCCESS_XML,
        )
        with WebinClient(config=webin_test_config) as client:
            receipt = client.submit.xml(b"<WEBIN/>")
        assert receipt.success is True


class TestSubmitXmlAsync:
    def test_returns_text_job_id(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="POST",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit/queue",
            text="job-abc-123\n",
        )
        job_id = webin_client.submit.xml_async(b"<WEBIN/>")
        assert job_id == "job-abc-123"

    def test_parses_xml_job_id(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="POST",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit/queue",
            content=b'<?xml version="1.0"?><JOB id="job-xyz"/>',
        )
        job_id = webin_client.submit.xml_async(b"<WEBIN/>")
        assert job_id == "job-xyz"


class TestPoll:
    def test_returns_none_while_processing(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit/poll/job-1",
            status_code=202,
        )
        assert webin_client.submit.poll("job-1") is None

    def test_returns_receipt_when_done(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit/poll/job-1",
            content=RECEIPT_SUCCESS_XML,
        )
        receipt = webin_client.submit.poll("job-1")
        assert receipt is not None
        assert receipt.success is True

    def test_raises_on_4xx(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url="https://www.ebi.ac.uk/ena/submit/webin-v2/submit/poll/job-1",
            status_code=404,
        )
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.submit.poll("job-1")
