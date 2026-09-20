"""HTTP access with retries/backoff, checksum-verified downloads and error mapping.

All connectors go through :class:`HttpClient` so that transient failures are
retried uniformly and every failure surfaces as a domain exception.
"""

from __future__ import annotations

import hashlib
import ssl
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .config import Settings, get_settings
from .exceptions import AuthenticationError, DatasetUnavailableError, HTTPError, NetworkError
from .logging import get_logger

log = get_logger("http")

_RETRY_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_SENSITIVE_PARAMS = {"api_key", "key", "registrationkey", "userid", "token"}


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def redact_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return params safe for logs/manifests (credentials masked)."""
    if not params:
        return {}
    return {k: ("***" if k.lower() in _SENSITIVE_PARAMS else v) for k, v in params.items()}


def redact_url(url: str) -> str:
    """Mask credential-bearing query parameters in a URL."""
    if "?" not in url:
        return url
    base, _, query = url.partition("?")
    parts = []
    for item in query.split("&"):
        key, eq, _val = item.partition("=")
        if key.lower() in _SENSITIVE_PARAMS and eq:
            parts.append(f"{key}=***")
        else:
            parts.append(item)
    return base + "?" + "&".join(parts)


def _ssl_context(settings: Settings) -> ssl.SSLContext | bool:
    """Verify TLS against the operating-system trust store (like pip/uv) so that
    corporate proxies with private roots work; fall back to certifi."""
    if not settings.ssl_verify:
        return False
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001 - truststore optional
        return True


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    url: str  # final URL after redirects, credentials redacted
    requested_url: str
    status_code: int
    sha256: str
    size_bytes: int
    content_type: str | None


class HttpClient:
    """Thin wrapper over httpx with exponential backoff.

    ``sleep`` is injectable so tests can run without waiting.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ):
        self.settings = settings or get_settings()
        self._sleep = sleep
        self._client = httpx.Client(
            timeout=self.settings.http_timeout,
            follow_redirects=True,
            headers={"User-Agent": self.settings.user_agent, "Accept": "*/*"},
            verify=_ssl_context(self.settings),
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ core
    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
        data: Any = None,
    ) -> httpx.Response:
        attempts = self.settings.http_retries + 1
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                resp = self._client.request(
                    method, url, params=params, json=json, headers=headers, data=data
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                log.warning(
                    "http transient failure",
                    extra={"url": redact_url(url), "attempt": attempt, "error": type(exc).__name__},
                )
            else:
                if resp.status_code in _RETRY_STATUSES and attempt < attempts:
                    log.warning(
                        "http retryable status",
                        extra={
                            "url": redact_url(url),
                            "status": resp.status_code,
                            "attempt": attempt,
                        },
                    )
                    self._backoff(attempt, resp.headers.get("Retry-After"))
                    continue
                self._raise_for_status(resp, url)
                return resp
            if attempt < attempts:
                self._backoff(attempt, None)
        raise NetworkError(
            f"request to {redact_url(url)} failed after {attempts} attempts: {last_exc}"
        )

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post_json(self, url: str, payload: Any, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, json=payload, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.get(url, **kwargs).json()

    def download(
        self,
        url: str,
        dest: Path,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        method: str = "GET",
        json: Any = None,
    ) -> DownloadResult:
        """Stream ``url`` into ``dest`` (written atomically) and return its checksum."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_name(dest.name + ".part")
        attempts = self.settings.http_retries + 1
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with self._client.stream(
                    method, url, params=params, headers=headers, json=json
                ) as resp:
                    if resp.status_code in _RETRY_STATUSES and attempt < attempts:
                        log.warning(
                            "download retryable status",
                            extra={
                                "url": redact_url(url),
                                "status": resp.status_code,
                                "attempt": attempt,
                            },
                        )
                        self._backoff(attempt, resp.headers.get("Retry-After"))
                        continue
                    self._raise_for_status(resp, url)
                    size = 0
                    with tmp.open("wb") as fh:
                        for chunk in resp.iter_bytes(1 << 20):
                            fh.write(chunk)
                            size += len(chunk)
                    tmp.replace(dest)
                    return DownloadResult(
                        path=dest,
                        url=redact_url(str(resp.url)),
                        requested_url=redact_url(url),
                        status_code=resp.status_code,
                        sha256=sha256_of_file(dest),
                        size_bytes=size,
                        content_type=resp.headers.get("Content-Type"),
                    )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                log.warning(
                    "download transient failure",
                    extra={"url": redact_url(url), "attempt": attempt, "error": type(exc).__name__},
                )
                if attempt < attempts:
                    self._backoff(attempt, None)
            finally:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
        raise NetworkError(
            f"download of {redact_url(url)} failed after {attempts} attempts: {last_exc}"
        )

    # --------------------------------------------------------------- helpers
    def _backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = self.settings.http_backoff_seconds * (2 ** (attempt - 1))
        if retry_after:
            try:
                delay = max(delay, float(retry_after))
            except ValueError:
                pass
        self._sleep(min(delay, 60.0))

    @staticmethod
    def _raise_for_status(resp: httpx.Response, url: str) -> None:
        code = resp.status_code
        if code < 400:
            return
        safe = redact_url(url)
        if code in (401, 403):
            raise AuthenticationError(
                f"authentication/authorization failed ({code}) for {safe}",
                status_code=code,
                url=safe,
            )
        if code == 404:
            raise DatasetUnavailableError(f"resource not found (404): {safe}")
        raise HTTPError(f"unexpected HTTP status {code} for {safe}", status_code=code, url=safe)
