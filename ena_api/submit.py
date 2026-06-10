"""Webin Submission API wrappers.

Covers synchronous XML submission (``POST /submit``) and the asynchronous
queue used for large payloads (``POST /submit/queue`` + ``GET /submit/poll``).
"""

from __future__ import annotations

import uuid
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
                entity_type=tag,
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


def _build_action_xml(action: str, target: str, *, alias: str | None = None, **action_attrs: str) -> bytes:
    """Build a WEBIN submission XML document containing a single action.

    Args:
        action: Action element name (e.g. ``"CANCEL"``, ``"HOLD"``, ``"RELEASE"``).
        target: Accession of the object the action applies to.
        alias: Submission alias. Auto-generated from ``action`` and a UUID if not given.
        **action_attrs: Extra attributes for the action element (e.g. ``HoldUntilDate``).

    Returns:
        UTF-8 encoded XML document bytes, suitable for :meth:`SubmitProxy.xml`.

    Example:
        >>> xml_bytes = _build_action_xml("CANCEL", "ERZ1234567", alias="my-submission")
        >>> b'<SUBMISSION alias="my-submission">' in xml_bytes
        True
        >>> b'target="ERZ1234567"' in xml_bytes
        True
    """
    submission_alias = alias or f"{action.lower()}-{uuid.uuid4().hex}"
    webin = ET.Element("WEBIN")
    submission_set = ET.SubElement(webin, "SUBMISSION_SET")
    submission = ET.SubElement(submission_set, "SUBMISSION", {"alias": submission_alias})
    actions = ET.SubElement(submission, "ACTIONS")
    action_el = ET.SubElement(actions, "ACTION")
    ET.SubElement(action_el, action, {"target": target, **action_attrs})
    return ET.tostring(webin, encoding="UTF-8", xml_declaration=True)


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

    def cancel(self, target: str, *, alias: str | None = None) -> SubmissionReceipt:
        """Cancel a private object before it is released.

        Args:
            target: Accession of the object to cancel (e.g. ``"ERZ1234567"``).
            alias: Submission alias. Auto-generated if not given.

        Returns:
            Parsed :class:`SubmissionReceipt`.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        return self.xml(_build_action_xml("CANCEL", target, alias=alias))

    def suppress(self, target: str, *, alias: str | None = None) -> SubmissionReceipt:
        """Suppress a public object, hiding it from public view.

        Args:
            target: Accession of the object to suppress.
            alias: Submission alias. Auto-generated if not given.

        Returns:
            Parsed :class:`SubmissionReceipt`.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        return self.xml(_build_action_xml("SUPPRESS", target, alias=alias))

    def kill(self, target: str, *, alias: str | None = None) -> SubmissionReceipt:
        """Permanently remove an object.

        This is an admin-only action and is irreversible.

        Args:
            target: Accession of the object to kill.
            alias: Submission alias. Auto-generated if not given.

        Returns:
            Parsed :class:`SubmissionReceipt`.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        return self.xml(_build_action_xml("KILL", target, alias=alias))

    def hold(self, target: str, hold_until_date: str, *, alias: str | None = None) -> SubmissionReceipt:
        """Set or update the release date of an object.

        Args:
            target: Accession of the object.
            hold_until_date: New release date as ``YYYY-MM-DD`` (max 2 years from now).
            alias: Submission alias. Auto-generated if not given.

        Returns:
            Parsed :class:`SubmissionReceipt`.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        return self.xml(_build_action_xml("HOLD", target, alias=alias, HoldUntilDate=hold_until_date))

    def release(self, target: str, *, alias: str | None = None) -> SubmissionReceipt:
        """Make a private object public immediately.

        Args:
            target: Accession of the object to release.
            alias: Submission alias. Auto-generated if not given.

        Returns:
            Parsed :class:`SubmissionReceipt`.

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses.
        """
        return self.xml(_build_action_xml("RELEASE", target, alias=alias))
