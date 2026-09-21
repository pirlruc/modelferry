"""Shared GitLab HTTP calls for registry and feature-flag providers."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote

import httpx

from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import AuthenticationError, DownloadError

_MAX_PAGES = 20
_MAX_REDIRECTS = 20
_ERROR_TEXT_LIMIT = 300
_PAGE_HEADER_LIMIT = 6
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_CREDENTIAL_HEADERS = frozenset(
    {
        "private-token",
        "job-token",
        "authorization",
        "unleash-instanceid",
        "unleash-appname",
    },
)


def project_path(project_id: str) -> str:
    """Percent-encode a GitLab project id or path.

    Args:
        project_id: Numeric id or ``group/project`` path.

    Returns:
        A single URL path segment.
    """
    return quote(project_id, safe="")


def _gitlab_url(base_url: str, path: str) -> httpx.URL:
    """Build a GitLab URL without decoding ``%2F`` inside the project id.

    Args:
        base_url: Registry origin.
        path: Absolute API path, including any percent-encoded slashes.

    Returns:
        A URL whose raw path is exactly ``path``.
    """
    return httpx.URL(base_url).copy_with(raw_path=path.encode("ascii"))


def _error_text(response: httpx.Response) -> str:
    """Extract a short GitLab error message.

    Args:
        response: HTTP response that failed.

    Returns:
        A status line plus the GitLab ``message`` field when one is present.
    """
    detail = _payload_message(response) or response.reason_phrase or "request failed"

    clipped = detail.replace("\n", " ")[:_ERROR_TEXT_LIMIT]
    return f"GitLab HTTP {response.status_code}: {clipped}"


def _payload_message(response: httpx.Response) -> str:
    """Return the GitLab message body, or an empty string.

    Args:
        response: HTTP response that failed.

    Returns:
        The ``message`` or ``error`` field, a JSON string, or ``""``.
    """
    payload = _json_body(response)
    if isinstance(payload, dict):
        return _message_text(payload.get("message") or payload.get("error"))

    if isinstance(payload, str):
        return payload

    return ""


def _json_body(response: httpx.Response) -> Any:
    """Decode a response body, treating non-JSON as missing.

    Args:
        response: HTTP response.

    Returns:
        The decoded JSON value, or ``None``.
    """
    try:
        return response.json()
    except ValueError:
        return None


def _checksum_header(response: httpx.Response, base_url: str) -> str | None:
    """Return ``x-checksum-sha256`` only when the body came from the GitLab origin.

    Object-storage redirects are followed, but a checksum header from another host is
    not a GitLab digest and is ignored.

    Args:
        response: Final download response, after redirects.
        base_url: Configured GitLab origin.

    Returns:
        The header value, or ``None`` when the response host is not GitLab.
    """
    if not _retains_credentials(httpx.URL(base_url), response.url):
        return None

    value = response.headers.get("x-checksum-sha256")
    if not isinstance(value, str) or not value:
        return None

    return value


def _follow_redirects(
    client: httpx.Client,
    url: httpx.URL,
    *,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    stream: bool,
) -> httpx.Response:
    """GET ``url``, dropping GitLab credentials when a redirect leaves the origin.

    Args:
        client: Shared HTTP client. Redirects are handled here, not by the client.
        url: Absolute GitLab URL.
        headers: Request headers, including the access token when one is configured.
        params: Query string for the first request only.
        stream: When true, the final response body is left unread.

    Returns:
        The final response. Redirect hops are closed before it is returned.

    Raises:
        DownloadError: If a redirect has no usable ``Location`` or the hop limit is hit.
        httpx.HTTPError: If the transport fails. Callers map that to ``DownloadError``.
    """
    current = url
    current_headers = dict(headers)
    current_params = params
    for _hop in range(_MAX_REDIRECTS):
        response = _transmit(client, current, current_headers, current_params, stream=stream)
        if response.status_code not in _REDIRECT_STATUSES:
            return response

        current, current_headers = _advance_redirect(response, current, current_headers)
        current_params = None

    raise DownloadError("GitLab redirect limit exceeded")


def _transmit(
    client: httpx.Client,
    url: httpx.URL,
    headers: dict[str, str],
    params: dict[str, Any] | None,
    *,
    stream: bool,
) -> httpx.Response:
    """Send one GET without letting the client follow redirects itself.

    Args:
        client: Shared HTTP client.
        url: Request URL.
        headers: Request headers.
        params: Optional query string.
        stream: When true, leave the body unread.

    Returns:
        The raw response.
    """
    request = client.build_request("GET", url, params=params, headers=headers)
    return client.send(request, stream=stream, follow_redirects=False)


def _advance_redirect(
    response: httpx.Response,
    current: httpx.URL,
    headers: dict[str, str],
) -> tuple[httpx.URL, dict[str, str]]:
    """Close a redirect response and return the next URL and headers.

    Args:
        response: Redirect response. It is read and closed.
        current: URL that produced ``response``.
        headers: Headers used for ``current``.

    Returns:
        The next URL and the headers that may be sent there.

    Raises:
        DownloadError: If ``Location`` is missing or uses a scheme other than HTTP(S).
    """
    location = response.headers.get("location")
    try:
        response.read()
    finally:
        response.close()

    if not location:
        raise DownloadError("GitLab redirect did not include a Location header")

    target = _redirect_target(current, location)
    if _retains_credentials(current, target):
        return target, headers

    return target, _without_credentials(headers)


def _redirect_target(current: httpx.URL, location: str) -> httpx.URL:
    """Resolve a redirect location against ``current``.

    Args:
        current: URL that returned the redirect.
        location: ``Location`` header value.

    Returns:
        An absolute HTTP or HTTPS URL.

    Raises:
        DownloadError: If the target scheme is not HTTP or HTTPS.
    """
    target = current.join(location.strip())
    if target.scheme not in {"http", "https"}:
        raise DownloadError("Refusing a GitLab redirect that is not HTTP(S)")

    return target


def _retains_credentials(current: httpx.URL, target: httpx.URL) -> bool:
    """Return whether GitLab credentials may be sent to ``target``.

    Args:
        current: URL that returned the redirect.
        target: Redirect destination.

    Returns:
        True for the same origin and for an HTTP to HTTPS upgrade of that host.
    """
    if _same_origin(current, target):
        return True

    return _is_https_upgrade(current, target)


def _same_origin(url: httpx.URL, other: httpx.URL) -> bool:
    """Return whether two URLs share scheme, host, and port.

    Args:
        url: First URL.
        other: Second URL.

    Returns:
        True when both URLs are the same origin.
    """
    return (
        url.scheme == other.scheme
        and url.host == other.host
        and _port_or_default(url) == _port_or_default(other)
    )


def _is_https_upgrade(url: httpx.URL, other: httpx.URL) -> bool:
    """Return whether ``other`` is the HTTPS upgrade of ``url``.

    Args:
        url: Request URL.
        other: Redirect destination.

    Returns:
        True for ``http`` port 80 to ``https`` port 443 on the same host.
    """
    if url.host != other.host:
        return False

    return (
        url.scheme == "http"
        and _port_or_default(url) == 80
        and other.scheme == "https"
        and _port_or_default(other) == 443
    )


def _port_or_default(url: httpx.URL) -> int | None:
    """Return the explicit port or the default for the scheme.

    Args:
        url: URL whose port is needed.

    Returns:
        The port number, or ``None`` when the scheme has no default.
    """
    if url.port is not None:
        return url.port

    if url.scheme == "http":
        return 80

    if url.scheme == "https":
        return 443

    return None


def _without_credentials(headers: dict[str, str]) -> dict[str, str]:
    """Drop GitLab and Unleash credentials from redirect headers.

    Args:
        headers: Headers that were sent to the previous hop.

    Returns:
        The same mapping without token or Unleash identity headers.
    """
    return {key: value for key, value in headers.items() if key.lower() not in _CREDENTIAL_HEADERS}


def _next_page(header: str) -> int:
    """Parse a GitLab ``x-next-page`` header.

    Args:
        header: Header value with surrounding whitespace already removed.

    Returns:
        The next page number.

    Raises:
        DownloadError: If the value is not a small positive integer.
    """
    if len(header) > _PAGE_HEADER_LIMIT or not header.isdigit():
        raise DownloadError(f"GitLab returned an invalid x-next-page value: {header!r}")

    page = int(header)
    if page < 1:
        raise DownloadError(f"GitLab returned an invalid x-next-page value: {header!r}")

    return page


def _message_text(message: Any) -> str:
    """Flatten a GitLab ``message`` field.

    Args:
        message: String, list, or another JSON value.

    Returns:
        A single line, or ``""`` when the value is not text.
    """
    if isinstance(message, str):
        return message

    if isinstance(message, list):
        return "; ".join(str(item) for item in message)

    return ""


class GitLabHttp:
    """Authenticated JSON and streaming calls against one GitLab origin."""

    def __init__(self, config: FetcherConfig, client: httpx.Client) -> None:
        """Bind configuration and the shared HTTP client.

        Args:
            config: Token, header name, base URL, and timeout.
            client: Client created by ``ModelFetcher``.
        """
        self._config = config
        self._client = client

    def headers(self, accept: str, *, require_token: bool = True) -> dict[str, str]:
        """Build GitLab authentication headers.

        Args:
            accept: Value of the ``Accept`` header.
            require_token: When true, a missing token is an error. Unleash calls set
                this false because they authenticate with ``UNLEASH-INSTANCEID``.

        Returns:
            Header mapping. Includes ``PRIVATE-TOKEN`` or ``JOB-TOKEN`` when a token
            is configured.

        Raises:
            AuthenticationError: If a token is required and none is configured.
        """
        headers = {"Accept": accept}
        if self._config.token:
            headers[self._config.token_header] = self._config.token
        elif require_token:
            raise AuthenticationError(
                "GitLab token is missing. Pass token= or set GITLAB_TOKEN or CI_JOB_TOKEN.",
            )

        return headers

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        require_token: bool = True,
    ) -> Any | None:
        """GET a JSON document.

        Args:
            path: Absolute API path beginning with ``/api/``.
            params: Optional query string.
            extra_headers: Headers merged over the authentication headers.
            require_token: When false, the call may proceed with ``extra_headers`` only.

        Returns:
            The decoded JSON value, or ``None`` when GitLab responds with 404.

        Raises:
            AuthenticationError: On HTTP 401 or 403.
            DownloadError: On transport failures or other HTTP errors.
        """
        response = self._send(
            path,
            params=params,
            extra_headers=extra_headers,
            require_token=require_token,
        )
        if response.status_code == 404:
            return None

        self._raise_for_status(response)
        return self._decode_json(response)

    def get_pages(self, path: str, *, params: dict[str, Any] | None = None) -> list[Any] | None:
        """GET a paginated JSON list.

        Args:
            path: Absolute API path beginning with ``/api/``.
            params: Query string merged with page controls.

        Returns:
            Combined page items, or ``None`` when the first page is 404.

        Raises:
            AuthenticationError: On HTTP 401 or 403.
            DownloadError: On transport failures, other HTTP errors, a non-list body,
                an invalid ``x-next-page`` header, or more than 20 pages.
        """
        collected: list[Any] = []
        page = 1
        for _ in range(_MAX_PAGES):
            query: dict[str, Any] = dict(params or {})
            query["per_page"] = 100
            query["page"] = page
            response = self._send(path, params=query)
            if response.status_code == 404:
                return None if page == 1 else collected

            self._raise_for_status(response)
            payload = self._decode_json(response)
            if not isinstance(payload, list):
                raise DownloadError(f"Expected a JSON list from {path}")

            collected.extend(payload)
            next_page = response.headers.get("x-next-page", "").strip()
            if not next_page:
                return collected

            page = _next_page(next_page)

        raise DownloadError(f"GitLab pagination exceeded {_MAX_PAGES} pages for {path}")

    @contextmanager
    def open_download(self, path: str) -> Iterator[httpx.Response]:
        """Open a file download, mapping 404 to a sentinel status for the caller.

        Args:
            path: Absolute API path of the file.

        Yields:
            The streaming response. Status 404 is yielded so the registry can fall
            back from the model registry to the generic package registry.

        Raises:
            AuthenticationError: On HTTP 401 or 403.
            DownloadError: On transport failures or HTTP statuses other than 200 and 404.
        """
        response = self._send(path, stream=True, accept="application/octet-stream")
        try:
            if response.status_code in {401, 403}:
                response.read()
                raise AuthenticationError(_error_text(response))

            if response.status_code == 404:
                response.read()
            elif response.status_code >= 400:
                response.read()
                raise DownloadError(_error_text(response))

            yield response
        except httpx.HTTPError as exc:
            raise DownloadError(f"GitLab download failed for {path}: {exc}") from exc
        finally:
            response.close()

    def _send(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        require_token: bool = True,
        stream: bool = False,
        accept: str = "application/json",
    ) -> httpx.Response:
        """Send one GET and map transport errors.

        Redirects are followed here. GitLab credentials are removed when the next hop
        is a different origin, so a package redirect cannot leak ``PRIVATE-TOKEN`` or
        ``JOB-TOKEN`` to object storage.

        Args:
            path: Absolute API path.
            params: Optional query string.
            extra_headers: Headers merged over the authentication headers.
            require_token: When false, a missing access token is allowed.
            stream: When true, leave the final body unread.
            accept: Value of the ``Accept`` header.

        Returns:
            The raw response. HTTP status is not yet classified beyond transport.

        Raises:
            AuthenticationError: When a token is required and missing. Status codes
                are left to the caller via :meth:`_raise_for_status` after a 404 check.
            DownloadError: When httpx cannot complete the request, or a redirect is
                refused.
        """
        headers = self.headers(accept, require_token=require_token)
        if extra_headers:
            headers.update(extra_headers)

        url = _gitlab_url(self._config.base_url, path)
        try:
            return _follow_redirects(
                self._client,
                url,
                headers=headers,
                params=params,
                stream=stream,
            )
        except httpx.HTTPError as exc:
            raise DownloadError(f"GitLab request failed for {path}: {exc}") from exc

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise the library error that matches an HTTP status.

        Args:
            response: Completed response that is not a 404.

        Raises:
            AuthenticationError: On HTTP 401 or 403.
            DownloadError: On any other status of 400 or higher.
        """
        if response.status_code in {401, 403}:
            raise AuthenticationError(_error_text(response))

        if response.status_code >= 400:
            raise DownloadError(_error_text(response))

    def _decode_json(self, response: httpx.Response) -> Any:
        """Decode a JSON body.

        Args:
            response: Successful response.

        Returns:
            The decoded JSON value.

        Raises:
            DownloadError: If the body is not JSON.
        """
        try:
            return response.json()
        except ValueError as exc:
            raise DownloadError("GitLab returned a non-JSON response") from exc
