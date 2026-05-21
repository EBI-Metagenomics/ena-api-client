"""Webin Submission API wrappers.

Covers synchronous XML submission (``POST /submit``) and the asynchronous
queue used for large payloads (``POST /submit/queue`` + ``GET /submit/poll``).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Final

import httpx

from .models import AccessionRecord, SubmissionReceipt

_HEADERS: Final = {
    "Content-Type": "application/xml",
    "Accept": "application/xml",
}

# Receipt child tags that may carry accession info.
_RECEIPT_ENTITY_TAGS: Final = (
    "SAMPLE",
    "PROJECT",
    "STUDY",
    "EXPERIMENT",
    "RUN",
    "ANALYSIS",
    "SUBMISSION",
)


def parse_receipt(xml_bytes: bytes) -> SubmissionReceipt:
    """Parse an ENA submission receipt XML document.

    Args:
        xml_bytes: Raw response body from the Submission API.

    Returns:
        SubmissionReceipt with success flag, accessions, info messages, errors.

    Example:
        >>> xml = b'<?xml version="1.0"?><RECEIPT success="true"><SAMPLE alias="s1" accession="ERS1" status="PRIVATE"/></RECEIPT>'
        >>> r = parse_receipt(xml)
        >>> r.success
        True
        >>> r.accessions[0].accession
        'ERS1'
    """
    root = ET.fromstring(xml_bytes)
    success = root.get("success", "false").lower() == "true"

    messages: list[str] = []
    errors: list[str] = []
    msgs_el = root.find("MESSAGES")
    if msgs_el is not None:
        messages = [f"INFO: {info.text}" for info in msgs_el.findall("INFO") if info.text]
        errors = [f"ERROR: {err.text}" for err in msgs_el.findall("ERROR") if err.text]

    accessions: list[AccessionRecord] = []
    for tag in _RECEIPT_ENTITY_TAGS:
        for entity in root.findall(tag):
            record = AccessionRecord(
                alias=entity.get("alias", ""),
                accession=entity.get("accession", ""),
                status=entity.get("status", ""),
                holdUntilDate=entity.get("holdUntilDate", ""),
            )
            ext = entity.find("EXT_ID")
            if ext is not None:
                record.external_accession = ext.get("accession", "")
                record.external_type = ext.get("type", "")
            accessions.append(record)

    return SubmissionReceipt(
        success=success,
        accessions=accessions,
        messages=messages,
        errors=errors,
    )


class SubmitProxy:
    """Synchronous and asynchronous XML submission to the Webin v2 API.

    Obtain via :attr:`ena_api.WebinClient.submit` — not constructed directly.
    """

    def __init__(self, http: httpx.Client, base_url: str) -> None:
        self._http = http
        self._base_url = base_url

    def xml(self, xml_bytes: bytes) -> SubmissionReceipt:
        """Submit an XML document synchronously.

        Args:
            xml_bytes: WEBIN-rooted XML payload.

        Returns:
            Parsed :class:`SubmissionReceipt`.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        url = f"{self._base_url}/submit"
        response = self._http.post(url, content=xml_bytes, headers=_HEADERS)
        response.raise_for_status()
        return parse_receipt(response.content)

    def xml_async(self, xml_bytes: bytes) -> str:
        """Submit a large XML payload (>15 MB) via the async queue.

        Returns:
            Job ID that can be passed to :meth:`poll` until a receipt is ready.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        url = f"{self._base_url}/submit/queue"
        response = self._http.post(url, content=xml_bytes, headers=_HEADERS)
        response.raise_for_status()

        # ENA returns either a plain text job ID or an XML stub containing the ID.
        text = response.text.strip()
        if text.startswith("<"):
            root = ET.fromstring(response.content)
            job_id = root.get("id") or (root.findtext("ID") or "")
            return job_id.strip()
        return text

    def poll(self, job_id: str) -> SubmissionReceipt | None:
        """Poll for an async submission's receipt.

        Args:
            job_id: Job identifier returned by :meth:`xml_async`.

        Returns:
            A :class:`SubmissionReceipt` if the job finished, or ``None`` if still processing.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses other than 202 (still processing).
        """
        url = f"{self._base_url}/submit/poll/{job_id}"
        response = self._http.get(url, headers={"Accept": "application/xml"})
        if response.status_code == 202:
            return None
        response.raise_for_status()
        return parse_receipt(response.content)
