"""Shared test fixtures for the backend test suite."""
import os
import pytest

# Force SQLite mode for tests
os.environ["USE_SQLITE"] = "true"
os.environ["USE_MOCK_DATA"] = "false"
os.environ["REQUIRE_AUTH_FOR_DATA"] = "false"
os.environ["TENANT_REQUIRED"] = "false"
os.environ["PROJECT_ID"] = "test-project"

from fastapi.testclient import TestClient
from main import app


@pytest.fixture()
def client():
    """FastAPI test client with SQLite backend."""
    return TestClient(app)


@pytest.fixture()
def auth_headers():
    """Headers simulating an authenticated request (no real Firebase token)."""
    return {"X-Tenant-ID": "test-tenant"}
