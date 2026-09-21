"""HTTP fixtures for GitLab provider tests."""

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class Route:
    """One scripted GitLab response."""

    status: int = 200
    json_body: Any = None
    content: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


class GitLabMock:
    """Path-addressed GitLab API stand-in backed by ``httpx.MockTransport``."""

    def __init__(self) -> None:
        """Create an empty route table."""
        self.routes: dict[tuple[str, str], Route] = {}
        self.calls: list[httpx.Request] = []

    def add(
        self,
        method: str,
        path: str,
        *,
        status: int = 200,
        json_body: Any = None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        """Register a response for an exact method and path.

        Args:
            method: HTTP method.
            path: URL path, percent-encoded the way GitLab receives it.
            status: HTTP status code.
            json_body: JSON payload. When set, it takes precedence over ``content``.
            content: Raw file bytes.
            headers: Extra response headers.
        """
        self.routes[(method.upper(), path)] = Route(
            status=status,
            json_body=json_body,
            content=content,
            headers=dict(headers or {}),
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Answer one request from the route table.

        Args:
            request: Outbound request captured by httpx.

        Returns:
            The scripted response, or a JSON 404 when the path is unknown.
        """
        self.calls.append(request)
        path = request.url.raw_path.decode("ascii").split("?", maxsplit=1)[0]
        route = self.routes.get((request.method.upper(), path))
        if route is None:
            return httpx.Response(404, json={"message": f"no route for {path}"})

        if route.json_body is not None:
            return httpx.Response(route.status, json=route.json_body, headers=route.headers)

        return httpx.Response(route.status, content=route.content, headers=route.headers)

    def client(self) -> httpx.Client:
        """Build a client that never touches the network.

        Returns:
            An httpx client using this mock as its transport.
        """
        return httpx.Client(transport=httpx.MockTransport(self.handler))

    def paths(self) -> list[str]:
        """Return the paths requested so far, in order.

        Returns:
            URL paths without query strings.
        """
        return [call.url.raw_path.decode("ascii").split("?", maxsplit=1)[0] for call in self.calls]

    def header(self, call_index: int, name: str) -> str | None:
        """Return one request header.

        Args:
            call_index: Index into :attr:`calls`.
            name: Header name. Lookup is case-insensitive.

        Returns:
            The header value, or ``None`` when it was not sent.
        """
        value = self.calls[call_index].headers.get(name)
        if isinstance(value, str):
            return value

        return None
