"""Typed Python client for the ENA Webin Submission and Reports APIs."""

from __future__ import annotations

from .browser import BrowserProxy, is_accession
from .client import WebinClient
from .config import WebinConfig
from .exceptions import (
    ENAAuthError,
    ENAClientError,
    ENAInvalidAccessionError,
    ENANotFoundError,
)
from .models import (
    AccessionRecord,
    AnalysisReport,
    ExperimentReport,
    FileReport,
    RunProcessReport,
    RunReport,
    SampleReport,
    StudyReport,
    SubmissionReceipt,
)
from .reports import ReportsProxy
from .submit import SubmitProxy, parse_receipt

__all__ = [
    "AccessionRecord",
    "AnalysisReport",
    "BrowserProxy",
    "ENAAuthError",
    "ENAClientError",
    "ENAInvalidAccessionError",
    "ENANotFoundError",
    "ExperimentReport",
    "FileReport",
    "ReportsProxy",
    "RunProcessReport",
    "RunReport",
    "SampleReport",
    "StudyReport",
    "SubmissionReceipt",
    "SubmitProxy",
    "WebinClient",
    "WebinConfig",
    "is_accession",
    "parse_receipt",
]
