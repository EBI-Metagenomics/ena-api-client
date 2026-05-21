"""Top-level Webin API client."""

from __future__ import annotations

from typing import Final

import httpx

from .config import WebinConfig
from .reports import ReportsProxy
from .submit import SubmitProxy

_DEFAULT_TIMEOUT: Final = 120.0


class WebinClient:
    """Authenticated ENA Webin API client.

    Wraps the Webin v2 Submission API and Webin Reports API. Credentials are
    loaded from the ``ENA_WEBIN`` / ``ENA_WEBIN_PASSWORD`` environment
    variables unless an explicit :class:`WebinConfig` is supplied.

    Args:
        config: Optional :class:`WebinConfig`. If omitted, configuration is
            read from environment variables.
        timeout: HTTP timeout in seconds (default 120).
        transport: Optional ``httpx`` transport override (used in tests).

    Example:
        >>> import os
        >>> os.environ["ENA_WEBIN"] = "Webin-12345"
        >>> os.environ["ENA_WEBIN_PASSWORD"] = "secret"
        >>> client = WebinClient()
        >>> client.config.webin_id
        'Webin-12345'
        >>> client.close()
    """

    def __init__(
        self,
        config: WebinConfig | None = None,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config or WebinConfig()  # type: ignore[call-arg]
        self._http = httpx.Client(
            auth=self.config.basic_auth(),
            timeout=timeout,
            transport=transport,
        )
        self._submit = SubmitProxy(self._http, self.config.submit_url)
        self._reports = ReportsProxy(self._http, self.config.reports_url)

    @property
    def submit(self) -> SubmitProxy:
        """Access the Webin Submission API."""
        return self._submit

    @property
    def reports(self) -> ReportsProxy:
        """Access the Webin Reports API."""
        return self._reports

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> WebinClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
