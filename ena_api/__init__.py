"""Typed Python client for the ENA Webin Submission and Reports APIs."""

from __future__ import annotations

from .client import WebinClient
from .config import WebinConfig
from .models import (
    AccessionRecord,
    AnalysisReport,
    ExperimentReport,
    FileReport,
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
    "ExperimentReport",
    "FileReport",
    "ReportsProxy",
    "RunReport",
    "SampleReport",
    "StudyReport",
    "SubmissionReceipt",
    "SubmitProxy",
    "WebinClient",
    "WebinConfig",
    "parse_receipt",
]
