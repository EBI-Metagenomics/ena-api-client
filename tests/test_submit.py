"""Tests for ena_api.submit."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx
import pytest

from ena_api import SubmissionReceipt, WebinClient, parse_receipt
from ena_api.submit import _build_action_xml

from .conftest import RECEIPT_FAILURE_XML, RECEIPT_SUCCESS_XML

_SUBMIT_URL = "https://www.ebi.ac.uk/ena/submit/webin-v2/submit"


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
        assert sample.entity_type == "SAMPLE"
        submission = r.accessions[1]
        assert submission.alias == "sub-1"
        assert submission.entity_type == "SUBMISSION"
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


class TestBuildActionXml:
    def test_structure_with_explicit_alias(self):
        xml_bytes = _build_action_xml("CANCEL", "ERZ1234567", alias="my-submission")
        root = ET.fromstring(xml_bytes)
        assert root.tag == "WEBIN"
        submission = root.find("SUBMISSION_SET/SUBMISSION")
        assert submission is not None
        assert submission.get("alias") == "my-submission"
        action = submission.find("ACTIONS/ACTION/CANCEL")
        assert action is not None
        assert action.get("target") == "ERZ1234567"

    def test_auto_generates_alias(self):
        xml_bytes = _build_action_xml("CANCEL", "ERZ1234567")
        root = ET.fromstring(xml_bytes)
        submission = root.find("SUBMISSION_SET/SUBMISSION")
        assert submission is not None
        alias = submission.get("alias")
        assert alias is not None
        assert alias.startswith("cancel-")

    def test_hold_includes_extra_attrs(self):
        xml_bytes = _build_action_xml("HOLD", "ERS9000001", HoldUntilDate="2026-12-31")
        root = ET.fromstring(xml_bytes)
        hold = root.find("SUBMISSION_SET/SUBMISSION/ACTIONS/ACTION/HOLD")
        assert hold is not None
        assert hold.get("target") == "ERS9000001"
        assert hold.get("HoldUntilDate") == "2026-12-31"


class TestCancel:
    def test_success(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, content=RECEIPT_SUCCESS_XML)
        receipt = webin_client.submit.cancel("ERZ1234567")
        assert receipt.success is True
        request = httpx_mock.get_requests()[0]
        action = ET.fromstring(request.content).find("SUBMISSION_SET/SUBMISSION/ACTIONS/ACTION/CANCEL")
        assert action is not None
        assert action.get("target") == "ERZ1234567"

    def test_raises_on_401(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, status_code=401)
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.submit.cancel("ERZ1234567")


class TestSuppress:
    def test_success(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, content=RECEIPT_SUCCESS_XML)
        receipt = webin_client.submit.suppress("ERS9000001")
        assert receipt.success is True
        request = httpx_mock.get_requests()[0]
        action = ET.fromstring(request.content).find("SUBMISSION_SET/SUBMISSION/ACTIONS/ACTION/SUPPRESS")
        assert action is not None
        assert action.get("target") == "ERS9000001"

    def test_raises_on_500(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.submit.suppress("ERS9000001")


class TestKill:
    def test_success(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, content=RECEIPT_SUCCESS_XML)
        receipt = webin_client.submit.kill("ERZ1234567")
        assert receipt.success is True
        request = httpx_mock.get_requests()[0]
        action = ET.fromstring(request.content).find("SUBMISSION_SET/SUBMISSION/ACTIONS/ACTION/KILL")
        assert action is not None
        assert action.get("target") == "ERZ1234567"

    def test_raises_on_401(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, status_code=401)
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.submit.kill("ERZ1234567")


class TestHold:
    def test_success(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, content=RECEIPT_SUCCESS_XML)
        receipt = webin_client.submit.hold("ERS9000001", "2026-12-31")
        assert receipt.success is True
        request = httpx_mock.get_requests()[0]
        action = ET.fromstring(request.content).find("SUBMISSION_SET/SUBMISSION/ACTIONS/ACTION/HOLD")
        assert action is not None
        assert action.get("target") == "ERS9000001"
        assert action.get("HoldUntilDate") == "2026-12-31"

    def test_raises_on_500(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, status_code=500)
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.submit.hold("ERS9000001", "2026-12-31")


class TestRelease:
    def test_success(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, content=RECEIPT_SUCCESS_XML)
        receipt = webin_client.submit.release("ERS9000001")
        assert receipt.success is True
        request = httpx_mock.get_requests()[0]
        action = ET.fromstring(request.content).find("SUBMISSION_SET/SUBMISSION/ACTIONS/ACTION/RELEASE")
        assert action is not None
        assert action.get("target") == "ERS9000001"

    def test_raises_on_401(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="POST", url=_SUBMIT_URL, status_code=401)
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.submit.release("ERS9000001")
