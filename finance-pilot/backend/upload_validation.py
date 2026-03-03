"""Shared upload validation for all CSV upload endpoints."""
import os

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))
ALLOWED_CSV_MIME_TYPES = {"text/csv", "application/vnd.ms-excel", "application/octet-stream"}


async def validate_and_read_upload(file: UploadFile, label: str = "file") -> bytes:
    """Validate uploaded file size, extension and MIME type, then return contents."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    if file.content_type and file.content_type not in ALLOWED_CSV_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type '{file.content_type}'. Expected CSV.",
        )
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB",
        )
    return contents
