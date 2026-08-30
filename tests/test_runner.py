from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from amfi_ssd.models import AMC, DownloadResult, Scheme, SSDLinks  # noqa: E402
from amfi_ssd import runner  # noqa: E402
from amfi_ssd.runner import _failure_details  # noqa: E402


def test_failure_details_names_each_failed_file():
    details = _failure_details(
        [
            ("SSD.xml", DownloadResult(status="FAILED", error="Invalid XML")),
            ("SSD.xls", DownloadResult(status="DOWNLOADED")),
            ("SSD.pdf", DownloadResult(status="FAILED", error="HTTP 404")),
        ]
    )

    assert details == "SSD.xml: Invalid XML | SSD.pdf: HTTP 404"


def test_failure_details_is_empty_when_no_file_failed():
    details = _failure_details(
        [
            ("SSD.xml", DownloadResult(status="DOWNLOADED")),
            ("SSD.xls", DownloadResult(status="SKIPPED_EXISTING")),
            ("SSD.pdf", DownloadResult(status="MISSING")),
        ]
    )

    assert details == ""


def test_failed_file_does_not_stop_the_next_scheme(tmp_path, monkeypatch):
    class FakeDiscovery:
        def __init__(self, headed=False):
            del headed

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def get_amcs(self):
            return [AMC("62", "Test AMC")]

        def get_schemes(self, amc):
            del amc
            return [Scheme("1", "First"), Scheme("2", "Second")]

        def get_ssd_links(self, amc, scheme):
            del amc
            return SSDLinks(xml_url=f"https://example.test/{scheme.scheme_id}.xml")

    seen_schemes = []

    def fake_download(session, url, output_path, kind, force=False):
        del session, url, kind, force
        seen_schemes.append(output_path.parent.name)
        if output_path.parent.name.startswith("1_"):
            return DownloadResult(status="FAILED", error="HTTP 503")
        return DownloadResult(status="DOWNLOADED", path=str(output_path))

    monkeypatch.setattr(runner, "AMFIDiscovery", FakeDiscovery)
    monkeypatch.setattr(runner, "build_session", object)
    monkeypatch.setattr(runner, "download_file", fake_download)

    totals = runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=tmp_path / "report.csv",
    )

    assert any(name.startswith("1_") for name in seen_schemes)
    assert any(name.startswith("2_") for name in seen_schemes)
    assert totals["schemes_processed"] == 2
    assert totals["failed"] == 1
    assert totals["success"] == 1
