"""Pydantic models for ENA Webin API responses.

Receipts returned by the Submission API and records returned by the Reports
API are parsed into the typed models defined here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_ALLOW_EXTRA = ConfigDict(extra="allow", populate_by_name=True)


class AccessionRecord(BaseModel):
    """A single accession returned in a submission receipt.

    Attributes:
        entity_type: The XML tag from the receipt that produced this record
            (e.g. ``"PROJECT"``, ``"SAMPLE"``, ``"SUBMISSION"``).  Use this to
            distinguish data-object accessions from the submission-envelope
            accession (``entity_type == "SUBMISSION"``).

    Example:
        >>> rec = AccessionRecord(alias="s1", accession="ERS1", status="PRIVATE", entity_type="SAMPLE")
        >>> rec.accession
        'ERS1'
        >>> rec.external_accession
        ''
        >>> rec.entity_type
        'SAMPLE'
    """

    model_config = _ALLOW_EXTRA

    alias: str = ""
    accession: str = ""
    status: str = ""
    hold_until_date: str = Field("", alias="holdUntilDate")
    external_accession: str = ""
    external_type: str = ""
    entity_type: str = ""


class SubmissionReceipt(BaseModel):
    """Parsed ENA submission receipt.

    Attributes:
        success: True iff the receipt root carried ``success="true"``.
        accessions: One entry per ``<SAMPLE>``/``<PROJECT>``/``<STUDY>``/etc.
        messages: ``INFO`` messages from the receipt's ``<MESSAGES>`` block.
        warnings: ``WARNING`` messages from the receipt's ``<MESSAGES>`` block.
        errors: ``ERROR`` messages from the receipt's ``<MESSAGES>`` block.

    Example:
        >>> r = SubmissionReceipt(success=True, accessions=[], messages=[], errors=[])
        >>> r.success
        True
    """

    success: bool = False
    accessions: list[AccessionRecord] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class _BaseReport(BaseModel):
    """Common fields shared by Reports API entities."""

    model_config = _ALLOW_EXTRA

    alias: str = ""
    accession: str = ""
    secondary_accession: str = ""
    status: str = "UNKNOWN"


class StudyReport(_BaseReport):
    """A project/study record from ``/report/projects``."""

    title: str = ""


class SampleReport(_BaseReport):
    """A sample record from ``/report/samples``."""

    title: str = ""


class RunReport(_BaseReport):
    """A run record from ``/report/runs``."""

    experiment_accession: str = ""
    study_accession: str = ""
    sample_accession: str = ""


class ExperimentReport(_BaseReport):
    """An experiment record from ``/report/experiments``."""

    title: str = ""
    study_accession: str = ""
    sample_accession: str = ""


class AnalysisReport(_BaseReport):
    """An analysis record from ``/report/analyses``."""

    title: str = ""
    study_accession: str = ""


class FileReport(BaseModel):
    """A submitted-file record from ``/report/files``."""

    model_config = _ALLOW_EXTRA

    accession: str = ""
    run_accession: str = ""
    filename: str = ""
    checksum: str = ""
    checksum_method: str = ""
