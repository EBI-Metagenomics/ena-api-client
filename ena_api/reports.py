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
    "experiment_accession": ("experimentAccession", "experimentId"),
    "study_accession": ("studyAccession", "studyId"),
    "sample_accession": ("sampleAccession", "sampleId"),
    "run_accession": ("runAccession", "runId"),
    "filename": ("filename", "fileName", "name"),
    "checksum": ("checksum", "md5"),
    "checksum_method": ("checksumMethod", "checksum_method"),
}

T = TypeVar("T", bound=BaseModel)


def _coerce(record: dict[str, Any], model_cls: type[T]) -> T:
    """Build a model instance from a flat report dict, trying common key aliases.

    Any raw key that doesn't map to a known field is passed through unchanged
    (relies on the model's ``extra="allow"`` config to keep it in
    ``model_dump()``), so a Reports API field name this alias table doesn't
    yet anticipate is still visible to callers instead of silently dropped.
    """
    field_names = set(model_cls.model_fields.keys())
    # Keys reserved for other typed fields this model declares (e.g. an
    # ExperimentReport row's "studyAccession" foreign key) — the generic
    # "accession" field must not steal one of these just because it appears
    # earlier in its own alias tuple than this record's own entity-typed key
    # (e.g. "experimentAccession").
    reserved_keys: set[str] = set()
    for field in field_names:
        if field != "accession":
            reserved_keys.update(_REPORT_FIELD_ALIASES.get(field, ()))

    out: dict[str, Any] = {}
    consumed_keys: set[str] = set()
    for field in field_names:
        candidates = _REPORT_FIELD_ALIASES.get(field, (field,))
        if field == "accession":
            candidates = tuple(k for k in candidates if k not in reserved_keys)
        for key in candidates:
            if key in record and record[key] not in (None, ""):
                out[field] = record[key]
                consumed_keys.add(key)
                break
    for key, value in record.items():
        if key not in consumed_keys and key not in out:
            out[key] = value
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
        """List runs owned by the Webin account.

        The Reports API's ``/report/runs`` rows often carry only
        ``experiment_accession``, leaving ``study_accession``/``sample_accession``
        blank — those live on the run's experiment instead. This method joins
        against ``list_experiments()`` and fills them in whenever the run's own
        report didn't already supply them, so callers always get full lineage.
        """
        runs = [_coerce(r, RunReport) for r in self._fetch("runs", max_results)]
        if not runs:
            return runs
        experiments_by_accession = {
            exp.accession: exp for exp in self.list_experiments(max_results) if exp.accession
        }
        for run in runs:
            experiment = experiments_by_accession.get(run.experiment_accession)
            if experiment is None:
                continue
            if not run.study_accession:
                run.study_accession = experiment.study_accession
            if not run.sample_accession:
                run.sample_accession = experiment.sample_accession
        return runs

    def list_experiments(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[ExperimentReport]:
        """List experiments owned by the Webin account."""
        return [_coerce(r, ExperimentReport) for r in self._fetch("experiments", max_results)]

    def list_analyses(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[AnalysisReport]:
        """List analyses owned by the Webin account."""
        return [_coerce(r, AnalysisReport) for r in self._fetch("analyses", max_results)]

    def list_files(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[FileReport]:
        """List files submitted under the Webin account."""
        return [_coerce(r, FileReport) for r in self._fetch("files", max_results)]

    def find_runs_by_experiment_alias(
        self, aliases: set[str], *, max_results: int = _DEFAULT_MAX_RESULTS
    ) -> dict[str, dict[str, str]]:
        """Find existing runs by their experiment's alias.

        A reads submission registers an experiment (carrying the alias the
        caller controls) plus a run. To support idempotent/resumable
        submission — "does a run for alias X already exist?" — this looks up
        each alias among the account's experiments and maps it to both
        accessions. Returns ``{alias: {"experiment_accession": ...,
        "run_accession": ...}}`` for the aliases that exist; aliases with no
        matching experiment are omitted. Mirrors the alias-matching concept
        ``ena_common.find_duplicates_by_alias_title`` uses for studies/samples,
        generalised to the two-hop experiment→run relationship.
        """
        if not aliases:
            return {}
        experiments = self.list_experiments(max_results)
        # Raw (unenriched) runs are enough here — only experiment_accession and
        # accession are needed, both already present without the list_runs()
        # study/sample join, which would just re-fetch list_experiments again.
        runs = [_coerce(r, RunReport) for r in self._fetch("runs", max_results)]

        runs_by_experiment: dict[str, str] = {}
        for run in runs:
            if run.experiment_accession and run.accession and run.experiment_accession not in runs_by_experiment:
                runs_by_experiment[run.experiment_accession] = run.accession

        found: dict[str, dict[str, str]] = {}
        for exp in experiments:
            if exp.alias in aliases and exp.accession:
                found[exp.alias] = {
                    "experiment_accession": exp.accession,
                    "run_accession": runs_by_experiment.get(exp.accession, ""),
                }
        return found
