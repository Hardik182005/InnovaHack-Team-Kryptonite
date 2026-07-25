"""Goals and growth simulation — §6.10, §18.

Nothing here executes, buys or recommends a security. A simulation is arithmetic
over the user's own contributions plus an explicitly illustrative assumption, and
principal is always reported separately from growth (§25.11, §25.12).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Request, status

from ..config import get_logger
from ..dependencies import (
    ApiError,
    authorize_analysis,
    bad_request,
    get_repositories,
    get_session,
    not_found,
    parse_uuid,
)
from ..models.entities import CalculationProvenance, FinancialGoal, Simulation, User, utc_now
from ..models.transaction import money
from ..repositories.base import Repositories
from ..services import projections
from ..services.pipeline import STATE_RECOVERABLE
from . import serializers
from .schemas import GoalPatch, GoalRequest, SimulateRequest
from .support import require_analysis_ready

logger = get_logger(__name__)

router = APIRouter(prefix="/api/goals", tags=["goals"])

ZERO = Decimal("0.00")


def _parse_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        raise bad_request("INVALID_DATE", "Use a target date in YYYY-MM-DD format.")


def _months_until(target: Optional[date]) -> int:
    if target is None:
        return 12
    today = date.today()
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if months <= 0:
        raise bad_request(
            "TARGET_DATE_IN_PAST", "Choose a target date in the future."
        )
    return months


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create a goal (§6.10)")
def create_goal(
    payload: GoalRequest,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    analysis = authorize_analysis(repos, session, payload.analysis_id)
    require_analysis_ready(analysis)

    target_date = _parse_date(payload.target_date)
    record = FinancialGoal(
        analysis_id=analysis.id,
        user_id=session.id,
        name=payload.name,
        goal_type=payload.goal_type,
        target_amount=money(payload.target_amount),
        target_date=target_date,
        months=_months_until(target_date),
        starting_principal=money(payload.starting_principal),
    )
    repos.goals.put(record)
    return serializers.goal(record)


def _load_goal(repos: Repositories, session: User, goal_id: str):
    parse_uuid(goal_id, "goal_id")
    record = repos.goals.get(goal_id)
    if record is None:
        raise not_found("GOAL_NOT_FOUND", "We could not find that goal.")
    analysis = authorize_analysis(repos, session, record.analysis_id)
    return record, analysis


@router.patch("/{goal_id}", summary="Update a goal")
def patch_goal(
    goal_id: str,
    payload: GoalPatch,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    record, _ = _load_goal(repos, session, goal_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise bad_request("NO_CHANGES", "No changes were supplied.")

    if "name" in changes:
        record.name = changes["name"]
    if "target_amount" in changes:
        record.target_amount = money(changes["target_amount"])
    if "starting_principal" in changes:
        record.starting_principal = money(changes["starting_principal"])
    if "target_date" in changes:
        record.target_date = _parse_date(changes["target_date"])
        record.months = _months_until(record.target_date)
    record.updated_at = utc_now()
    repos.goals.put(record)
    return serializers.goal(record)


@router.post("/{goal_id}/simulate", summary="Run an illustrative projection (§6.10)")
def simulate_goal(
    goal_id: str,
    payload: SimulateRequest,
    repos: Repositories = Depends(get_repositories),
    session: User = Depends(get_session),
) -> Dict[str, Any]:
    record, analysis = _load_goal(repos, session, goal_id)
    require_analysis_ready(analysis)

    snapshot = repos.calculations.get_safe_spare(analysis.id)
    roundup_record = repos.calculations.get_roundups(analysis.id)
    recoverable = repos.calculations.get_state(analysis.id, STATE_RECOVERABLE, {}) or {}

    safe_monthly = snapshot.safe_monthly_contribution if snapshot else ZERO
    roundups = (
        roundup_record.allowed_round_up_total
        if (roundup_record and payload.include_roundups)
        else ZERO
    )
    confirmed = ZERO
    if payload.include_confirmed_recovery:
        try:
            confirmed = money(recoverable.get("confirmed_from_decisions", "0"))
        except Exception:
            confirmed = ZERO

    # The Safe Spare snapshot already folds in confirmed recovery, so adding it
    # again here would double-count it. It is reported separately for the UI.
    if snapshot is not None and snapshot.confirmed_recovery_included > 0:
        confirmed_for_math = ZERO
    else:
        confirmed_for_math = confirmed

    months = payload.months or record.months
    rate = (
        Decimal(payload.annual_return_rate)
        if payload.annual_return_rate is not None
        else record.annual_return_rate
    )

    inputs = projections.GoalInputs(
        target_amount=record.target_amount,
        months=months,
        starting_principal=record.starting_principal,
        safe_monthly_contribution=safe_monthly,
        confirmed_recovered_amount=confirmed_for_math,
        roundup_contribution=roundups,
        annual_return_rate=rate,
        target_date=record.target_date,
    )
    result = projections.simulate(inputs)

    simulation = Simulation(
        goal_id=record.id,
        analysis_id=analysis.id,
        user_contributions=result.user_contributions,
        illustrative_growth=result.illustrative_growth,
        projected_value=result.projected_value,
        goal_gap=result.goal_gap,
        estimated_completion_months=result.estimated_completion_months,
        estimated_completion_date=result.estimated_completion_date,
        required_monthly_contribution=result.required_monthly_contribution,
        safe_monthly_contribution=safe_monthly,
        contribution_shortfall=result.contribution_shortfall,
        achievable=result.achievable,
        scenarios=[
            {
                "name": s.name,
                "annual_rate": float(s.annual_rate),
                "user_contributions": str(s.user_contributions),
                "illustrative_growth": str(s.illustrative_growth),
                "projected_value": str(s.projected_value),
            }
            for s in result.scenarios
        ],
        disclaimer=result.disclaimer,
        prov=CalculationProvenance(
            calculation_version=projections.CALCULATION_VERSION,
            method="projections.simulate",
            confidence=1.0,
            timestamp=utc_now(),
        ),
    )
    repos.goals.put_simulation(simulation)

    return serializers.simulation_response(
        simulation,
        record,
        analysis.currency,
        inputs.monthly_contribution,
        roundups,
        confirmed,
        _timeline(inputs, months),
    )


def _timeline(inputs: projections.GoalInputs, months: int) -> List[Dict[str, Any]]:
    """Month-by-month principal vs growth, for the chart (§6.4, §25.12).

    Sampled to at most 24 points so a 40-year goal does not return 480 rows.
    """
    rate = projections.monthly_rate_from_annual(inputs.annual_return_rate)
    monthly = inputs.monthly_contribution
    step = max(1, months // 24)
    out: List[Dict[str, Any]] = []
    for m in range(0, months + 1, step):
        value = projections.future_value(inputs.starting_principal, monthly, rate, m)
        contributed = money(inputs.starting_principal + monthly * Decimal(m))
        out.append(
            {
                "month": m,
                "user_contributions": str(contributed),
                "illustrative_growth": str(money(value - contributed)),
                "projected_value": str(value),
            }
        )
    return out
