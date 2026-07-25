"""Safe Spare and round-up read/settings endpoints — §6.6, §6.8, §18.

Changing a setting re-runs the deterministic engines, so the user sees the
consequence of a tighter buffer or a bigger increment immediately.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from ..config import get_logger
from ..dependencies import get_analysis, get_repositories, get_session
from ..models.entities import AnalysisSession, User
from ..repositories.base import Repositories
from ..services.pipeline import (
    STATE_ROUNDUP_RULES,
    STATE_SAFE_SPARE_SETTINGS,
)
from . import serializers
from .schemas import RoundUpRulesPatch, SafeSpareSettingsPatch
from .support import recalculate, record_audit, require_analysis_ready

logger = get_logger(__name__)

router = APIRouter(prefix="/api/analyses", tags=["safe-spare"])


@router.get("/{analysis_id}/safe-spare", summary="Safe Spare breakdown (§6.6)")
def get_safe_spare(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    return serializers.safe_spare(analysis, repos)


@router.patch("/{analysis_id}/safe-spare-settings", summary="Change safety settings (§6.6)")
def patch_safe_spare_settings(
    payload: SafeSpareSettingsPatch,
    request: Request,
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    before = repos.calculations.get_state(analysis.id, STATE_SAFE_SPARE_SETTINGS, {}) or {}
    changes = payload.model_dump(exclude_unset=True)
    merged = dict(before)
    merged.update({k: v for k, v in changes.items() if v is not None})
    # An explicit null clears a cap rather than being ignored.
    for key, value in changes.items():
        if value is None:
            merged.pop(key, None)

    repos.calculations.set_state(analysis.id, STATE_SAFE_SPARE_SETTINGS, merged)
    record_audit(
        repos,
        analysis,
        session,
        entity_type="analysis",
        entity_id=analysis.id,
        action="safe_spare_settings",
        before=before,
        after=merged,
        request=request,
    )
    recalculate(repos, request.app.state.settings, analysis)
    return serializers.safe_spare(analysis, repos)


@router.get("/{analysis_id}/roundups", summary="Round-up calculation (§6.8)")
def get_roundups(
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    return serializers.roundups(analysis, repos)


@router.patch("/{analysis_id}/roundup-rules", summary="Change round-up rules (§6.8)")
def patch_roundup_rules(
    payload: RoundUpRulesPatch,
    request: Request,
    analysis: AnalysisSession = Depends(get_analysis),
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    require_analysis_ready(analysis)
    before = repos.calculations.get_state(analysis.id, STATE_ROUNDUP_RULES, {}) or {}
    changes = payload.model_dump(exclude_unset=True)

    merged = dict(before)
    for key, value in changes.items():
        if value is None:
            merged.pop(key, None)
        elif key == "excluded_categories":
            merged[key] = [c.value if hasattr(c, "value") else str(c) for c in value]
        else:
            merged[key] = value

    repos.calculations.set_state(analysis.id, STATE_ROUNDUP_RULES, merged)
    record_audit(
        repos,
        analysis,
        session,
        entity_type="analysis",
        entity_id=analysis.id,
        action="roundup_rules",
        before=before,
        after=merged,
        request=request,
    )
    recalculate(repos, request.app.state.settings, analysis)
    return serializers.roundups(analysis, repos)
