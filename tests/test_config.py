"""Tests for ena_api.config.WebinConfig."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from ena_api import WebinConfig


class TestWebinConfig:
    def test_explicit_values(self):
        cfg = WebinConfig(webin_id="Webin-99", password="pw", test=False)
        assert cfg.webin_id == "Webin-99"
        assert cfg.password.get_secret_value() == "pw"
        assert cfg.test is False

    def test_test_flag_switches_host(self):
        prod = WebinConfig(webin_id="Webin-1", password="x", test=False)
        test = WebinConfig(webin_id="Webin-1", password="x", test=True)
        assert "wwwdev" not in prod.submit_url
        assert "wwwdev" in test.submit_url
        assert "wwwdev" not in prod.reports_url
        assert "wwwdev" in test.reports_url

    def test_submit_url_format(self):
        cfg = WebinConfig(webin_id="Webin-1", password="x", test=False)
        assert cfg.submit_url == "https://www.ebi.ac.uk/ena/submit/webin-v2"

    def test_reports_url_format(self):
        cfg = WebinConfig(webin_id="Webin-1", password="x", test=False)
        assert cfg.reports_url == "https://www.ebi.ac.uk/ena/submit/report"

    def test_basic_auth_returns_username_password(self):
        cfg = WebinConfig(webin_id="Webin-1", password="abc")
        assert cfg.basic_auth() == ("Webin-1", "abc")

    def test_password_not_in_repr(self):
        cfg = WebinConfig(webin_id="Webin-1", password="topsecret")
        assert "topsecret" not in repr(cfg)

    def test_loads_from_env(self):
        with patch.dict(os.environ, {"ENA_WEBIN": "Webin-77", "ENA_WEBIN_PASSWORD": "envpw"}, clear=False):
            cfg = WebinConfig(_env_file=None)
            assert cfg.webin_id == "Webin-77"
            assert cfg.password.get_secret_value() == "envpw"

    def test_missing_env_raises(self):
        # Ensure env vars are absent and BaseSettings has no fallback file values.
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValidationError):
            WebinConfig(_env_file=None)
