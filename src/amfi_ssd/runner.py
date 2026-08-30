from __future__ import annotations

from datetime import datetime
from pathlib import Path
import logging

from .discovery import AMFIDiscovery
from .downloader import build_session, download_file
from .models import AMC, DownloadResult, SchemeRunResult
from .reporting import append_report_row
from .utils import sanitize_filename, ensure_directory


LOGGER = logging.getLogger(__name__)


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


def run_downloader(
    output_dir: Path,
    report_file: Path,
    headed: bool = False,
    force: bool = False,
    amc_filter: str | None = None,
    limit_amcs: int | None = None,
    limit_schemes: int | None = None,
) -> dict:
    run_date = datetime.now().date().isoformat()
    session = build_session()

    totals = {
        "amcs_discovered": 0,
        "amcs_processed": 0,
        "schemes_discovered": 0,
        "schemes_processed": 0,
        "success": 0,
        "partial": 0,
        "failed": 0,
    }

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
            except Exception as exc:
                LOGGER.exception("Scheme discovery failed for %s", amc.amc_name)
                continue

            totals["schemes_discovered"] += len(schemes)

            if limit_schemes is not None:
                schemes = schemes[:limit_schemes]

            for scheme in schemes:
                totals["schemes_processed"] += 1
                LOGGER.info("Scheme: %s", scheme.scheme_name)

                row = SchemeRunResult(
                    amc_id=amc.amc_id,
                    amc_name=amc.amc_name,
                    scheme_id=scheme.scheme_id,
                    scheme_name=scheme.scheme_name,
                )

                try:
                    links = discovery.get_ssd_links(amc, scheme)
                    row.xml_url = links.xml_url or ""
                    row.xls_url = links.xls_url or ""
                    row.xlsx_url = links.xlsx_url or ""
                    row.pdf_url = links.pdf_url or ""

                    amc_dir = sanitize_filename(amc.amc_name)
                    scheme_dir = sanitize_filename(
                        f"{scheme.scheme_id}_{scheme.scheme_name}",
                        fallback=sanitize_filename(scheme.scheme_name),
                    )
                    scheme_path = ensure_directory(
                        output_dir / run_date / amc_dir / scheme_dir
                    )

                    xml = download_file(
                        session,
                        links.xml_url,
                        scheme_path / "SSD.xml",
                        "xml",
                        force=force,
                    )
                    row.xml_status = xml.status
                    row.xml_path = xml.path

                    xls = download_file(
                        session,
                        links.xls_url,
                        scheme_path / "SSD.xls",
                        "xls",
                        force=force,
                    )
                    row.xls_status = xls.status
                    row.xls_path = xls.path

                    xlsx = download_file(
                        session,
                        links.xlsx_url,
                        scheme_path / "SSD.xlsx",
                        "xlsx",
                        force=force,
                    )
                    row.xlsx_status = xlsx.status
                    row.xlsx_path = xlsx.path

                    pdf = download_file(
                        session,
                        links.pdf_url,
                        scheme_path / "SSD.pdf",
                        "pdf",
                        force=force,
                    )
                    row.pdf_status = pdf.status
                    row.pdf_path = pdf.path

                    row.failure_details = _failure_details(
                        [
                            ("SSD.xml", xml),
                            ("SSD.xls", xls),
                            ("SSD.xlsx", xlsx),
                            ("SSD.pdf", pdf),
                        ]
                    )

                    row.overall_status = _overall_status(
                        [
                            row.xml_status,
                            row.xls_status,
                            row.xlsx_status,
                            row.pdf_status,
                        ]
                    )

                except Exception as exc:
                    LOGGER.exception(
                        "Scheme processing failed: %s / %s",
                        amc.amc_name,
                        scheme.scheme_name,
                    )
                    row.overall_status = "FAILED"
                    row.failure_details = (
                        f"Scheme processing: {type(exc).__name__}: {exc}"
                    )

                append_report_row(report_file, run_date, row)

                if row.overall_status == "SUCCESS":
                    totals["success"] += 1
                elif row.overall_status == "PARTIAL":
                    totals["partial"] += 1
                else:
                    totals["failed"] += 1

    return totals
