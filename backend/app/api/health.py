"""Liveness and readiness — §17, §18.

``/health`` answers "is this process up?" and must stay dependency-free so a
load balancer never removes a healthy instance because a third party is down.

``/ready`` reports provider configuration and reachability. It is deliberately
**always 200**: with every LLM provider unavailable the deterministic core still
produces every financial figure (§3.21), so a down provider is a degraded
capability, not an unready service. The payload carries provider names, model
identifiers and states only — never a key (§14, §22).
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from ..config import Settings
from ..dependencies import ai_provider_status, get_settings

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
def health(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    return {
        "status": "ok",
        "version": settings.version,
        "environment": settings.environment,
    }


@router.get("/ready", summary="Readiness probe with AI provider status")
def ready(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """Report configuration health without ever disclosing a credential."""
    router_status = ai_provider_status()
    configured = settings.provider_status()

    # Merge: settings knows what is *configured*, the router knows what is
    # *reachable*. Keys are never present in either structure.
    merged: Dict[str, Dict[str, Any]] = {}
    for entry in configured:
        name = str(entry.get("provider", "unknown"))
        merged[name] = {
            "provider": name,
            "configured": bool(entry.get("configured")),
            "credentials_present": bool(entry.get("credentials_present")),
            "model": entry.get("model"),
            "fallback_model": entry.get("fallback_model"),
            "available": False,
            "detail": "configured" if entry.get("configured") else "not_configured",
            "roles": [],
        }
    for entry in router_status:
        name = str(entry.get("provider") or entry.get("name") or "unknown")
        target = merged.setdefault(
            name,
            {
                "provider": name,
                "configured": False,
                "credentials_present": False,
                "model": None,
                "fallback_model": None,
                "available": False,
                "detail": "unknown",
                "roles": [],
            },
        )
        target["available"] = bool(entry.get("available"))
        target["configured"] = bool(entry.get("configured", target["configured"]))
        if entry.get("model") is not None:
            target["model"] = entry.get("model")
        if entry.get("detail"):
            target["detail"] = entry.get("detail")
        if entry.get("roles"):
            target["roles"] = list(entry.get("roles") or [])

    providers = [merged[name] for name in sorted(merged)]
    return {
        "status": "ready",
        "version": settings.version,
        "environment": settings.environment,
        # The product is fully functional with this False (§3.21, §25.17).
        "ai_enabled": any(p["available"] for p in providers),
        "deterministic_core": "available",
        "providers": providers,
    }
