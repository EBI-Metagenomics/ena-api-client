"""Tests for ena_api.reports."""

from __future__ import annotations

import httpx
import pytest

from ena_api import WebinClient

from .conftest import (
    EXPERIMENTS_REPORT_JSON,
    PROJECTS_REPORT_JSON,
    RUN_PROCESS_REPORT_JSON,
    RUNS_REPORT_JSON,
    SAMPLES_REPORT_JSON,
)

_BASE = "https://www.ebi.ac.uk/ena/submit/report"


class TestListProjects:
    def test_parses_response(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/projects?format=json&max-results=5000",
            json=PROJECTS_REPORT_JSON,
        )
        projects = webin_client.reports.list_projects()
        assert len(projects) == 2
        assert projects[0].alias == "study-alpha"
        assert projects[0].accession == "ERP000001"
        assert projects[0].title == "Alpha study"
        assert projects[0].status == "PRIVATE"
        assert projects[0].secondary_accession == "PRJEB10001"
        assert projects[1].status == "PUBLIC"

    def test_empty_on_404(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/projects?format=json&max-results=5000",
            status_code=404,
        )
        assert webin_client.reports.list_projects() == []

    def test_permission_error_on_401(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/projects?format=json&max-results=5000",
            status_code=401,
        )
        with pytest.raises(PermissionError):
            webin_client.reports.list_projects()

    def test_permission_error_on_403(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/projects?format=json&max-results=5000",
            status_code=403,
        )
        with pytest.raises(PermissionError):
            webin_client.reports.list_projects()

    def test_raises_on_500(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/projects?format=json&max-results=5000",
            status_code=500,
        )
        with pytest.raises(httpx.HTTPStatusError):
            webin_client.reports.list_projects()

    def test_max_results_in_query_string(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/projects?format=json&max-results=10",
            json=[],
        )
        webin_client.reports.list_projects(max_results=10)


class TestListSamples:
    def test_parses_response(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/samples?format=json&max-results=5000",
            json=SAMPLES_REPORT_JSON,
        )
        samples = webin_client.reports.list_samples()
        assert len(samples) == 1
        assert samples[0].alias == "sample-1"
        assert samples[0].accession == "ERS9000001"
        assert samples[0].title == "Sample one"


class TestListRuns:
    def test_parses_response(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/runs?format=json&max-results=5000",
            json=RUNS_REPORT_JSON,
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/experiments?format=json&max-results=5000",
            json=[],
        )
        runs = webin_client.reports.list_runs()
        assert len(runs) == 1
        assert runs[0].accession == "ERR9000001"
        assert runs[0].experiment_accession == "ERX9000001"

    def test_enriched_with_experiment_lineage(self, httpx_mock, webin_client: WebinClient):
        """Run reports often lack study/sample accession; list_runs() should
        join against list_experiments() to fill them in."""
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/runs?format=json&max-results=5000",
            json=RUNS_REPORT_JSON,
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/experiments?format=json&max-results=5000",
            json=EXPERIMENTS_REPORT_JSON,
        )
        runs = webin_client.reports.list_runs()
        assert len(runs) == 1
        assert runs[0].experiment_accession == "ERX9000001"
        assert runs[0].study_accession == "ERP000001"
        assert runs[0].sample_accession == "ERS9000001"

    def test_no_runs_skips_experiment_fetch(self, httpx_mock, webin_client: WebinClient):
        """No runs means no possible join — avoid an unnecessary HTTP call."""
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/runs?format=json&max-results=5000",
            json=[],
        )
        assert webin_client.reports.list_runs() == []


class TestFindRunsByExperimentAlias:
    def test_matches_existing_alias(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/experiments?format=json&max-results=5000",
            json=EXPERIMENTS_REPORT_JSON,
        )
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/runs?format=json&max-results=5000",
            json=RUNS_REPORT_JSON,
        )
        found = webin_client.reports.find_runs_by_experiment_alias({"run-1", "missing-alias"})
        assert found == {"run-1": {"experiment_accession": "ERX9000001", "run_accession": "ERR9000001"}}

    def test_no_aliases_skips_http_calls(self, webin_client: WebinClient):
        assert webin_client.reports.find_runs_by_experiment_alias(set()) == {}


class TestOtherEntities:
    def test_list_experiments_empty(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/experiments?format=json&max-results=5000",
            json=[],
        )
        assert webin_client.reports.list_experiments() == []

    def test_list_analyses_empty(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/analyses?format=json&max-results=5000",
            json=[],
        )
        assert webin_client.reports.list_analyses() == []

    def test_list_files_empty(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/files?format=json&max-results=5000",
            json=[],
        )
        assert webin_client.reports.list_files() == []


class TestEntriesWithoutReport:
    def test_skips_malformed_entries(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/projects?format=json&max-results=5000",
            json=[{"not_report": {}}, {"report": {"studyAlias": "ok"}}],
        )
        projects = webin_client.reports.list_projects()
        assert len(projects) == 1
        assert projects[0].alias == "ok"


class TestListRunProcesses:
    def test_parses_processing_status(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/run-process?format=json&max-results=5000",
            json=RUN_PROCESS_REPORT_JSON,
        )
        processes = webin_client.reports.list_run_processes()
        assert [p.run_accession for p in processes] == ["ERR9000001", "ERR9000002"]
        assert processes[0].process_status == "COMPLETED"
        assert processes[0].process_date == "2026-01-02T03:04:05"
        assert processes[1].error_message == "File checksum mismatch"

    def test_status_filter_is_sent_to_ena(self, httpx_mock, webin_client: WebinClient):
        httpx_mock.add_response(
            method="GET",
            url=f"{_BASE}/run-process?format=json&max-results=5000&process-status=IN_PROGRESS",
            json=[],
        )
        assert webin_client.reports.list_run_processes(process_status="IN_PROGRESS") == []
