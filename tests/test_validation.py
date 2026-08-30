from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from amfi_ssd.validation import validate_pdf, validate_xml


def test_validate_pdf(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.7\n")
    ok, _ = validate_pdf(p)
    assert ok


def test_validate_xml(tmp_path):
    p = tmp_path / "a.xml"
    p.write_text("<root><x>1</x></root>", encoding="utf-8")
    ok, _ = validate_xml(p)
    assert ok
