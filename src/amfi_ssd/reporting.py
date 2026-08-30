from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from .models import SchemeRunResult


REPORT_COLUMNS = [
    ("run_date", "Run Date"),
    ("amc_name", "AMC"),
    ("scheme_name", "Scheme"),
    ("xml_status", "XML Status"),
    ("xls_status", "XLS Status"),
    ("pdf_status", "PDF Status"),
    ("overall_status", "Overall Result"),
    ("failure_details", "Failure Details"),
]


def append_report_row(path: Path, run_date: str, row: SchemeRunResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()

    data = asdict(row)
    data["run_date"] = run_date

    with path.open("a", newline="", encoding="utf-8-sig") as f:
        headers = [header for _, header in REPORT_COLUMNS]
        writer = csv.DictWriter(f, fieldnames=headers)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {header: data.get(field, "") for field, header in REPORT_COLUMNS}
        )
