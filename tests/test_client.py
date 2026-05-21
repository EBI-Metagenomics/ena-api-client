"""Tests for ena_api.client.WebinClient."""

from __future__ import annotations

from ena_api import ReportsProxy, SubmitProxy, WebinClient, WebinConfig


class TestWebinClient:
    def test_loads_from_config(self):
        cfg = WebinConfig(webin_id="Webin-1", password="x", test=False)
        with WebinClient(config=cfg) as client:
            assert client.config.webin_id == "Webin-1"

    def test_submit_proxy_attached(self):
        cfg = WebinConfig(webin_id="Webin-1", password="x")
        with WebinClient(config=cfg) as client:
            assert isinstance(client.submit, SubmitProxy)

    def test_reports_proxy_attached(self):
        cfg = WebinConfig(webin_id="Webin-1", password="x")
        with WebinClient(config=cfg) as client:
            assert isinstance(client.reports, ReportsProxy)

    def test_context_manager_closes(self):
        cfg = WebinConfig(webin_id="Webin-1", password="x")
        with WebinClient(config=cfg) as client:
            pass
        # closing again is a no-op
        client.close()
