"""GitHub REST calls for release assets and flag documents."""

from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

import httpx

from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import (
    AuthenticationError,
    DownloadError,
    ModelNotFoundError,
)

_API_VERSION = "2022-11-28"
_MAX_REDIRECTS = 5
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def api_headers(config: FetcherConfig, *, download: bool = False) -> dict[str, str]:
    """Return GitHub REST headers, including a bearer token when one is set.

    Args:
        config: Resolved host and token.
        download: When true, ask for the asset bytes instead of JSON.

    Returns:
        Headers safe to send to the configured host.
    """
    headers = {
        "Accept": "application/octet-stream"
        if download
        else "application/vnd.github+json",
        "User-Agent": "model-fetcher",
        "X-GitHub-Api-Version": _API_VERSION,
    }
    if config.token:
        headers["Authorization"] = f"Bearer {config.token}"
    return headers


def _redirect_target(current: str, location: str | None) -> str:
    """Resolve a redirect and refuse a non-HTTP scheme.

    Args:
        current: URL that returned the redirect.
        location: Location header value.

    Returns:
        The absolute next URL.

    Raises:
        DownloadError: When Location is missing or not HTTP(S).
    """
    if not location:
        raise DownloadError("GitHub redirect did not include a Location header")
    target = str(httpx.URL(current).join(location.strip()))
    if urlsplit(target).scheme not in {"http", "https"}:
        raise DownloadError("Refusing a GitHub redirect that is not HTTP(S)")
    return target


def _headers_for_target(
    config: FetcherConfig, headers: dict[str, str], target: str
) -> dict[str, str]:
    """Keep the bearer token on the API host only.

    Args:
        config: Resolved API host.
        headers: Headers from the previous hop.
        target: Next URL.

    Returns:
        Headers safe to send to ``target``.

    Raises:
        DownloadError: When a non-HTTPS redirect leaves the API host.
    """
    if urlsplit(target).scheme != "https" and not same_host(config, target):
        raise DownloadError("Refusing a GitHub redirect that is not HTTPS")
    if same_host(config, target):
        return headers
    return {
        key: value for key, value in headers.items() if key.lower() != "authorization"
    }


def same_host(config: FetcherConfig, url: str) -> bool:
    """Return whether ``url`` stays on the configured API host.

    Args:
        config: Resolved base URL.
        url: Absolute URL about to be requested.

    Returns:
        True when both URLs share a hostname.
    """
    configured = (urlsplit(config.base_url).hostname or "").lower()
    target = (urlsplit(url).hostname or "").lower()
    return bool(configured) and configured == target


class GitHubHttp:
    """Small GitHub REST client that refuses to send a token off-host."""

    def __init__(self, config: FetcherConfig, client: httpx.Client) -> None:
        """Store the shared client.

        Args:
            config: Resolved GitHub settings.
            client: HTTP client owned by ``ModelFetcher``.
        """
        self._config = config
        self._client = client

    def get_json(self, path: str) -> dict[str, Any]:
        """GET one JSON document under the API base URL.

        Args:
            path: Absolute path beginning with ``/``.

        Returns:
            The JSON object.

        Raises:
            AuthenticationError: On HTTP 401 or 403.
            ModelNotFoundError: On HTTP 404.
            DownloadError: On any other failure or a non-object body.
        """
        response = self._send("GET", path, download=False)
        payload = response.json()
        if not isinstance(payload, dict):
            raise DownloadError(f"GitHub response for {path} was not an object")
        return payload

    def get_raw_json(self, path: str) -> dict[str, Any]:
        """GET a repository file as JSON via the raw media type.

        Args:
            path: Absolute contents API path.

        Returns:
            The file parsed as a JSON object.

        Raises:
            DownloadError: If the body is not a JSON object.
        """
        headers = api_headers(self._config)
        headers["Accept"] = "application/vnd.github.raw+json"
        url = f"{self._config.base_url}{path}"
        response = self._client.request(
            "GET", url, headers=headers, follow_redirects=False
        )
        self._raise_for_status(response, path)
        payload = response.json()
        if not isinstance(payload, dict):
            raise DownloadError(f"GitHub file {path} was not a JSON object")
        return payload

    def stream(self, url: str) -> Iterator[bytes]:
        """Stream an asset URL that stays on the API host.

        Args:
            url: Asset API URL from the release document.

        Yields:
            Body chunks.

        Raises:
            DownloadError: If the URL leaves the API host.
        """
        if not same_host(self._config, url):
            raise DownloadError("Refusing to send the GitHub token to another host")
        headers = api_headers(self._config, download=True)
        current = url
        for _hop in range(_MAX_REDIRECTS + 1):
            response = self._open(current, headers)
            if response.status_code not in _REDIRECT_STATUSES:
                try:
                    self._raise_for_status(response, current)
                    yield from response.iter_bytes()
                finally:
                    response.close()
                return
            current, headers = self._follow(response, current, headers)
        raise DownloadError("GitHub redirect limit exceeded")

    def _open(self, url: str, headers: dict[str, str]) -> httpx.Response:
        """Send one streamed GET.

        Args:
            url: Absolute URL.
            headers: Headers for this hop.

        Returns:
            The streamed response. The caller closes it.
        """
        request = self._client.build_request("GET", url, headers=headers)
        return self._client.send(request, stream=True, follow_redirects=False)

    def _follow(
        self,
        response: httpx.Response,
        current: str,
        headers: dict[str, str],
    ) -> tuple[str, dict[str, str]]:
        """Resolve one redirect and drop the token when the host changes.

        Args:
            response: Redirect response.
            current: URL that produced the redirect.
            headers: Headers used for that hop.

        Returns:
            The next URL and the headers safe to send there.
        """
        location = response.headers.get("location")
        try:
            response.read()
        finally:
            response.close()
        target = _redirect_target(current, location)
        return target, _headers_for_target(self._config, headers, target)

    def _send(self, method: str, path: str, *, download: bool) -> httpx.Response:
        """Send one request and map the status to a library error.

        Args:
            method: HTTP method.
            path: Absolute API path.
            download: Select the asset Accept header.

        Returns:
            The successful response.
        """
        url = f"{self._config.base_url}{path}"
        response = self._client.request(
            method,
            url,
            headers=api_headers(self._config, download=download),
            follow_redirects=False,
        )
        self._raise_for_status(response, path)
        return response

    @staticmethod
    def _raise_for_status(response: httpx.Response, label: str) -> None:
        """Map a GitHub status onto a library error.

        Args:
            response: Completed response.
            label: Path or URL used in the message.

        Raises:
            AuthenticationError: On HTTP 401 or 403.
            ModelNotFoundError: On HTTP 404.
            DownloadError: On any other non-success status.
        """
        if response.status_code in {401, 403}:
            raise AuthenticationError(f"GitHub rejected credentials for {label}")
        if response.status_code == 404:
            raise ModelNotFoundError(f"GitHub resource {label} was not found")
        if response.status_code >= 400:
            raise DownloadError(
                f"GitHub request for {label} failed with {response.status_code}"
            )
