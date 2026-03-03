"""Tests for core API endpoints."""
import pytest


class TestHealthCheck:
    def test_root_returns_status(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] == "Finance API is running"

    def test_root_returns_mode(self, client):
        response = client.get("/")
        data = response.json()
        assert "mode" in data
        assert data["mode"] in ("sqlite", "mock", "bigquery")


class TestTransactions:
    def test_get_transactions_requires_start_param(self, client, auth_headers):
        response = client.get("/transactions", headers=auth_headers)
        assert response.status_code == 422

    def test_get_transactions_returns_paginated(self, client, auth_headers):
        response = client.get(
            "/transactions?start=2025-01&end=2025-01",
            headers=auth_headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "total" in body
        assert isinstance(body["data"], list)

    def test_create_transaction(self, client, auth_headers):
        payload = {
            "date": "2025-06-15",
            "amount": 42.50,
            "merchant_clean": "Test Store",
            "category": "Mercado",
            "owner": "Victor",
            "type": "Shared",
        }
        response = client.post("/transactions", json=payload, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert "id" in data
