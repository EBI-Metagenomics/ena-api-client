"""Configuration for the ENA Webin API client.

Credentials and target environment are read from environment variables so
secrets never appear on the command line.
"""

from __future__ import annotations

from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROD_HOST: Final = "www.ebi.ac.uk"
TEST_HOST: Final = "wwwdev.ebi.ac.uk"


class WebinConfig(BaseSettings):
    """Webin account configuration.

    Reads ``ENA_WEBIN``, ``ENA_WEBIN_PASSWORD`` and ``ENA_WEBIN_TEST`` from the
    process environment (or from a ``.env`` file in the working directory).

    Attributes:
        webin_id: Webin account identifier (e.g. ``Webin-12345``).
        password: Webin account password, wrapped in ``SecretStr``.
        test: If ``True``, target the ENA test environment (``wwwdev.ebi.ac.uk``).

    Example:
        >>> cfg = WebinConfig(webin_id="Webin-1", password="secret")
        >>> cfg.webin_id
        'Webin-1'
        >>> cfg.submit_url
        'https://www.ebi.ac.uk/ena/submit/webin-v2'
        >>> cfg.reports_url
        'https://www.ebi.ac.uk/ena/submit/report'
        >>> cfg.browser_url
        'https://www.ebi.ac.uk/ena/browser/api'
        >>> WebinConfig(webin_id="Webin-1", password="x", test=True).submit_url
        'https://wwwdev.ebi.ac.uk/ena/submit/webin-v2'
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    webin_id: str = Field(..., validation_alias="ENA_WEBIN")
    password: SecretStr = Field(..., validation_alias="ENA_WEBIN_PASSWORD", repr=False)
    test: bool = Field(False, validation_alias="ENA_WEBIN_TEST")

    @property
    def _host(self) -> str:
        return TEST_HOST if self.test else PROD_HOST

    @property
    def browser_url(self) -> str:
        """Base URL for the ENA Browser API (record XML)."""
        return f"https://{self._host}/ena/browser/api"

    @property
    def submit_url(self) -> str:
        """Base URL for the Webin v2 Submission API."""
        return f"https://{self._host}/ena/submit/webin-v2"

    @property
    def reports_url(self) -> str:
        """Base URL for the Webin Reports API."""
        return f"https://{self._host}/ena/submit/report"

    def basic_auth(self) -> tuple[str, str]:
        """Return ``(username, password)`` for HTTP Basic auth."""
        return self.webin_id, self.password.get_secret_value()
