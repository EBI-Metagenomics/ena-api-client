"""Tests for ena_api.models."""

from __future__ import annotations

from ena_api import (
    AccessionRecord,
    AnalysisReport,
    ExperimentReport,
    FileReport,
    RunReport,
    SampleReport,
    StudyReport,
    SubmissionReceipt,
)


class TestAccessionRecord:
    def test_defaults(self):
        rec = AccessionRecord()
        assert rec.alias == ""
        assert rec.accession == ""
        assert rec.status == ""
        assert rec.hold_until_date == ""
        assert rec.external_accession == ""
        assert rec.external_type == ""
        assert rec.entity_type == ""

    def test_hold_until_alias(self):
        rec = AccessionRecord(holdUntilDate="2030-01-01")
        assert rec.hold_until_date == "2030-01-01"

    def test_round_trip(self):
        rec = AccessionRecord(alias="s1", accession="ERS1", status="PRIVATE")
        assert rec.alias == "s1"
        assert rec.accession == "ERS1"


class TestSubmissionReceipt:
    def test_defaults(self):
        r = SubmissionReceipt()
        assert r.success is False
        assert r.accessions == []
        assert r.messages == []
        assert r.errors == []

    def test_with_accessions(self):
        r = SubmissionReceipt(
            success=True,
            accessions=[AccessionRecord(alias="s1", accession="ERS1")],
            messages=["INFO: ok"],
            errors=[],
        )
        assert r.success is True
        assert len(r.accessions) == 1


class TestReports:
    def test_study_report(self):
        s = StudyReport(alias="a", accession="ERP1", title="t", status="PRIVATE")
        assert s.alias == "a"
        assert s.title == "t"

    def test_sample_report(self):
        s = SampleReport(alias="a", accession="ERS1", title="t")
        assert s.accession == "ERS1"
        assert s.status == "UNKNOWN"  # default

    def test_run_report(self):
        r = RunReport(alias="r", accession="ERR1", experiment_accession="ERX1")
        assert r.experiment_accession == "ERX1"

    def test_experiment_report(self):
        e = ExperimentReport(alias="e", accession="ERX1", study_accession="ERP1")
        assert e.study_accession == "ERP1"

    def test_analysis_report(self):
        a = AnalysisReport(alias="a", accession="ERZ1", study_accession="ERP1")
        assert a.accession == "ERZ1"

    def test_file_report(self):
        f = FileReport(filename="reads.fastq.gz", checksum="abc", checksum_method="MD5")
        assert f.filename == "reads.fastq.gz"
        assert f.checksum == "abc"

    def test_extra_fields_ignored(self):
        s = StudyReport.model_validate({"alias": "a", "unknown_field": "x"})
        assert s.alias == "a"
