from __future__ import annotations

from pathlib import Path
import logging
import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import DownloadResult
from .validation import validate_file


LOGGER = logging.getLogger(__name__)


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0 Safari/537.36"
            ),
            "Accept": "*/*",
        }
    )

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def download_file(
    session: requests.Session,
    url: str | None,
    output_path: Path,
    kind: str,
    force: bool = False,
    timeout: int = 60,
) -> DownloadResult:
    if not url:
        return DownloadResult(status="MISSING")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    part_path = output_path.with_name(output_path.name + ".part")
    if part_path.exists():
        part_path.unlink()

    try:
        LOGGER.info("Checking URL for %s: %s", output_path.name, url)
        with session.get(url, stream=True, timeout=timeout, allow_redirects=True) as response:
            if response.status_code != 200:
                return DownloadResult(
                    status="FAILED",
                    error=f"HTTP {response.status_code}",
                )

            if output_path.exists() and not force:
                valid, error = validate_file(output_path, kind)
                if valid:
                    return DownloadResult(
                        status="SKIPPED_EXISTING",
                        path=str(output_path),
                    )
                LOGGER.warning(
                    "Existing invalid file will be replaced: %s (%s)",
                    output_path,
                    error,
                )

            with part_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)

        valid, error = validate_file(part_path, kind)
        if not valid:
            part_path.unlink(missing_ok=True)
            return DownloadResult(status="FAILED", error=error)

        if output_path.exists():
            output_path.unlink()
        os.replace(part_path, output_path)

        return DownloadResult(
            status="DOWNLOADED",
            path=str(output_path),
        )

    except KeyboardInterrupt:
        part_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        part_path.unlink(missing_ok=True)
        return DownloadResult(
            status="FAILED",
            error=f"{type(exc).__name__}: {exc}",
        )
