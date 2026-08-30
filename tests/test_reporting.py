import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from amfi_ssd.models import SchemeRunResult  # noqa: E402
from amfi_ssd.reporting import append_report_row  # noqa: E402


def test_report_uses_simple_columns_and_one_failure_column(tmp_path):
    report_path = tmp_path / "report.csv"
    row = SchemeRunResult(
        amc_id="62",
        amc_name="360 ONE Mutual Fund",
        scheme_id="7119",
        scheme_name="360 ONE Dynamic Term Fund",
        xml_status="DOWNLOADED",
        xls_status="DOWNLOADED",
        xlsx_status="MISSING",
        pdf_status="FAILED",
        overall_status="PARTIAL",
        failure_details="SSD.pdf: HTTP 404",
    )

    append_report_row(report_path, "2026-08-28", row)

    with report_path.open(encoding="utf-8-sig", newline="") as report_file:
        rows = list(csv.DictReader(report_file))

    assert list(rows[0]) == [
        "Run Date",
        "AMC",
        "Scheme",
        "XML Status",
        "XLS Status",
        "PDF Status",
        "Overall Result",
        "Failure Details",
    ]
    assert rows[0] == {
        "Run Date": "2026-08-28",
        "AMC": "360 ONE Mutual Fund",
        "Scheme": "360 ONE Dynamic Term Fund",
        "XML Status": "DOWNLOADED",
        "XLS Status": "DOWNLOADED",
        "PDF Status": "FAILED",
        "Overall Result": "PARTIAL",
        "Failure Details": "SSD.pdf: HTTP 404",
    }
