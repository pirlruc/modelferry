"""Redirect rules shared by the GitHub and GitLab HTTP clients."""

from model_fetcher.exceptions import DownloadError

MAX_REDIRECTS = 5


def require_https_off_host(
    current_host: str,
    target_scheme: str,
    target_host: str,
    provider: str,
) -> None:
    """Refuse a cleartext redirect that leaves the current host.

    Args:
        current_host: Host that returned the redirect.
        target_scheme: Scheme of the next URL.
        target_host: Host of the next URL.
        provider: Name used in the error.

    Raises:
        DownloadError: When the next hop is not HTTPS and not the same host.
    """
    if target_scheme == "https":
        return
    if current_host and current_host.lower() == (target_host or "").lower():
        return
    raise DownloadError(f"Refusing a {provider} redirect that is not HTTPS")
