"""Analysis lifecycle and read endpoints — §18, §19.

Creating an analysis kicks the §19 state machine off in a background task so the
request returns immediately and the UI can poll `/status` for progress. The demo
path (`demo: true`) loads the synthetic statement from disk.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status

from ..config import Settings, get_logger
from ..dependencies import (
    ApiError,
    bad_request,
    get_analysis,
    get_repositories,
    get_session,
    not_found,
    parse_uuid,
)
from ..models.entities import (
    AnalysisSession,
    AnalysisStatus,
    UploadedDocument,
    User,
    utc_now,
)
from ..repositories.base import Repositories
from ..services.pipeline import AnalysisPipeline, PipelineError
from . import serializers
from .schemas import CreateAnalysisRequest
from .support import require_analysis_ready

logger = get_logger(__name__)

router = APIRouter(prefix="/api/analyses", tags=["analyses"])

#: Where the generated demo statement lives, relative to the repo root.
_DEMO_CANDIDATES = (
    "demo_data/demo_statement.csv",
    "backend/tests/fixtures/demo_statement.csv",
)


def _repo_root() -> str:
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def _load_demo_statement(settings: Settings):
    """Return (filename, bytes) for the synthetic demo statement (§23)."""
    configured = getattr(settings, "demo_statement_path", "") or ""
    candidates = ([configured] if configured else []) + [
        os.path.join(_repo_root(), "..", path) for path in _DEMO_CANDIDATES
    ] + [os.path.join(_repo_root(), path) for path in _DEMO_CANDIDATES]

    for path in candidates:
        resolved = os.path.abspath(path)
        if os.path.exists(resolved):
            with open(resolved, "rb") as handle:
                return os.path.basename(resolved), handle.read()
    return None, None


def _run_pipeline(
    repos: Repositories,
    settings: Settings,
    analysis_id: str,
    password: Optional[str] = None,
) -> None:
    """Background worker. Never raises — failures are recorded on the analysis.

    `password` is passed by value and never persisted (§22).
    """
    analysis = repos.analyses.get(analysis_id)
    if analysis is None:
        return
    try:
        AnalysisPipeline(repos, settings, password=password).run(analysis)
    except PipelineError as exc:
        logger.info("analysis %s failed: %s", analysis_id, exc.code)
    except Exception:  # pragma: no cover - defensive
        logger.exception("unexpected pipeline error for %s", analysis_id)
        current = repos.analyses.get(analysis_id)
        if current is not None and current.status is not AnalysisStatus.FAILED:
            current.fail("PIPELINE_FAILED", "We could not finish analysing this statement.")
            repos.analyses.put(current)


@router.post("", status_code=status.HTTP_202_ACCEPTED, summary="Start an analysis")
def create_analysis(
    payload: CreateAnalysisRequest,
    request: Request,
    background: BackgroundTasks,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    settings: Settings = request.app.state.settings

    if not payload.consent_confirmed:
        raise bad_request(
            "CONSENT_REQUIRED",
            "Please confirm you consent to your statement being analysed.",
        )

    # Idempotency (§19): the same key returns the original analysis rather than
    # starting a second one and duplicating the transactions.
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        existing_id = repos.analyses.find_by_idempotency_key(session.id, idempotency_key)
        if existing_id:
            existing = repos.analyses.get(existing_id)
            if existing is not None:
                return serializers.analysis_status(existing)

    if payload.demo:
        filename, content = _load_demo_statement(settings)
        if content is None:
            raise ApiError(
                503,
                "DEMO_UNAVAILABLE",
                "The demo statement is not available. Run scripts/generate_demo_statement.py.",
            )
        document = UploadedDocument(
            user_id=session.id,
            filename=filename,
            content_type="text/csv",
            size_bytes=len(content),
            object_key="demo/" + filename,
            is_demo=True,
            consent_given=True,
        )
        repos.documents.put(document)
        repos.documents.put_content(document.id, content)
        document_id = document.id
    else:
        if not payload.upload_id:
            raise bad_request(
                "UPLOAD_REQUIRED", "Upload a statement or choose the demo statement."
            )
        document_id = parse_uuid(payload.upload_id, "upload_id")
        document = repos.documents.get(document_id)
        if document is None or document.user_id != session.id:
            raise not_found("UPLOAD_NOT_FOUND", "We could not find that upload.")
        if not repos.documents.get_content(document_id):
            raise bad_request(
                "UPLOAD_INCOMPLETE", "That upload has not finished. Please try again."
            )
        if payload.document_password:
            document.password_protected = True
            repos.documents.put(document)

    analysis = AnalysisSession(
        user_id=session.id,
        document_id=document_id,
        idempotency_key=idempotency_key,
        auto_confirm=payload.auto_confirm or payload.demo,
        delete_after_processing=payload.delete_after_processing,
    )
    repos.analyses.put(analysis)
    if idempotency_key:
        repos.analyses.remember_idempotency_key(session.id, idempotency_key, analysis.id)

    background.add_task(
        _run_pipeline, repos, settings, analysis.id, payload.document_password
    )
    return serializers.analysis_status(analysis)


@router.get("/{analysis_id}/status", summary="Processing status and progress")
def analysis_status(
    analysis: AnalysisSession = Depends(get_analysis),
) -> Dict[str, Any]:
    return serializers.analysis_status(analysis)


@router.get("/{analysis_id}/summary", summary="Dashboard summary (§6.4)")
def analysis_summary(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    return serializers.summary(analysis, repos)


@router.get("/{analysis_id}/transactions", summary="Extraction review rows (§6.3)")
def analysis_transactions(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    needs_review: bool = Query(False),
) -> Dict[str, Any]:
    rows = repos.transactions.list_for_analysis(analysis.id)
    if needs_review:
        rows = [t for t in rows if t.validation_warnings or t.category_confidence < 0.7]
    total = len(rows)
    start = (page - 1) * page_size
    return serializers.transaction_page(
        analysis, rows[start : start + page_size], page, page_size, total
    )


@router.get("/{analysis_id}/categories", summary="Spending intelligence (§6.5)")
def analysis_categories(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    return serializers.categories(analysis, repos)


@router.get("/{analysis_id}/recurring", summary="Recurring payments (§11)")
def analysis_recurring(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    return serializers.recurring(analysis, repos)


@router.get("/{analysis_id}/leaks", summary="Leak Radar findings (§6.9)")
def analysis_leaks(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    return serializers.leaks(analysis, repos)


@router.get("/{analysis_id}/cashflow-confidence", summary="Cashflow Confidence (§6.7)")
def analysis_cashflow(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    return serializers.cashflow_confidence(analysis, repos)


@router.post("/{analysis_id}/confirm", summary="Confirm the extraction (§6.3)")
def confirm_analysis(
    request: Request,
    background: BackgroundTasks,
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    settings: Settings = request.app.state.settings
    if analysis.status is AnalysisStatus.COMPLETED:
        return serializers.analysis_status(analysis)
    if analysis.status is not AnalysisStatus.AWAITING_REVIEW:
        raise ApiError(
            409, "NOT_AWAITING_REVIEW", "This analysis is not waiting for confirmation."
        )
    background.add_task(_run_pipeline, repos, settings, analysis.id)
    return serializers.analysis_status(analysis)


@router.delete("/{analysis_id}", summary="Delete an analysis and its data (§22)")
def delete_analysis(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    result = repos.purge_analysis(analysis.id)
    logger.info("analysis deleted")
    return {"deleted": True, "analysis_id": analysis.id, "detail": result}
