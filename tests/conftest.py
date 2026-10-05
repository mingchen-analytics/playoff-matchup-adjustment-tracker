"""Normal CI must never make live NBA/network requests."""

import pytest
import requests


@pytest.fixture(autouse=True)
def block_live_http(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Normal tests must use fixtures/caches, not live HTTP.")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
