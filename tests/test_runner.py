import csv
from concurrent.futures import Future
from pathlib import Path
import sys
import threading


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from amfi_ssd.models import (  # noqa: E402
    AMC,
    DownloadResult,
    Scheme,
    SchemeRunResult,
    SSDLinks,
)
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


class TwoSchemeDiscovery:
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


class ClosableSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _missing_or_downloaded(url, output_path):
    if url is None:
        return DownloadResult(status="MISSING")
    return DownloadResult(status="DOWNLOADED", path=str(output_path))


def test_workers_one_keeps_scheme_downloads_sequential(tmp_path, monkeypatch):
    events = []

    class RecordingDiscovery(TwoSchemeDiscovery):
        def get_ssd_links(self, amc, scheme):
            events.append(f"discover-{scheme.scheme_id}")
            return super().get_ssd_links(amc, scheme)

    def fake_download(session, url, output_path, kind, force=False):
        del session, kind, force
        if url is not None:
            events.append(f"download-{output_path.parent.name[0]}")
        return _missing_or_downloaded(url, output_path)

    monkeypatch.setattr(runner, "AMFIDiscovery", RecordingDiscovery)
    monkeypatch.setattr(runner, "build_session", ClosableSession)
    monkeypatch.setattr(runner, "download_file", fake_download)

    runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=tmp_path / "report.csv",
        workers=1,
    )

    assert events == ["discover-1", "download-1", "discover-2", "download-2"]


def test_scheme_jobs_overlap_and_use_separate_sessions(tmp_path, monkeypatch):
    barrier = threading.Barrier(2, timeout=2)
    sessions = []
    session_lock = threading.Lock()

    def session_factory():
        session = ClosableSession()
        with session_lock:
            sessions.append(session)
        return session

    def fake_download(session, url, output_path, kind, force=False):
        del session, kind, force
        if url is not None:
            barrier.wait()
        return _missing_or_downloaded(url, output_path)

    monkeypatch.setattr(runner, "AMFIDiscovery", TwoSchemeDiscovery)
    monkeypatch.setattr(runner, "build_session", session_factory)
    monkeypatch.setattr(runner, "download_file", fake_download)

    totals = runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=tmp_path / "report.csv",
        workers=2,
    )

    assert totals["success"] == 2
    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    assert all(session.closed for session in sessions)


def test_download_starts_while_main_thread_discovers_later_schemes(
    tmp_path, monkeypatch
):
    first_download_started = threading.Event()

    class StreamingDiscovery(TwoSchemeDiscovery):
        def get_ssd_links(self, amc, scheme):
            if scheme.scheme_id == "2":
                assert first_download_started.wait(timeout=2)
            return super().get_ssd_links(amc, scheme)

    def fake_download(session, url, output_path, kind, force=False):
        del session, kind, force
        if url is not None:
            first_download_started.set()
        return _missing_or_downloaded(url, output_path)

    monkeypatch.setattr(runner, "AMFIDiscovery", StreamingDiscovery)
    monkeypatch.setattr(runner, "build_session", ClosableSession)
    monkeypatch.setattr(runner, "download_file", fake_download)

    runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=tmp_path / "report.csv",
        workers=2,
    )


def test_report_rows_stay_in_discovery_order(tmp_path, monkeypatch):
    second_completed = threading.Event()
    main_thread_id = threading.get_ident()
    report_thread_ids = []
    totals_thread_ids = []
    original_append_report_row = runner.append_report_row
    original_update_totals = runner._update_totals

    def fake_download(session, url, output_path, kind, force=False):
        del session, kind, force
        if url is None:
            return DownloadResult(status="MISSING")
        if output_path.parent.name.startswith("1_"):
            assert second_completed.wait(timeout=2)
        else:
            second_completed.set()
        return DownloadResult(status="DOWNLOADED", path=str(output_path))

    monkeypatch.setattr(runner, "AMFIDiscovery", TwoSchemeDiscovery)
    monkeypatch.setattr(runner, "build_session", ClosableSession)
    monkeypatch.setattr(runner, "download_file", fake_download)
    monkeypatch.setattr(
        runner,
        "append_report_row",
        lambda *args: (
            report_thread_ids.append(threading.get_ident()),
            original_append_report_row(*args),
        )[1],
    )
    monkeypatch.setattr(
        runner,
        "_update_totals",
        lambda *args: (
            totals_thread_ids.append(threading.get_ident()),
            original_update_totals(*args),
        )[1],
    )
    report_path = tmp_path / "report.csv"

    runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=report_path,
        workers=2,
    )

    with report_path.open(encoding="utf-8-sig", newline="") as report_file:
        rows = list(csv.DictReader(report_file))
    assert [row["Scheme"] for row in rows] == ["First", "Second"]
    assert report_thread_ids == [main_thread_id, main_thread_id]
    assert totals_thread_ids == [main_thread_id, main_thread_id]


def test_main_thread_updates_totals_for_all_scheme_statuses(tmp_path, monkeypatch):
    class ThreeSchemeDiscovery(TwoSchemeDiscovery):
        def get_schemes(self, amc):
            del amc
            return [
                Scheme("1", "Success"),
                Scheme("2", "Partial"),
                Scheme("3", "Failed"),
            ]

    def fake_download(session, url, output_path, kind, force=False):
        del session, url, force
        scheme_id = output_path.parent.name[0]
        if scheme_id == "1":
            return DownloadResult(status="DOWNLOADED", path=str(output_path))
        if scheme_id == "2" and kind == "xml":
            return DownloadResult(status="DOWNLOADED", path=str(output_path))
        return DownloadResult(status="FAILED", error="test failure")

    monkeypatch.setattr(runner, "AMFIDiscovery", ThreeSchemeDiscovery)
    monkeypatch.setattr(runner, "build_session", ClosableSession)
    monkeypatch.setattr(runner, "download_file", fake_download)

    totals = runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=tmp_path / "report.csv",
        workers=3,
    )

    assert totals["schemes_processed"] == 3
    assert totals["success"] == 1
    assert totals["partial"] == 1
    assert totals["failed"] == 1


def test_unexpected_worker_exception_does_not_stop_other_workers(
    tmp_path, monkeypatch
):
    original_download_scheme = runner.download_scheme

    def crashing_worker(job):
        if job.scheme.scheme_id == "1":
            raise RuntimeError("worker crashed")
        return original_download_scheme(job)

    monkeypatch.setattr(runner, "AMFIDiscovery", TwoSchemeDiscovery)
    monkeypatch.setattr(runner, "build_session", ClosableSession)
    monkeypatch.setattr(
        runner,
        "download_file",
        lambda session, url, output_path, kind, force=False: _missing_or_downloaded(
            url, output_path
        ),
    )
    monkeypatch.setattr(runner, "download_scheme", crashing_worker)

    totals = runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=tmp_path / "report.csv",
        workers=2,
    )

    assert totals["schemes_processed"] == 2
    assert totals["failed"] == 1
    assert totals["success"] == 1


def test_discovery_stays_on_the_main_thread(tmp_path, monkeypatch):
    main_thread_id = threading.get_ident()

    class MainThreadDiscovery(TwoSchemeDiscovery):
        def get_amcs(self):
            assert threading.get_ident() == main_thread_id
            return super().get_amcs()

        def get_schemes(self, amc):
            assert threading.get_ident() == main_thread_id
            return super().get_schemes(amc)

        def get_ssd_links(self, amc, scheme):
            assert threading.get_ident() == main_thread_id
            return super().get_ssd_links(amc, scheme)

    monkeypatch.setattr(runner, "AMFIDiscovery", MainThreadDiscovery)
    monkeypatch.setattr(runner, "build_session", ClosableSession)
    monkeypatch.setattr(
        runner,
        "download_file",
        lambda session, url, output_path, kind, force=False: _missing_or_downloaded(
            url, output_path
        ),
    )

    runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=tmp_path / "report.csv",
        workers=2,
    )


def test_duplicate_output_path_is_not_submitted_twice(tmp_path, monkeypatch):
    class DuplicateDiscovery(TwoSchemeDiscovery):
        def get_schemes(self, amc):
            del amc
            return [Scheme("1", "Same"), Scheme("1", "same")]

    submitted = []

    def fake_worker(job):
        submitted.append(job)
        row = SchemeRunResult(
            amc_id=job.amc.amc_id,
            amc_name=job.amc.amc_name,
            scheme_id=job.scheme.scheme_id,
            scheme_name=job.scheme.scheme_name,
            overall_status="SUCCESS",
        )
        return row

    monkeypatch.setattr(runner, "AMFIDiscovery", DuplicateDiscovery)
    monkeypatch.setattr(runner, "download_scheme", fake_worker)

    totals = runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=tmp_path / "report.csv",
        workers=2,
    )

    assert len(submitted) == 1
    assert totals["success"] == 1
    assert totals["failed"] == 1


def test_ctrl_c_cancels_pending_jobs_and_keeps_completed_rows(
    tmp_path, monkeypatch
):
    class FourSchemeDiscovery(TwoSchemeDiscovery):
        def get_schemes(self, amc):
            del amc
            return [Scheme(str(number), f"Scheme {number}") for number in range(4)]

    executors = []

    class FakeExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers
            self.futures = []
            self.shutdown_calls = []
            executors.append(self)

        def submit(self, function, job):
            del function
            future = Future()
            if not self.futures:
                future.set_result(
                    SchemeRunResult(
                        amc_id=job.amc.amc_id,
                        amc_name=job.amc.amc_name,
                        scheme_id=job.scheme.scheme_id,
                        scheme_name=job.scheme.scheme_name,
                        overall_status="SUCCESS",
                    )
                )
            self.futures.append(future)
            return future

        def shutdown(self, wait=True, cancel_futures=False):
            self.shutdown_calls.append((wait, cancel_futures))

    def interrupt_wait(futures, return_when):
        del futures, return_when
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "AMFIDiscovery", FourSchemeDiscovery)
    monkeypatch.setattr(runner, "ThreadPoolExecutor", FakeExecutor)
    monkeypatch.setattr(runner, "wait", interrupt_wait)
    report_path = tmp_path / "report.csv"

    totals = runner.run_downloader(
        output_dir=tmp_path / "downloads",
        report_file=report_path,
        workers=2,
    )

    assert totals["cancelled"] is True
    assert totals["schemes_processed"] == 1
    assert executors[0].shutdown_calls == [(True, True)]
    assert all(future.cancelled() for future in executors[0].futures[1:])
    with report_path.open(encoding="utf-8-sig", newline="") as report_file:
        rows = list(csv.DictReader(report_file))
    assert [row["Scheme"] for row in rows] == ["Scheme 0"]
