"""Shared GitLab HTTP calls for registry and feature-flag providers."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote

import httpx

from model_fetcher.config import FetcherConfig
from model_fetcher.exceptions import AuthenticationError, DownloadError

_MAX_PAGES = 20
_ERROR_TEXT_LIMIT = 300


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
    detail = ""
    try:
        payload = response.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if isinstance(message, str):
            detail = message
        elif isinstance(message, list):
            detail = "; ".join(str(item) for item in message)
    elif isinstance(payload, str):
        detail = payload

    if not detail:
        detail = response.reason_phrase or "request failed"

    clipped = detail.replace("\n", " ")[:_ERROR_TEXT_LIMIT]
    return f"GitLab HTTP {response.status_code}: {clipped}"


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
            DownloadError: On transport failures, other HTTP errors, or a non-list body.
        """
        collected: list[Any] = []
        page = 1
        while page <= _MAX_PAGES:
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

            page = int(next_page)

        return collected

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
        url = _gitlab_url(self._config.base_url, path)
        try:
            with self._client.stream(
                "GET",
                url,
                headers=self.headers("application/octet-stream"),
            ) as response:
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

    def _send(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        require_token: bool = True,
    ) -> httpx.Response:
        """Send one GET and map transport errors.

        Args:
            path: Absolute API path.
            params: Optional query string.
            extra_headers: Headers merged over the authentication headers.
            require_token: When false, a missing access token is allowed.

        Returns:
            The raw response. HTTP status is not yet classified beyond transport.

        Raises:
            AuthenticationError: When a token is required and missing. Status codes
                are left to the caller via :meth:`_raise_for_status` after a 404 check.
            DownloadError: When httpx cannot complete the request.
        """
        headers = self.headers("application/json", require_token=require_token)
        if extra_headers:
            headers.update(extra_headers)

        url = _gitlab_url(self._config.base_url, path)
        try:
            return self._client.get(url, params=params, headers=headers)
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
