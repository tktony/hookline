"""Tests for the SSRF guard (is_safe_url)."""

from unittest.mock import patch

import pytest

from app.worker import is_safe_url


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "192.168.1.1",  # private
        "172.16.0.1",  # private
        "169.254.169.254",  # link-local (cloud metadata)
        "0.0.0.0",  # unspecified
    ],
)
def test_rejects_internal_addresses(ip):
    """URLs resolving to internal/private addresses are rejected."""
    with patch("app.worker.socket.gethostbyname", return_value=ip):
        assert is_safe_url("http://anything.com/") is False


@pytest.mark.parametrize(
    "ip",
    [
        "8.8.8.8",  # public DNS
        "93.184.216.34",  # public
    ],
)
def test_allows_public_addresses(ip):
    """URLs resolving to public addresses are allowed."""
    with patch("app.worker.socket.gethostbyname", return_value=ip):
        assert is_safe_url("http://anything.com/") is True


def test_rejects_unresolvable_host():
    """A hostname that fails to resolve is rejected (fail closed)."""
    import socket

    with patch("app.worker.socket.gethostbyname", side_effect=socket.gaierror):
        assert is_safe_url("http://nonexistent.invalid/") is False
