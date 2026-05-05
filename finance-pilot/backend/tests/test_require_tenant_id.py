"""Tests for the require_tenant_id guard function (Task 3.2).

Validates Requirement 1.2: queries without tenant_id are rejected with HTTP 400.
"""
import pytest
from fastapi import HTTPException

from auth import require_tenant_id
from models import TenantContext


class TestRequireTenantIdGuard:
    """Unit tests for the require_tenant_id guard."""

    def test_valid_tenant_id_returns_id(self):
        tenant = TenantContext(tenant_id="ws-abc123", user_id="u1")
        result = require_tenant_id(tenant)
        assert result == "ws-abc123"

    def test_valid_tenant_id_with_dots_and_dashes(self):
        tenant = TenantContext(tenant_id="ws-u-a1b2c3d4e5f6", user_id="u1")
        result = require_tenant_id(tenant)
        assert result == "ws-u-a1b2c3d4e5f6"

    def test_empty_tenant_id_raises_400(self):
        tenant = TenantContext(tenant_id="", user_id="u1")
        with pytest.raises(HTTPException) as exc_info:
            require_tenant_id(tenant)
        assert exc_info.value.status_code == 400
        assert "tenant_id is required" in exc_info.value.detail

    def test_whitespace_tenant_id_raises_400(self):
        tenant = TenantContext(tenant_id="   ", user_id="u1")
        with pytest.raises(HTTPException) as exc_info:
            require_tenant_id(tenant)
        assert exc_info.value.status_code == 400

    def test_default_tenant_id_is_allowed(self):
        """'default' is a valid workspace id used by legacy workspaces."""
        tenant = TenantContext(tenant_id="default", user_id="u1")
        result = require_tenant_id(tenant)
        assert result == "default"

    def test_valid_tenant_without_user_id(self):
        """Guard only checks tenant_id, not authentication."""
        tenant = TenantContext(tenant_id="ws-public", user_id=None)
        result = require_tenant_id(tenant)
        assert result == "ws-public"

    def test_returns_tenant_id_for_convenience(self):
        """The return value should be the tenant_id string for direct use."""
        tenant = TenantContext(tenant_id="my-workspace", user_id="u1")
        tid = require_tenant_id(tenant)
        assert isinstance(tid, str)
        assert tid == "my-workspace"
