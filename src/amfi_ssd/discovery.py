from __future__ import annotations

import json
import logging
import re
from typing import Protocol

import requests

from .models import AMC, Scheme, SSDLinks


LOGGER = logging.getLogger(__name__)
BASE_URL = "https://www.amfiindia.com"
SCHEME_DETAILS_URL = f"{BASE_URL}/otherdata/scheme-details"
SCHEMES_URL = f"{BASE_URL}/api/populate-scheme"
DOCUMENTS_URL = f"{BASE_URL}/api/schemes/{{scheme_id}}/documents"

_NEXT_FLIGHT_CHUNK = re.compile(
    r'self\.__next_f\.push\(\[1,("(?:\\.|[^"\\])*")\]\)'
)
_MUTUAL_FUNDS_MARKER = '"mutualFunds":'


class DiscoveryBackend(Protocol):
    def close(self) -> None: ...

    def get_amcs(self) -> list[AMC]: ...

    def get_schemes(self, amc: AMC) -> list[Scheme]: ...

    def get_ssd_links(self, amc: AMC, scheme: Scheme) -> SSDLinks: ...


def _optional_url(document: dict, field: str) -> str | None:
    value = document.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"AMFI document field {field} was not text.")
    return value.strip() or None


def _parse_ssd_document(document: dict) -> SSDLinks:
    return SSDLinks(
        xml_url=_optional_url(document, "summaryXmlUrl"),
        xls_url=_optional_url(document, "summaryXlsUrl"),
        pdf_url=_optional_url(document, "summaryPdfUrl"),
    )


class PlaywrightDiscovery:
    """Use AMFI's interactive page when direct HTTP discovery fails."""

    def __init__(self, *, headed: bool, timeout_ms: int):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Playwright fallback is unavailable. Install the project requirements."
            ) from exc

        self.timeout_ms = timeout_ms
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=not headed)
            self._page = self._browser.new_page()
            self._page.set_default_timeout(timeout_ms)
        except Exception as exc:
            self.close()
            raise RuntimeError(f"Playwright fallback could not start: {exc}") from exc

    def close(self) -> None:
        browser = getattr(self, "_browser", None)
        playwright = getattr(self, "_playwright", None)
        if browser is not None:
            browser.close()
            self._browser = None
        if playwright is not None:
            playwright.stop()
            self._playwright = None

    def _load_page(self) -> None:
        self._page.goto(
            SCHEME_DETAILS_URL,
            wait_until="networkidle",
            timeout=self.timeout_ms,
        )

    def _select_amc(self, amc: AMC) -> None:
        field = self._page.get_by_placeholder("Select Mutual Fund")
        field.click()
        self._page.get_by_role("option", name=amc.amc_name, exact=True).click()
        self._page.get_by_placeholder("Select Scheme Name").wait_for(
            state="visible"
        )

    def _response_payloads(self, action) -> list[object]:
        responses = []

        def collect(response) -> None:
            responses.append(response)

        self._page.on("response", collect)
        try:
            action()
            self._page.wait_for_timeout(1_000)
            self._page.wait_for_load_state("networkidle")
        finally:
            self._page.remove_listener("response", collect)

        payloads = []
        for response in responses:
            try:
                payloads.append(response.json())
            except Exception:
                continue
        return payloads

    @staticmethod
    def _find_schemes(payloads: list[object]) -> list[Scheme]:
        for payload in reversed(payloads):
            if not isinstance(payload, list):
                continue
            schemes = [
                Scheme(
                    scheme_id=item["scheme_id"].strip(),
                    scheme_name=item["scheme_name"].strip(),
                )
                for item in payload
                if isinstance(item, dict)
                and isinstance(item.get("scheme_id"), str)
                and item["scheme_id"].strip()
                and isinstance(item.get("scheme_name"), str)
                and item["scheme_name"].strip()
            ]
            if schemes:
                return schemes
        raise RuntimeError("Playwright did not find AMFI scheme data.")

    def get_amcs(self) -> list[AMC]:
        self._load_page()
        return AMFIDiscovery._parse_amcs(self._page.content())

    def get_schemes(self, amc: AMC) -> list[Scheme]:
        self._load_page()
        payloads = self._response_payloads(lambda: self._select_amc(amc))
        return self._find_schemes(payloads)

    def get_ssd_links(self, amc: AMC, scheme: Scheme) -> SSDLinks:
        self._load_page()
        self._select_amc(amc)
        scheme_field = self._page.get_by_placeholder("Select Scheme Name")
        scheme_field.click()
        self._page.get_by_role("option", name=scheme.scheme_name, exact=True).click()
        go_button = self._page.locator("button", has_text="GO")
        go_button.wait_for(state="visible")
        payloads = self._response_payloads(go_button.click)
        for payload in reversed(payloads):
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                continue
            for document in payload["data"]:
                if isinstance(document, dict) and any(
                    field in document
                    for field in ("summaryXmlUrl", "summaryXlsUrl", "summaryPdfUrl")
                ):
                    return _parse_ssd_document(document)
        raise RuntimeError("Playwright did not find AMFI document data.")


class AMFIDiscovery:
    """Discover AMCs, schemes, and SSD links through AMFI HTTP responses."""

    def __init__(
        self,
        headed: bool = False,
        timeout_ms: int = 30_000,
        *,
        session: requests.Session | None = None,
        fallback: DiscoveryBackend | None = None,
    ):
        self.headed = headed
        self.timeout_ms = timeout_ms
        self.timeout = timeout_ms / 1000
        self._session = session or requests.Session()
        self._owns_session = session is None
        self._fallback = fallback
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/151.0 Safari/537.36"
                ),
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            }
        )

    def __enter__(self) -> "AMFIDiscovery":
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._owns_session:
            self._session.close()
        if self._fallback is not None:
            self._fallback.close()

    def _browser_fallback(self) -> DiscoveryBackend:
        if self._fallback is None:
            self._fallback = PlaywrightDiscovery(
                headed=self.headed,
                timeout_ms=self.timeout_ms,
            )
        return self._fallback

    def _use_fallback(self, operation: str, exc: Exception):
        LOGGER.warning(
            "Direct AMFI %s failed. Starting Playwright fallback: %s",
            operation,
            exc,
        )
        try:
            return self._browser_fallback()
        except Exception as fallback_exc:
            raise RuntimeError(
                f"Direct AMFI {operation} failed: {exc}. "
                f"Playwright fallback failed: {fallback_exc}"
            ) from fallback_exc

    def _get(self, url: str, **kwargs) -> requests.Response:
        try:
            response = self._session.get(url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            raise RuntimeError(f"AMFI request failed for {url}: {exc}") from exc

    def _get_json(self, url: str, **kwargs):
        response = self._get(url, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"AMFI returned invalid JSON for {url}.") from exc

    @staticmethod
    def _extract_mutual_funds(page_html: str) -> list[dict]:
        chunks: list[str] = []
        for match in _NEXT_FLIGHT_CHUNK.finditer(page_html):
            try:
                chunks.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                continue

        page_payload = "".join(chunks)
        marker_index = page_payload.find(_MUTUAL_FUNDS_MARKER)
        if marker_index < 0:
            raise RuntimeError(
                "AMFI Scheme Details page did not contain the Mutual Fund list."
            )

        array_start = marker_index + len(_MUTUAL_FUNDS_MARKER)
        try:
            mutual_funds, _ = json.JSONDecoder().raw_decode(
                page_payload[array_start:].lstrip()
            )
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "AMFI Scheme Details page contained an invalid Mutual Fund list."
            ) from exc

        if not isinstance(mutual_funds, list):
            raise RuntimeError("AMFI Mutual Fund data was not a list.")
        return mutual_funds

    def get_amcs(self) -> list[AMC]:
        try:
            response = self._get(SCHEME_DETAILS_URL)
            return self._parse_amcs(response.text)
        except Exception as exc:
            return self._use_fallback("AMC discovery", exc).get_amcs()

    @classmethod
    def _parse_amcs(cls, page_html: str) -> list[AMC]:
        mutual_funds = cls._extract_mutual_funds(page_html)
        amcs = [
            AMC(amc_id=item["mf_id"].strip(), amc_name=item["mf_name"].strip())
            for item in mutual_funds
            if isinstance(item, dict)
            and isinstance(item.get("mf_id"), str)
            and item["mf_id"].strip()
            and isinstance(item.get("mf_name"), str)
            and item["mf_name"].strip()
        ]
        if not amcs:
            raise RuntimeError("AMFI returned no valid Mutual Fund entries.")
        return amcs

    def get_schemes(self, amc: AMC) -> list[Scheme]:
        try:
            payload = self._get_json(SCHEMES_URL, params={"MF_ID": amc.amc_id})
            if not isinstance(payload, list):
                raise RuntimeError("AMFI scheme data was not a list.")

            return [
                Scheme(
                    scheme_id=item["scheme_id"].strip(),
                    scheme_name=item["scheme_name"].strip(),
                )
                for item in payload
                if isinstance(item, dict)
                and isinstance(item.get("scheme_id"), str)
                and item["scheme_id"].strip()
                and isinstance(item.get("scheme_name"), str)
                and item["scheme_name"].strip()
            ]
        except Exception as exc:
            return self._use_fallback("scheme discovery", exc).get_schemes(amc)

    def get_ssd_links(self, amc: AMC, scheme: Scheme) -> SSDLinks:
        try:
            url = DOCUMENTS_URL.format(scheme_id=scheme.scheme_id)
            payload = self._get_json(url)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise RuntimeError("AMFI document data did not contain a data list.")
            if not payload["data"]:
                return SSDLinks()

            document = payload["data"][0]
            if not isinstance(document, dict):
                raise RuntimeError("AMFI document data contained an invalid entry.")
            return _parse_ssd_document(document)
        except Exception as exc:
            return self._use_fallback("document discovery", exc).get_ssd_links(
                amc, scheme
            )
