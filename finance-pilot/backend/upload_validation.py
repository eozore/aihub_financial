"""Shared upload validation for PDF and CSV upload endpoints."""
import os

from fastapi import HTTPException, UploadFile

MAX_UPLOAD_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(10 * 1024 * 1024)))

ALLOWED_CSV_MIME_TYPES = {"text/csv", "application/vnd.ms-excel", "application/octet-stream"}
ALLOWED_PDF_MIME_TYPES = {"application/pdf"}
ALLOWED_MIME_TYPES = ALLOWED_CSV_MIME_TYPES | ALLOWED_PDF_MIME_TYPES
ALLOWED_EXTENSIONS = {".csv", ".pdf"}


async def validate_and_read_upload(file: UploadFile, label: str = "file") -> bytes:
    """Validate uploaded file size, extension and MIME type, then return contents.

    Accepts both CSV and PDF files.  Keeps the 10 MB size limit.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = _get_extension(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and CSV files are allowed",
        )

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid content type '{file.content_type}'. Expected PDF or CSV.",
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


def detect_file_type(filename: str) -> str:
    """Return ``'pdf'`` or ``'csv'`` based on the file extension."""
    ext = _get_extension(filename)
    if ext == ".pdf":
        return "pdf"
    return "csv"


def _get_extension(filename: str) -> str:
    """Return the lowercased file extension including the dot."""
    return ("." + filename.rsplit(".", 1)[-1]).lower() if "." in filename else ""
