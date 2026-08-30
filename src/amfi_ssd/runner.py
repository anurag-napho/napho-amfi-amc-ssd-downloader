from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import logging

from .discovery import AMFIDiscovery
from .downloader import build_session, download_file
from .models import AMC, DownloadResult, Scheme, SchemeRunResult, SSDLinks
from .reporting import append_report_row
from .utils import sanitize_filename, ensure_directory


LOGGER = logging.getLogger(__name__)
MAX_WORKERS = 16


@dataclass(frozen=True)
class SchemeDownloadJob:
    sequence: int
    amc: AMC
    scheme: Scheme
    links: SSDLinks
    output_path: Path
    force: bool


def _overall_status(statuses: list[str]) -> str:
    success_like = {"DOWNLOADED", "SKIPPED_EXISTING"}
    non_missing = [s for s in statuses if s != "MISSING"]

    if non_missing and all(s in success_like for s in non_missing):
        return "SUCCESS"
    if any(s in success_like for s in statuses):
        return "PARTIAL"
    return "FAILED"


def _failure_details(results: list[tuple[str, DownloadResult]]) -> str:
    failures = [
        f"{file_type}: {result.error or 'Unknown error'}"
        for file_type, result in results
        if result.status == "FAILED"
    ]
    return " | ".join(failures)


def _new_result(job: SchemeDownloadJob) -> SchemeRunResult:
    return SchemeRunResult(
        amc_id=job.amc.amc_id,
        amc_name=job.amc.amc_name,
        scheme_id=job.scheme.scheme_id,
        scheme_name=job.scheme.scheme_name,
        xml_url=job.links.xml_url or "",
        xls_url=job.links.xls_url or "",
        xlsx_url=job.links.xlsx_url or "",
        pdf_url=job.links.pdf_url or "",
    )


def _failed_result(job: SchemeDownloadJob, error: BaseException | str) -> SchemeRunResult:
    row = _new_result(job)
    row.overall_status = "FAILED"
    if isinstance(error, BaseException):
        detail = f"{type(error).__name__}: {error}"
    else:
        detail = error
    row.failure_details = f"Scheme processing: {detail}"
    return row


def _output_path(output_dir: Path, run_date: str, amc: AMC, scheme: Scheme) -> Path:
    amc_dir = sanitize_filename(amc.amc_name)
    scheme_dir = sanitize_filename(
        f"{scheme.scheme_id}_{scheme.scheme_name}",
        fallback=sanitize_filename(scheme.scheme_name),
    )
    return output_dir / run_date / amc_dir / scheme_dir


def _path_key(path: Path) -> str:
    """Return a portable key that detects case-only output collisions."""
    return str(path.resolve()).casefold()


def download_scheme(job: SchemeDownloadJob) -> SchemeRunResult:
    """Download one scheme with a session that belongs only to this job."""
    row = _new_result(job)
    session = None
    try:
        session = build_session()
        scheme_path = ensure_directory(job.output_path)
        results: list[tuple[str, DownloadResult]] = []

        for label, url, filename, kind, status_field, path_field in (
            ("SSD.xml", job.links.xml_url, "SSD.xml", "xml", "xml_status", "xml_path"),
            ("SSD.xls", job.links.xls_url, "SSD.xls", "xls", "xls_status", "xls_path"),
            (
                "SSD.xlsx",
                job.links.xlsx_url,
                "SSD.xlsx",
                "xlsx",
                "xlsx_status",
                "xlsx_path",
            ),
            ("SSD.pdf", job.links.pdf_url, "SSD.pdf", "pdf", "pdf_status", "pdf_path"),
        ):
            result = download_file(
                session,
                url,
                scheme_path / filename,
                kind,
                force=job.force,
            )
            setattr(row, status_field, result.status)
            setattr(row, path_field, result.path)
            results.append((label, result))

        row.failure_details = _failure_details(results)
        row.overall_status = _overall_status(
            [
                row.xml_status,
                row.xls_status,
                row.xlsx_status,
                row.pdf_status,
            ]
        )
        return row
    except Exception as exc:
        LOGGER.exception(
            "Scheme processing failed: %s / %s",
            job.amc.amc_name,
            job.scheme.scheme_name,
        )
        return _failed_result(job, exc)
    finally:
        close = getattr(session, "close", None)
        if close is not None:
            try:
                close()
            except Exception:
                LOGGER.exception(
                    "HTTP session close failed: %s / %s",
                    job.amc.amc_name,
                    job.scheme.scheme_name,
                )


def _update_totals(totals: dict, row: SchemeRunResult) -> None:
    totals["schemes_processed"] += 1
    if row.overall_status == "SUCCESS":
        totals["success"] += 1
    elif row.overall_status == "PARTIAL":
        totals["partial"] += 1
    else:
        totals["failed"] += 1


def run_downloader(
    output_dir: Path,
    report_file: Path,
    headed: bool = False,
    force: bool = False,
    amc_filter: str | None = None,
    limit_amcs: int | None = None,
    limit_schemes: int | None = None,
    workers: int = 4,
) -> dict:
    if not 1 <= workers <= MAX_WORKERS:
        raise ValueError(f"workers must be between 1 and {MAX_WORKERS}")

    run_date = datetime.now().date().isoformat()

    totals = {
        "amcs_discovered": 0,
        "amcs_processed": 0,
        "schemes_discovered": 0,
        "schemes_processed": 0,
        "success": 0,
        "partial": 0,
        "failed": 0,
        "cancelled": False,
    }

    executor = ThreadPoolExecutor(max_workers=workers) if workers > 1 else None
    pending: dict[Future, SchemeDownloadJob] = {}
    buffered: dict[int, SchemeRunResult] = {}
    next_to_write = 0
    sequence = 0
    output_paths: dict[str, SchemeDownloadJob] = {}
    max_outstanding = max(workers * 2, 1)

    def write_row(row: SchemeRunResult) -> None:
        append_report_row(report_file, run_date, row)
        _update_totals(totals, row)

    def flush_ordered() -> None:
        nonlocal next_to_write
        while next_to_write in buffered:
            write_row(buffered.pop(next_to_write))
            next_to_write += 1

    def collect(futures: set[Future]) -> None:
        for future in futures:
            job = pending.pop(future)
            if future.cancelled():
                continue
            try:
                buffered[job.sequence] = future.result()
            except BaseException as exc:
                LOGGER.exception(
                    "Download worker failed: %s / %s",
                    job.amc.amc_name,
                    job.scheme.scheme_name,
                )
                buffered[job.sequence] = _failed_result(job, exc)
        flush_ordered()

    def collect_one_or_more() -> None:
        if not pending:
            return
        done, _ = wait(set(pending), return_when=FIRST_COMPLETED)
        collect(done)

    def outstanding_count() -> int:
        return sequence - next_to_write

    try:
        with AMFIDiscovery(headed=headed) as discovery:
            amcs = discovery.get_amcs()
            totals["amcs_discovered"] = len(amcs)

            if amc_filter:
                target = amc_filter.strip().lower()
                amcs = [a for a in amcs if target in a.amc_name.lower()]

            if limit_amcs is not None:
                amcs = amcs[:limit_amcs]

            for amc in amcs:
                LOGGER.info("AMC: %s", amc.amc_name)
                totals["amcs_processed"] += 1

                try:
                    schemes = discovery.get_schemes(amc)
                except Exception:
                    LOGGER.exception("Scheme discovery failed for %s", amc.amc_name)
                    continue

                totals["schemes_discovered"] += len(schemes)

                if limit_schemes is not None:
                    schemes = schemes[:limit_schemes]

                for scheme in schemes:
                    LOGGER.info("Scheme: %s", scheme.scheme_name)
                    job_sequence = sequence
                    sequence += 1
                    path = _output_path(output_dir, run_date, amc, scheme)
                    try:
                        links = discovery.get_ssd_links(amc, scheme)
                    except Exception as exc:
                        LOGGER.exception(
                            "Document discovery failed: %s / %s",
                            amc.amc_name,
                            scheme.scheme_name,
                        )
                        job = SchemeDownloadJob(
                            sequence=job_sequence,
                            amc=amc,
                            scheme=scheme,
                            links=SSDLinks(),
                            output_path=path,
                            force=force,
                        )
                        buffered[job.sequence] = _failed_result(
                            job, f"Document discovery: {type(exc).__name__}: {exc}"
                        )
                        flush_ordered()
                        while outstanding_count() >= max_outstanding and pending:
                            collect_one_or_more()
                        continue
                    job = SchemeDownloadJob(
                        sequence=job_sequence,
                        amc=amc,
                        scheme=scheme,
                        links=links,
                        output_path=path,
                        force=force,
                    )

                    path_key = _path_key(path)
                    previous = output_paths.get(path_key)
                    if previous is not None:
                        error = (
                            "Duplicate output path matches "
                            f"scheme {previous.scheme.scheme_id}: {path}"
                        )
                        LOGGER.error("%s", error)
                        buffered[job.sequence] = _failed_result(job, error)
                        flush_ordered()
                    else:
                        output_paths[path_key] = job
                        if executor is None:
                            buffered[job.sequence] = download_scheme(job)
                            flush_ordered()
                        else:
                            future = executor.submit(download_scheme, job)
                            pending[future] = job

                    while outstanding_count() >= max_outstanding and pending:
                        collect_one_or_more()

            while pending:
                collect_one_or_more()

    except KeyboardInterrupt:
        totals["cancelled"] = True
        LOGGER.warning("Cancellation requested. Cancelling pending download jobs.")
        for future in pending:
            future.cancel()
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)
            executor = None
        completed = {
            future for future in pending if future.done() and not future.cancelled()
        }
        collect(completed)
        for row_sequence in sorted(buffered):
            write_row(buffered[row_sequence])
        buffered.clear()
    finally:
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)

    return totals
