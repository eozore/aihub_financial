"""Tests for upload validation logic."""
import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock


@pytest.mark.asyncio
async def test_rejects_non_csv_non_pdf_file():
    from upload_validation import validate_and_read_upload

    file = MagicMock()
    file.filename = "data.xlsx"
    file.content_type = "application/vnd.ms-excel"

    with pytest.raises(HTTPException) as exc_info:
        await validate_and_read_upload(file)
    assert exc_info.value.status_code == 400
    assert "PDF and CSV" in exc_info.value.detail


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


@pytest.mark.asyncio
async def test_accepts_valid_pdf():
    from upload_validation import validate_and_read_upload

    pdf_content = b"%PDF-1.4 fake pdf content"
    file = MagicMock()
    file.filename = "fatura.pdf"
    file.content_type = "application/pdf"
    file.read = AsyncMock(return_value=pdf_content)

    result = await validate_and_read_upload(file)
    assert result == pdf_content


@pytest.mark.asyncio
async def test_accepts_pdf_with_octet_stream():
    """PDF uploaded with generic content type should still be accepted."""
    from upload_validation import validate_and_read_upload

    pdf_content = b"%PDF-1.4 fake pdf content"
    file = MagicMock()
    file.filename = "fatura.pdf"
    file.content_type = "application/octet-stream"
    file.read = AsyncMock(return_value=pdf_content)

    result = await validate_and_read_upload(file)
    assert result == pdf_content


def test_detect_file_type_pdf():
    from upload_validation import detect_file_type

    assert detect_file_type("fatura.pdf") == "pdf"
    assert detect_file_type("FATURA.PDF") == "pdf"


def test_detect_file_type_csv():
    from upload_validation import detect_file_type

    assert detect_file_type("data.csv") == "csv"
    assert detect_file_type("DATA.CSV") == "csv"
