import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_module(monkeypatch):
    """Import a fresh backend.server module per test, with a mocked endpoint."""
    monkeypatch.setenv("DOINGS_ENDPOINT", "https://example.test/stt")
    import importlib
    import backend.server
    importlib.reload(backend.server)
    return backend.server


@pytest.fixture
def client(app_module):
    with TestClient(app_module.app) as c:
        yield c
