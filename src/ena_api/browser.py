"""ENA Browser API wrappers.

The Browser API (``/ena/browser/api``) is ENA's read side: it serves the
*current* XML of a registered object. Webin Basic auth is what makes a
**private** (held) record readable — without it only released data is served.

The one thing this exists for is a correct MODIFY: an ENA MODIFY replaces the
whole object, so the only safe way to change one field is to fetch the object's
current XML, patch it, and send it back (see
``ena_submission_toolkit.records.modify_records``).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

import httpx

from .exceptions import ENAAuthError, ENAInvalidAccessionError, ENANotFoundError
from .models.endpoints import BROWSER_XML

#: Deliberately strict: the accession goes straight into a URL path.
_ACCESSION_RE: Final = re.compile(r"^[A-Za-z0-9._-]{3,64}$")


def is_accession(value: str | None) -> bool:
    """Whether ``value`` looks like an ENA accession.

    A cheap guard for anything that puts a caller-supplied accession into a
    URL path or an XML document.

    Example:
        >>> is_accession("ERS9000001"), is_accession("../../etc/passwd")
        (True, False)
    """
    return value is not None and _ACCESSION_RE.match(value) is not None


class BrowserProxy:
    """Read-only access to the ENA Browser API.

    Obtain via :attr:`ena_api.WebinClient.browser` — not constructed directly.
    """

    def __init__(self, http: httpx.Client, base_url: str) -> None:
        self._http = http
        self._base_url = base_url

    def xml(self, accession: str) -> bytes:
        """Fetch a record's current XML document.

        Args:
            accession: The record's accession, e.g. ``ERS9000001``.

        Returns:
            The raw XML response body.

        Raises:
            ENAInvalidAccessionError: Not a plausible accession.
            ENAAuthError: ENA returned 401/403 — check the credentials.
            ENANotFoundError: ENA holds no XML for it (404 or empty).
            httpx.HTTPStatusError: Any other 4xx/5xx.

        Example:
            >>> BrowserProxy(httpx.Client(), "https://x/api").xml("../../etc/passwd")
            Traceback (most recent call last):
            ena_api.exceptions.ENAInvalidAccessionError: Not a plausible accession: '../../etc/passwd'
        """
        if not is_accession(accession):
            raise ENAInvalidAccessionError(f"Not a plausible accession: {accession!r}")
        return self._get_xml([accession], accession)

    def xml_many(self, accessions: Sequence[str]) -> bytes:
        """Fetch several records' current XML in a single request.

        The Browser API accepts a comma-separated list of accessions and
        answers with one document containing every record it found, so a
        caller needing the current state of a page of records pays for one
        request rather than one per record. Records ENA does not hold are
        simply absent from the document — unlike :meth:`xml`, a missing
        accession is not an error, because the others still came back.

        Args:
            accessions: The accessions to fetch. Duplicates are collapsed and
                order is preserved.

        Returns:
            The raw XML response body, or ``b""`` when ``accessions`` is empty.

        Raises:
            ENAInvalidAccessionError: One of them is not a plausible accession.
            ENAAuthError: ENA returned 401/403 — check the credentials.
            ENANotFoundError: ENA holds none of these accessions (404 or empty).
            httpx.HTTPStatusError: Any other 4xx/5xx.
        """
        ids = list(dict.fromkeys(a for a in accessions if a))
        for accession in ids:
            if not is_accession(accession):
                raise ENAInvalidAccessionError(f"Not a plausible accession: {accession!r}")
        if not ids:
            return b""
        return self._get_xml(ids, f"any of {len(ids)} accession(s)")

    def _get_xml(self, ids: Sequence[str], label: str) -> bytes:
        url = self._base_url + BROWSER_XML.path.format(accession=",".join(ids))
        response = self._http.get(url, headers={"Accept": "application/xml"})
        if response.status_code in (401, 403):
            raise ENAAuthError(f"Not authorised to read {label} — check the Webin credentials")
        if response.status_code == 404 or not response.content.strip():
            raise ENANotFoundError(f"ENA holds no XML for {label}")
        response.raise_for_status()
        return response.content
