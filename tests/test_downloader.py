from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from amfi_ssd.downloader import download_file  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, chunks=()):
        self.status_code = status_code
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        yield from self._chunks


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_existing_file_is_skipped_only_after_streamed_url_check(tmp_path):
    output_path = tmp_path / "SSD.pdf"
    output_path.write_bytes(b"%PDF-valid local file")
    session = FakeSession([FakeResponse(status_code=200)])

    result = download_file(
        session,
        "https://portal.amfiindia.com/SSD.pdf",
        output_path,
        "pdf",
    )

    assert result.status == "SKIPPED_EXISTING"
    assert session.calls == [
        (
            "https://portal.amfiindia.com/SSD.pdf",
            {"stream": True, "timeout": 60, "allow_redirects": True},
        )
    ]


def test_unavailable_url_fails_even_when_valid_local_file_exists(tmp_path):
    output_path = tmp_path / "SSD.pdf"
    original = b"%PDF-valid local file"
    output_path.write_bytes(original)
    session = FakeSession([FakeResponse(status_code=404)])

    result = download_file(
        session,
        "https://portal.amfiindia.com/SSD.pdf",
        output_path,
        "pdf",
    )

    assert result.status == "FAILED"
    assert result.error == "HTTP 404"
    assert output_path.read_bytes() == original


def test_streamed_response_downloads_and_validates_file(tmp_path):
    output_path = tmp_path / "SSD.xml"
    session = FakeSession(
        [FakeResponse(chunks=[b"<?xml version='1.0'?>", b"<root />"])]
    )

    result = download_file(
        session,
        "https://portal.amfiindia.com/SSD.xml",
        output_path,
        "xml",
    )

    assert result.status == "DOWNLOADED"
    assert output_path.read_bytes() == b"<?xml version='1.0'?><root />"
    assert not (tmp_path / "SSD.xml.part").exists()
