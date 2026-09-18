"""Webin Reports API wrappers.

Each list method targets ``GET /ena/submit/report/{entity}`` and returns the
records currently registered under the authenticated Webin account, including
both private (held) and public (released) entries.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

import httpx

# Re-exported from here for one release: mimicc's tests import
# ``ena_api.reports._coerce``.  Drop the re-export in the next minor version.
from ._processing import _coerce
from .browser import is_accession
from .exceptions import ENAAuthError, ENAInvalidAccessionError, ENANotFoundError
from .models import (
    XML_ENTITIES,
    AnalysisReport,
    ExperimentReport,
    FileReport,
    RunProcessReport,
    RunReport,
    SampleReport,
    StudyReport,
)
from .models.endpoints import REPORT_LIST, REPORT_XML

_DEFAULT_MAX_RESULTS: Final = 5000


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

    def _fetch(self, entity: str, max_results: int, **extra: Any) -> list[dict[str, Any]]:
        """Issue ``GET /report/{entity}`` and return the unwrapped report dicts.

        Returns ``[]`` on 404 (no records yet); raises ``ENAAuthError`` on
        401/403; raises ``httpx.HTTPStatusError`` on other 4xx/5xx.
        """
        url = f"{self._base_url}{REPORT_LIST[entity].path}"
        params: dict[str, Any] = {"format": "json", "max-results": max_results, **extra}
        response = self._http.get(url, params=params)

        if response.status_code == 404:
            return []
        if response.status_code in (401, 403):
            raise ENAAuthError(f"Reports API returned {response.status_code} for {url} — check Webin credentials")
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
        experiments_by_accession = {exp.accession: exp for exp in self.list_experiments(max_results) if exp.accession}
        for run in runs:
            experiment = experiments_by_accession.get(run.experiment_accession)
            if experiment is None:
                continue
            if not run.study_accession:
                run.study_accession = experiment.study_accession
            if not run.sample_accession:
                run.sample_accession = experiment.sample_accession
        return runs

    def list_run_processes(
        self, max_results: int = _DEFAULT_MAX_RESULTS, *, process_status: str | None = None
    ) -> list[RunProcessReport]:
        """List the data-file processing status of the account's runs.

        Registering a run and archiving its read files are two different
        events: ``/report/runs`` answers "does ENA have this run?", this
        answers "has ENA finished processing its files?". Optionally filtered
        server-side to one ``process_status``.
        """
        extra = {"process-status": process_status} if process_status else {}
        return [_coerce(r, RunProcessReport) for r in self._fetch("run-process", max_results, **extra)]

    def list_experiments(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[ExperimentReport]:
        """List experiments owned by the Webin account."""
        return [_coerce(r, ExperimentReport) for r in self._fetch("experiments", max_results)]

    def list_analyses(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[AnalysisReport]:
        """List analyses owned by the Webin account."""
        return [_coerce(r, AnalysisReport) for r in self._fetch("analyses", max_results)]

    def list_files(self, max_results: int = _DEFAULT_MAX_RESULTS) -> list[FileReport]:
        """List the read files submitted under the Webin account.

        ``/report/run-files``: one row per data file of a run, with its
        checksum and archive status. (``/report/files``, which this method
        used to call, is not an endpoint ENA serves — it answered 404, which
        :meth:`_fetch` turned into an empty list.)
        """
        return [_coerce(r, FileReport) for r in self._fetch("run-files", max_results)]

    def xml(self, entity: str, accessions: Sequence[str]) -> bytes:
        """The submitted XML of records this account owns, private ones included.

        The Browser API (:class:`~ena_api.browser.BrowserProxy`) serves only
        released records: it answers 404 for a private one, with or without
        credentials. The Reports API has the account's own copy — the document
        as submitted, checklist attributes and all — from the moment of
        registration, which makes it the source for anything that reads a
        record the account still holds: a listing's full field set, and the
        current XML a MODIFY has to patch.

        Scoped by ownership like every other report: an accession this account
        did not submit is simply absent from the answer, and an unauthenticated
        request is refused outright.

        Args:
            entity: ``projects``, ``samples``, ``runs``, ``experiments`` or
                ``analyses`` — the same vocabulary as the list methods. ENA
                calls a study a project here too.
            accessions: Primary accessions (``ERS…``, ``PRJEB…``, ``ERR…``).
                The secondary form is not matched — ENA answers with an empty
                document rather than an error — so pass the accession a report
                row leads with. Duplicates are collapsed, order preserved, and
                an accession ENA has nothing for is left out of the answer
                rather than failing it.

        Returns:
            The raw XML response body, or ``b""`` when ``accessions`` is empty.

        Raises:
            ENAInvalidAccessionError: ``entity`` is unknown, or an accession
                is not plausible.
            ENAAuthError: ENA returned 401/403 — check the credentials.
            ENANotFoundError: ENA returned nothing for any of these accessions.
            httpx.HTTPStatusError: Any other 4xx/5xx.
        """
        if entity not in XML_ENTITIES:
            raise ENAInvalidAccessionError(f"No record XML for {entity!r}; expected one of {', '.join(XML_ENTITIES)}")
        ids = list(dict.fromkeys(a for a in accessions if a))
        for accession in ids:
            if not is_accession(accession):
                raise ENAInvalidAccessionError(f"Not a plausible accession: {accession!r}")
        if not ids:
            return b""

        url = self._base_url + REPORT_XML[entity].path.format(ids=",".join(ids))
        response = self._http.get(url, headers={"Accept": "application/xml"})
        if response.status_code in (401, 403):
            raise ENAAuthError(f"Reports API returned {response.status_code} for {url} — check Webin credentials")
        # An accession this account does not own is not an error, it is an
        # absence — and every accession being absent leaves an empty body,
        # which ENA still calls a 200.
        if response.status_code == 404 or not response.content.strip():
            raise ENANotFoundError(f"The Webin account holds no XML for any of {len(ids)} accession(s)")
        response.raise_for_status()
        return response.content

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
