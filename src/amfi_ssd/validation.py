from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET


def _head(path: Path, size: int = 512) -> bytes:
    with path.open("rb") as f:
        return f.read(size)


def is_html(path: Path) -> bool:
    head = _head(path, 1024).lstrip().lower()
    return (
        head.startswith(b"<!doctype html")
        or head.startswith(b"<html")
        or b"<html" in head[:512]
    )


def validate_xml(path: Path) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size == 0:
        return False, "XML file is empty."
    if is_html(path):
        return False, "XML response is HTML."
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        return False, f"Invalid XML: {exc}"
    return True, ""


def validate_pdf(path: Path) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size == 0:
        return False, "PDF file is empty."
    if not _head(path, 8).startswith(b"%PDF"):
        return False, "File does not have a PDF signature."
    return True, ""


def validate_spreadsheet(path: Path) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size == 0:
        return False, "Spreadsheet file is empty."
    if is_html(path):
        return False, "Spreadsheet response is HTML."
    return True, ""


def validate_file(path: Path, kind: str) -> tuple[bool, str]:
    kind = kind.lower()
    if kind == "xml":
        return validate_xml(path)
    if kind == "pdf":
        return validate_pdf(path)
    if kind in {"xls", "xlsx"}:
        return validate_spreadsheet(path)
    return False, f"Unknown file kind: {kind}"
