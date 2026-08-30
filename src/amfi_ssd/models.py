from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class AMC:
    amc_id: str
    amc_name: str


@dataclass(frozen=True)
class Scheme:
    scheme_id: str
    scheme_name: str


@dataclass
class SSDLinks:
    xml_url: Optional[str] = None
    xls_url: Optional[str] = None
    xlsx_url: Optional[str] = None
    pdf_url: Optional[str] = None


@dataclass
class DownloadResult:
    status: str
    path: str = ""
    error: str = ""


@dataclass
class SchemeRunResult:
    amc_id: str
    amc_name: str
    scheme_id: str
    scheme_name: str
    xml_url: str = ""
    xls_url: str = ""
    xlsx_url: str = ""
    pdf_url: str = ""
    xml_status: str = "MISSING"
    xml_path: str = ""
    xls_status: str = "MISSING"
    xls_path: str = ""
    xlsx_status: str = "MISSING"
    xlsx_path: str = ""
    pdf_status: str = "MISSING"
    pdf_path: str = ""
    overall_status: str = "FAILED"
    failure_details: str = ""
