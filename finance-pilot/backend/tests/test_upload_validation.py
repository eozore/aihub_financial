"""Tests for upload validation logic."""
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_rejects_non_csv_file():
    from upload_validation import validate_and_read_upload

    file = MagicMock()
    file.filename = "data.xlsx"
    file.content_type = "application/vnd.ms-excel"

    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(file)
    assert exc_info.value.status_code == 400
    assert "CSV" in exc_info.value.detail


@pytest.mark.asyncio
async def test_rejects_empty_file():
    from upload_validation import validate_and_read_upload

    file = MagicMock()
    file.filename = "data.csv"
    file.content_type = "text/csv"
    file.read = AsyncMock(return_value=b"")

    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(file)
    assert exc_info.value.status_code == 400
    assert "empty" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_rejects_oversized_file():
    from upload_validation import validate_and_read_upload, MAX_UPLOAD_SIZE_BYTES

    file = MagicMock()
    file.filename = "data.csv"
    file.content_type = "text/csv"
    file.read = AsyncMock(return_value=b"x" * (MAX_UPLOAD_SIZE_BYTES + 1))

    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(file)
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_accepts_valid_csv():
    from upload_validation import validate_and_read_upload

    csv_content = b"date,amount,title\n2025-01-01,100,Test"
    file = MagicMock()
    file.filename = "data.csv"
    file.content_type = "text/csv"
    file.read = AsyncMock(return_value=csv_content)

    result = await validate_and_read_upload(file)
    assert result == csv_content
