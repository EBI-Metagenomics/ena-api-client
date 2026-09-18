"""Errors this client raises.

Each one also subclasses the built-in it replaces, so callers that catch
``PermissionError``/``LookupError``/``ValueError`` — as
``ena-submission-toolkit`` does — keep working unchanged.
"""

from __future__ import annotations


class ENAClientError(Exception):
    """Base class for every error this client raises."""


class ENAAuthError(ENAClientError, PermissionError):
    """ENA refused the credentials (401/403).

    Example:
        >>> isinstance(ENAAuthError(), PermissionError)
        True
    """


class ENANotFoundError(ENAClientError, LookupError):
    """ENA holds nothing for what was asked for (404, or an empty document)."""


class ENAInvalidAccessionError(ENAClientError, ValueError):
    """An argument is not a plausible accession, or names an unknown entity."""
