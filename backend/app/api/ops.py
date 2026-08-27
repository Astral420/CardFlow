"""Serves the lightweight ops dashboard: a single dependency-free HTML/JS
page (no separate frontend build, no Grafana/Prometheus stack -- see
/OBSERVABILITY.md's Dashboard section for why) that polls
GET /api/health/pipeline and renders it.

Gated by an optional shared-secret query token (?token=...) instead of
app-level auth -- see app.config.Settings.ops_dashboard_token and
app/api/health.py's module docstring for the reasoning.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from app.config import settings

router = APIRouter(prefix="/api/ops", tags=["ops"])

_DASHBOARD_HTML = (
    Path(__file__).resolve().parent.parent / "templates" / "ops_dashboard.html"
).read_text(encoding="utf-8")


@router.get("/dashboard", response_class=HTMLResponse)
def ops_dashboard(token: str = Query(default="")) -> HTMLResponse:
    if settings.ops_dashboard_token and token != settings.ops_dashboard_token:
        # 404 rather than 401/403: don't confirm to an unauthenticated
        # caller that a token-gated route even exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return HTMLResponse(_DASHBOARD_HTML)
