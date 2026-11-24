"""Fuzz cache_segment. A bad path must raise DownloadError and nothing else."""

import sys

import atheris

with atheris.instrument_imports():
    from model_fetcher.cache import cache_segment
    from model_fetcher.exceptions import DownloadError


def test_one_input(data: bytes) -> None:
    """Feed one unicode string into the cache path encoder.

    Args:
        data: Raw fuzzer input.
    """
    provider = atheris.FuzzedDataProvider(data)
    text = provider.ConsumeUnicodeNoSurrogates(200)
    try:
        cache_segment(text)
    except DownloadError:
        return


def main() -> None:
    """Start the atheris loop."""
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
