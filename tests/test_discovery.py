import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from amfi_ssd.discovery import (  # noqa: E402
    AMFIDiscovery,
    DOCUMENTS_URL,
    SCHEME_DETAILS_URL,
    SCHEMES_URL,
)
from amfi_ssd.models import AMC, Scheme  # noqa: E402


class FakeResponse:
    def __init__(self, *, text="", payload=None):
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.headers = {}
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class FakeFallback:
    def __init__(self):
        self.calls = []

    def close(self):
        return None

    def get_amcs(self):
        self.calls.append("amcs")
        return [AMC(amc_id="62", amc_name="360 ONE Mutual Fund")]

    def get_schemes(self, amc):
        self.calls.append(("schemes", amc.amc_id))
        return [Scheme(scheme_id="7119", scheme_name="Fallback Scheme")]

    def get_ssd_links(self, amc, scheme):
        raise AssertionError("Not used in this test")


def next_page_html(mutual_funds):
    payload = f'c:["$","component",null,{{"mutualFunds":{json.dumps(mutual_funds)}}}]\n'
    return f"<script>self.__next_f.push([1,{json.dumps(payload)}])</script>"


def test_get_amcs_parses_next_page_payload():
    session = FakeSession(
        [
            FakeResponse(
                text=next_page_html(
                    [
                        {"mf_id": "62", "mf_name": "360 ONE Mutual Fund"},
                        {"mf_id": "9", "mf_name": "HDFC Mutual Fund"},
                    ]
                )
            )
        ]
    )

    discovery = AMFIDiscovery(session=session)

    assert discovery.get_amcs() == [
        AMC(amc_id="62", amc_name="360 ONE Mutual Fund"),
        AMC(amc_id="9", amc_name="HDFC Mutual Fund"),
    ]
    assert session.calls[0][0] == SCHEME_DETAILS_URL


def test_get_schemes_uses_mf_id_and_parses_required_fields():
    session = FakeSession(
        [
            FakeResponse(
                payload=[
                    {
                        "scheme_id": "7119",
                        "scheme_name": "360 ONE Dynamic Term Fund",
                    }
                ]
            )
        ]
    )
    discovery = AMFIDiscovery(session=session)
    amc = AMC(amc_id="62", amc_name="360 ONE Mutual Fund")

    assert discovery.get_schemes(amc) == [
        Scheme(scheme_id="7119", scheme_name="360 ONE Dynamic Term Fund")
    ]
    assert session.calls[0][0] == SCHEMES_URL
    assert session.calls[0][1]["params"] == {"MF_ID": "62"}


def test_get_ssd_links_maps_amfi_fields_without_guessing_urls():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "data": [
                        {
                            "schemeId": "7119",
                            "summaryPdfUrl": (
                                "https://portal.amfiindia.com/spages/SSD_7119.pdf"
                            ),
                            "summaryXlsUrl": (
                                "https://portal.amfiindia.com/spages/SSD_7119.xls"
                            ),
                            "summaryXmlUrl": (
                                "https://portal.amfiindia.com/spages/SSD_7119.xml"
                            ),
                        }
                    ]
                }
            )
        ]
    )
    discovery = AMFIDiscovery(session=session)
    amc = AMC(amc_id="62", amc_name="360 ONE Mutual Fund")
    scheme = Scheme(scheme_id="7119", scheme_name="360 ONE Dynamic Term Fund")

    links = discovery.get_ssd_links(amc, scheme)

    assert links.xml_url == "https://portal.amfiindia.com/spages/SSD_7119.xml"
    assert links.xls_url == "https://portal.amfiindia.com/spages/SSD_7119.xls"
    assert links.xlsx_url is None
    assert links.pdf_url == "https://portal.amfiindia.com/spages/SSD_7119.pdf"
    assert session.calls[0][0] == DOCUMENTS_URL.format(scheme_id="7119")


def test_get_ssd_links_returns_none_for_missing_formats():
    session = FakeSession(
        [
            FakeResponse(
                payload={
                    "data": [
                        {
                            "schemeId": "7119",
                            "summaryPdfUrl": None,
                            "summaryXlsUrl": "",
                        }
                    ]
                }
            )
        ]
    )
    discovery = AMFIDiscovery(session=session)

    links = discovery.get_ssd_links(
        AMC(amc_id="62", amc_name="360 ONE Mutual Fund"),
        Scheme(scheme_id="7119", scheme_name="360 ONE Dynamic Term Fund"),
    )

    assert links.xml_url is None
    assert links.xls_url is None
    assert links.xlsx_url is None
    assert links.pdf_url is None


def test_invalid_direct_scheme_response_uses_discovery_fallback():
    session = FakeSession([FakeResponse(payload={"unexpected": "shape"})])
    fallback = FakeFallback()
    discovery = AMFIDiscovery(session=session, fallback=fallback)

    schemes = discovery.get_schemes(
        AMC(amc_id="62", amc_name="360 ONE Mutual Fund")
    )

    assert schemes == [Scheme(scheme_id="7119", scheme_name="Fallback Scheme")]
    assert fallback.calls == [("schemes", "62")]
