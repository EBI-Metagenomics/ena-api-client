"""Handwritten models that aren't derived from an ENA definition.

The receipt's shape is only partly in ENA's XSD — ``entity_type`` is this
client's own, and real receipts carry a ``WARNING`` the XSD never mentions —
so these stay handwritten. Report row models are generated instead, from the
field snapshots (see ``scripts/README.md``).
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
