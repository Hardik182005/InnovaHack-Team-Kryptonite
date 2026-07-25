"""Secure upload — §18 ``POST /api/uploads/presign``, §22.

The MVP stores bytes in the document repository rather than S3, but the API
shape is the one S3 presigning uses: request a grant, PUT to the returned URL,
then reference the upload when creating the analysis. Swapping in a real
presigned S3 URL therefore changes this module only.

Every §22 upload control is enforced here:

* extension and content-type allowlists;
* a hard byte ceiling, checked against the *actual* body, not the declared size;
* zero-byte rejection;
* filename sanitisation — a path is never used as, or joined to, a storage key;
* magic-byte sniffing, so ``statement.csv`` containing a PDF (or a ZIP, or an
  executable) is rejected rather than parsed;
* randomized object keys, so the storage key never reveals a filename;
* a short expiry on the grant.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, File, Request, UploadFile, status

from ..config import Settings, get_logger
from ..dependencies import (
    ApiError,
    bad_request,
    get_repositories,
    get_session,
    get_settings,
    not_found,
    parse_uuid,
)
from ..models.entities import UploadedDocument, UploadTicket, User, random_object_key, utc_now
from ..repositories.base import Repositories
from .schemas import PresignRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

#: Leading bytes that identify a container format. Used to catch a file whose
#: extension disagrees with its content (§22 file allowlist).
_MAGIC = (
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "zip"),
    (b"\xd0\xcf\x11\xe0", "ole"),
    (b"\x7fELF", "binary"),
    (b"MZ", "binary"),
    (b"\x89PNG", "image"),
    (b"\xff\xd8\xff", "image"),
    (b"\x1f\x8b", "binary"),
)

#: Which sniffed kinds each extension may legitimately contain.
_ALLOWED_KINDS = {
    ".pdf": {"pdf"},
    ".csv": {"text"},
    ".txt": {"text"},
    ".xlsx": {"zip"},
    ".xls": {"ole", "text"},  # some exporters emit CSV/HTML with an .xls name
}


def sniff(data: bytes) -> str:
    """Classify the payload from its leading bytes."""
    for prefix, kind in _MAGIC:
        if data.startswith(prefix):
            return kind
    sample = data[:4096]
    if b"\x00" in sample:
        return "binary"
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
        except UnicodeDecodeError:
            return "binary"
    return "text"


def safe_filename(raw: str) -> str:
    """Reduce a client-supplied name to a bare basename, or reject it.

    ``../../etc/passwd`` must never reach the filesystem *or* the storage key.
    Separators and parent references are treated as an attack, not as something
    to silently strip, because a caller with a legitimate file has no reason to
    send one.
    """
    name = (raw or "").strip()
    if not name:
        raise bad_request("INVALID_FILENAME", "That file name is not valid.")
    if "\x00" in name or "/" in name or "\\" in name or ".." in name:
        logger.warning(
            "rejected_unsafe_filename", extra={"event": "rejected_unsafe_filename"}
        )
        raise bad_request(
            "INVALID_FILENAME",
            "That file name is not valid. Please rename the file and try again.",
        )
    name = os.path.basename(name)
    if not name or name.startswith("."):
        raise bad_request("INVALID_FILENAME", "That file name is not valid.")
    return name[:255]


def check_extension(filename: str, settings: Settings) -> str:
    _, ext = os.path.splitext(filename.lower())
    if ext not in settings.allowed_upload_extensions:
        raise ApiError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            "That file type is not supported. Upload a CSV, PDF or spreadsheet export.",
            log_detail="extension=%s" % ext,
        )
    return ext


def check_content_type(content_type: str, settings: Settings) -> str:
    value = (content_type or "").split(";")[0].strip().lower()
    if not value:
        return "application/octet-stream"
    if value not in settings.allowed_upload_content_types:
        raise ApiError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            "That file type is not supported. Upload a CSV, PDF or spreadsheet export.",
            log_detail="content_type=%s" % value,
        )
    return value


def check_size(size_bytes: int, settings: Settings) -> None:
    if size_bytes <= 0:
        raise bad_request(
            "EMPTY_FILE", "That file is empty. Please upload a statement with transactions."
        )
    if size_bytes > settings.max_upload_bytes:
        raise ApiError(
            413,
            "FILE_TOO_LARGE",
            "That file is larger than the %d MB limit."
            % (settings.max_upload_bytes // (1024 * 1024)),
        )


def check_content_matches_extension(data: bytes, extension: str) -> None:
    kind = sniff(data)
    allowed = _ALLOWED_KINDS.get(extension)
    if allowed is not None and kind not in allowed:
        logger.warning(
            "rejected_content_type_mismatch",
            extra={"event": "rejected_content_type_mismatch", "sniffed": kind},
        )
        raise ApiError(
            415,
            "CONTENT_TYPE_MISMATCH",
            "The contents of that file do not match its file type. "
            "Please upload the original statement export.",
            log_detail="extension=%s sniffed=%s" % (extension, kind),
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/presign", status_code=status.HTTP_201_CREATED, summary="Request an upload grant")
def presign(
    payload: PresignRequest,
    settings: Settings = Depends(get_settings),
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    filename = safe_filename(payload.filename)
    extension = check_extension(filename, settings)
    content_type = check_content_type(payload.content_type, settings)
    check_size(payload.size_bytes, settings)

    # §22 randomized object keys: derived from a UUID and the date, never from
    # the user's filename. The filename is kept only as display metadata.
    object_key = random_object_key(filename)
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.upload_url_ttl_seconds
    )

    ticket = UploadTicket(
        user_id=session.id,
        filename=filename,
        content_type=content_type,
        object_key=object_key,
        upload_url="/api/uploads/%s/content",
        max_bytes=settings.max_upload_bytes,
        expires_at=expires_at.isoformat(),
    )
    ticket.upload_url = "/api/uploads/%s/content" % ticket.id
    repos.documents.put_ticket(ticket)

    # The document record is created up front and shares the ticket's ID, so the
    # `upload_id` the client receives here is the same one it later passes to
    # POST /api/analyses. One identifier, one object, no mapping table.
    repos.documents.put(
        UploadedDocument(
            id=ticket.id,
            user_id=session.id,
            filename=filename,
            content_type=content_type,
            size_bytes=0,
            object_key=object_key,
            expires_at=ticket.expires_at,
        )
    )
    logger.info("upload_presigned", extra={"event": "upload_presigned", "extension": extension})

    return {
        "upload_id": ticket.id,
        "upload_url": ticket.upload_url,
        "method": "PUT",
        "fields": {},
        "object_key": object_key,
        "expires_in_seconds": settings.upload_url_ttl_seconds,
        "expires_at": ticket.expires_at,
        "max_size_bytes": settings.max_upload_bytes,
    }


def _load_ticket(
    repos: Repositories, session: User, upload_id: str
) -> Tuple[UploadTicket, UploadedDocument]:
    parse_uuid(upload_id, "upload_id")
    ticket = repos.documents.get_ticket(upload_id)
    document = repos.documents.get(upload_id)
    if ticket is None or document is None or ticket.user_id != session.id:
        raise not_found("UPLOAD_NOT_FOUND", "That upload could not be found.")
    if ticket.expires_at:
        try:
            expires = datetime.fromisoformat(ticket.expires_at)
            if expires < datetime.now(timezone.utc):
                raise ApiError(
                    410, "UPLOAD_EXPIRED", "That upload link has expired. Please try again."
                )
        except ValueError:  # pragma: no cover - malformed stored timestamp
            pass
    return ticket, document


def _store(
    repos: Repositories,
    settings: Settings,
    ticket: UploadTicket,
    document: UploadedDocument,
    data: bytes,
    delete_after_processing: bool = True,
) -> Dict[str, Any]:
    check_size(len(data), settings)
    extension = check_extension(ticket.filename, settings)
    check_content_matches_extension(data, extension)

    document.size_bytes = len(data)
    document.checksum = hashlib.sha256(data).hexdigest()
    document.uploaded_at = utc_now()
    document.delete_after_processing = delete_after_processing
    document.password_protected = data.startswith(b"%PDF") and b"/Encrypt" in data[:8192]
    repos.documents.put(document)
    repos.documents.put_content(document.id, data)

    ticket.consumed = True
    repos.documents.put_ticket(ticket)

    logger.info(
        "upload_stored",
        extra={"event": "upload_stored", "size_bytes": len(data), "extension": extension},
    )
    return {
        "upload_id": document.id,
        "size_bytes": document.size_bytes,
        "checksum": document.checksum,
        "object_key": document.object_key,
        "password_protected": document.password_protected,
        "received": True,
    }


@router.put("/{upload_id}/content", summary="Upload the file body for a grant")
async def put_content(
    upload_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    ticket, document = _load_ticket(repos, session, upload_id)
    body = await request.body()
    return _store(repos, settings, ticket, document, body)


@router.post("/{upload_id}/content", summary="Upload the file body as multipart form data")
async def post_content(
    upload_id: str,
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    ticket, document = _load_ticket(repos, session, upload_id)
    # Read with a ceiling so an oversized body is rejected without buffering it
    # all — the extra byte is what distinguishes "at the limit" from "over".
    data = await file.read(settings.max_upload_bytes + 1)
    if file.filename:
        # The declared name is validated but never becomes the storage key.
        safe_filename(file.filename)
    return _store(repos, settings, ticket, document, data)
