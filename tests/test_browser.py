"""Tests for ena_api.browser."""

from __future__ import annotations

import httpx
import pytest

from ena_api import WebinClient

_BASE = "https://www.ebi.ac.uk/ena/browser/api"

SAMPLE_XML = b'<?xml version="1.0"?><SAMPLE_SET><SAMPLE alias="s1"><TITLE>One</TITLE></SAMPLE></SAMPLE_SET>'


class TestXml:
    def test_returns_body(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="GET", url=f"{_BASE}/xml/ERS9000001", content=SAMPLE_XML)
        assert webin_client.browser.xml("ERS9000001") == SAMPLE_XML

    @pytest.mark.parametrize("accession", ["", "../../etc/passwd", "a", "x" * 65])
    def test_rejects_implausible_accession(self, accession: str, webin_client: WebinClient):
        with pytest.raises(ValueError, match="Not a plausible accession"):
            webin_client.browser.xml(accession)

    def test_permission_error_on_401(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="GET", url=f"{_BASE}/xml/ERS9000001", status_code=401)
        with pytest.raises(PermissionError):
            webin_client.browser.xml("ERS9000001")

    def test_lookup_error_on_404(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="GET", url=f"{_BASE}/xml/ERS9000001", status_code=404)
        with pytest.raises(LookupError):
            webin_client.browser.xml("ERS9000001")

    def test_lookup_error_on_empty_body(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="GET", url=f"{_BASE}/xml/ERS9000001", content=b"   ")
        with pytest.raises(LookupError):
            webin_client.browser.xml("ERS9000001")

    def test_raises_on_500(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(method="GET", url=f"{_BASE}/xml/ERS9000001", status_code=500, content=b"nope")
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.browser.xml("ERS9000001")

    def test_test_environment_host(self, httpx_mock, webin_test_config):
        client = WebinClient(config=webin_test_config)
        httpx_mock.add_response(
            method="GET", url="https://wwwdev.ebi.ac.uk/ena/browser/api/xml/ERS9000001", content=SAMPLE_XML
        )
        assert client.browser.xml("ERS9000001") == SAMPLE_XML
        client.close()
