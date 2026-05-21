"""Webin Reports API wrappers.

Each list method targets ``GET /ena/submit/report/{entity}`` and returns the
records currently registered under the authenticated Webin account, including
both private (held) and public (released) entries.
"""

from __future__ import annotations

from typing import Any, Final, TypeVar

import httpx
from pydantic import BaseModel

from .models import (
    AnalysisReport,
    ExperimentReport,
    FileReport,
    RunReport,
    SampleReport,
    StudyReport,
)

_DEFAULT_MAX_RESULTS: Final = 5000

_REPORT_FIELD_ALIASES: Final[dict[str, tuple[str, ...]]] = {
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
    "experiment_accession": ("experimentAccession",),
    "study_accession": ("studyAccession",),
    "run_accession": ("runAccession",),
    "filename": ("filename", "fileName", "name"),
    "checksum": ("checksum", "md5"),
    "checksum_method": ("checksumMethod", "checksum_method"),
}

T = TypeVar("T", bound=BaseModel)


def _coerce(record: dict[str, Any], model_cls: type[T]) -> T:
    """Build a model instance from a flat report dict, trying common key aliases."""
    field_names = set(model_cls.model_fields.keys())
    out: dict[str, Any] = {}
    for field in field_names:
        for key in _REPORT_FIELD_ALIASES.get(field, (field,)):
            if key in record and record[key] not in (None, ""):
                out[field] = record[key]
                break
    return model_cls.model_validate(out)


class ReportsProxy:
    """Read-only access to the Webin Reports API.

    Returns records owned by the authenticated Webin account. Includes both
    private (held) and public (released) entries; filter on ``.status`` to
    distinguish them.

    Obtain via :attr:`ena_api.WebinClient.reports` — not constructed directly.
    """

    def __init__(self, http: httpx.Client, base_url: str) -> None:
        self._http = http
        self._base_url = base_url

    def _fetch(self, entity: str, max_results: int) -> list[dict[str, Any]]:
        """Issue ``GET /report/{entity}`` and return the unwrapped report dicts.

        Returns ``[]`` on 404 (no records yet); raises ``PermissionError`` on
        401/403; raises ``httpx.HTTPStatusError`` on other 4xx/5xx.
        """
        url = f"{self._base_url}/{entity}"
        params = {"format": "json", "max-results": max_results}
        response = self._http.get(url, params=params)

        if response.status_code == 404:
            return []
        if response.status_code in (401, 403):
            raise PermissionError(f"Reports API returned {response.status_code} for {url} — check Webin credentials")
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, list):
            return []
        return [entry["report"] for entry in payload if isinstance(entry, dict) and "report" in entry]

    def list_projects(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[StudyReport]:
        """List projects/studies owned by the Webin account."""
        return [_coerce(r, StudyReport) for r in self._fetch("projects", max_results)]

    def list_samples(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[SampleReport]:
        """List samples owned by the Webin account."""
        return [_coerce(r, SampleReport) for r in self._fetch("samples", max_results)]

    def list_runs(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[RunReport]:
        """List runs owned by the Webin account."""
        return [_coerce(r, RunReport) for r in self._fetch("runs", max_results)]

    def list_experiments(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[ExperimentReport]:
        """List experiments owned by the Webin account."""
        return [_coerce(r, ExperimentReport) for r in self._fetch("experiments", max_results)]

    def list_analyses(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[AnalysisReport]:
        """List analyses owned by the Webin account."""
        return [_coerce(r, AnalysisReport) for r in self._fetch("analyses", max_results)]

    def list_files(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[FileReport]:
        """List files submitted under the Webin account."""
        return [_coerce(r, FileReport) for r in self._fetch("files", max_results)]
