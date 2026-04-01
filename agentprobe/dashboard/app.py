"""FastAPI application for the AgentProbe dashboard."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agentprobe.core.models import AgentRecording
from agentprobe.storage.store import RecordingStore

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_store(config: Optional[Dict[str, Any]] = None) -> RecordingStore:
    """Instantiate a RecordingStore using the config or defaults."""
    db_path = ".agentprobe/index.db"
    if config and "db_path" in config:
        db_path = config["db_path"]
    return RecordingStore(db_path=db_path)


def _load_recording(store: RecordingStore, recording_id: str) -> AgentRecording:
    """Load the full recording from disk via the store index."""
    row = store.get(recording_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found")
    file_path = Path(row["path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Recording file not found: {file_path}")
    return AgentRecording.load(file_path)


def _compute_pass_rate(store: RecordingStore) -> float:
    """Return the pass rate as a percentage (0-100)."""
    stats = store.stats()
    by_status = stats.get("by_status", {})
    total = stats.get("total_recordings", 0)
    if total == 0:
        return 0.0
    success = by_status.get("success", 0)
    return round((success / total) * 100, 1)


def _cost_by_model(store: RecordingStore) -> List[Dict[str, Any]]:
    """Return cost aggregated by model."""
    conn = store._conn
    rows = conn.execute(
        "SELECT model, SUM(cost) AS total_cost, COUNT(*) AS count "
        "FROM recordings GROUP BY model ORDER BY total_cost DESC"
    ).fetchall()
    return [{"model": r["model"], "total_cost": round(r["total_cost"], 6), "count": r["count"]} for r in rows]


def _cost_over_time(store: RecordingStore) -> List[Dict[str, Any]]:
    """Return daily cost over time."""
    conn = store._conn
    rows = conn.execute(
        "SELECT DATE(created_at) AS day, SUM(cost) AS daily_cost, COUNT(*) AS count "
        "FROM recordings GROUP BY DATE(created_at) ORDER BY day"
    ).fetchall()
    return [{"day": r["day"], "cost": round(r["daily_cost"], 6), "count": r["count"]} for r in rows]


def _top_expensive(store: RecordingStore, limit: int = 10) -> List[Dict[str, Any]]:
    """Return the top N most expensive recordings."""
    conn = store._conn
    rows = conn.execute(
        "SELECT id, name, model, cost, duration, created_at "
        "FROM recordings ORDER BY cost DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _recent_test_runs(store: RecordingStore, limit: int = 10) -> List[Dict[str, Any]]:
    """Return recent recordings as a proxy for test runs."""
    return store.list_all(limit=limit)


def _format_duration(ms: float) -> str:
    """Format milliseconds into a readable string."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = seconds / 60
    return f"{minutes:.1f}m"


def _format_cost(usd: float) -> str:
    """Format USD cost."""
    if usd < 0.01:
        return f"${usd:.4f}"
    return f"${usd:.2f}"


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config: Optional[Dict[str, Any]] = None) -> FastAPI:
    """Create the dashboard FastAPI app."""

    app = FastAPI(
        title="AgentProbe Dashboard",
        description="Visual interface for AgentProbe recordings, tests, and cost analysis",
        version="0.1.0",
    )

    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    # Register template globals / filters
    templates.env.globals["format_duration"] = _format_duration
    templates.env.globals["format_cost"] = _format_cost

    # Serve static files if directory has content
    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Store config in app state
    app.state.config = config or {}

    # ------------------------------------------------------------------
    # HTML routes
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def root():
        """Redirect root to dashboard."""
        return RedirectResponse(url="/dashboard", status_code=302)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Main overview page."""
        store = _get_store(app.state.config)
        try:
            stats = store.stats()
            pass_rate = _compute_pass_rate(store)
            recent = _recent_test_runs(store)
            cost_time = _cost_over_time(store)
            by_status = stats.get("by_status", {})

            alerts: List[Dict[str, str]] = []
            error_count = by_status.get("error", 0)
            if error_count > 0:
                alerts.append({
                    "level": "error",
                    "message": f"{error_count} recording(s) ended with errors",
                })
            timeout_count = by_status.get("timeout", 0)
            if timeout_count > 0:
                alerts.append({
                    "level": "warning",
                    "message": f"{timeout_count} recording(s) timed out",
                })
            if stats["total_cost_usd"] > 10.0:
                alerts.append({
                    "level": "warning",
                    "message": f"Total cost has reached {_format_cost(stats['total_cost_usd'])}",
                })

            return templates.TemplateResponse("dashboard.html", {
                "request": request,
                "stats": stats,
                "pass_rate": pass_rate,
                "recent_runs": recent,
                "cost_over_time": cost_time,
                "alerts": alerts,
                "page": "dashboard",
            })
        finally:
            store.close()

    @app.get("/recordings", response_class=HTMLResponse)
    async def recordings_page(
        request: Request,
        q: Optional[str] = Query(None, description="Search query"),
        framework: Optional[str] = Query(None),
        model: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        after: Optional[str] = Query(None),
        before: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        per_page: int = Query(50, ge=1, le=200),
    ):
        """Recordings list page with search/filter."""
        store = _get_store(app.state.config)
        try:
            offset = (page - 1) * per_page
            recordings = store.search(
                name=q,
                framework=framework if framework else None,
                model=model if model else None,
                status=status if status else None,
                after=after,
                before=before,
                limit=per_page,
                offset=offset,
            )
            total = store.count()
            stats = store.stats()

            # Get unique values for filter dropdowns
            frameworks = list(stats.get("by_framework", {}).keys())
            models = list(stats.get("by_model", {}).keys())
            statuses = list(stats.get("by_status", {}).keys())

            return templates.TemplateResponse("recordings.html", {
                "request": request,
                "recordings": recordings,
                "total": total,
                "page_num": page,
                "per_page": per_page,
                "q": q or "",
                "framework_filter": framework or "",
                "model_filter": model or "",
                "status_filter": status or "",
                "frameworks": frameworks,
                "models": models,
                "statuses": statuses,
                "page": "recordings",
            })
        finally:
            store.close()

    @app.get("/recordings/{recording_id}", response_class=HTMLResponse)
    async def recording_detail(request: Request, recording_id: str):
        """Single recording trace view."""
        store = _get_store(app.state.config)
        try:
            row = store.get(recording_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Recording not found")
            recording = _load_recording(store, recording_id)
            rec_dict = recording.to_dict()

            return templates.TemplateResponse("recording_detail.html", {
                "request": request,
                "recording": rec_dict,
                "row": row,
                "page": "recordings",
            })
        finally:
            store.close()

    @app.get("/tests", response_class=HTMLResponse)
    async def tests_page(request: Request):
        """Test run history page."""
        store = _get_store(app.state.config)
        try:
            recordings = store.list_all(limit=100)
            stats = store.stats()
            pass_rate = _compute_pass_rate(store)

            return templates.TemplateResponse("recordings.html", {
                "request": request,
                "recordings": recordings,
                "total": stats.get("total_recordings", 0),
                "page_num": 1,
                "per_page": 100,
                "q": "",
                "framework_filter": "",
                "model_filter": "",
                "status_filter": "",
                "frameworks": list(stats.get("by_framework", {}).keys()),
                "models": list(stats.get("by_model", {}).keys()),
                "statuses": list(stats.get("by_status", {}).keys()),
                "page": "tests",
                "is_tests_view": True,
                "pass_rate": pass_rate,
            })
        finally:
            store.close()

    @app.get("/tests/{run_id}", response_class=HTMLResponse)
    async def test_run_detail(request: Request, run_id: str):
        """Single test run results — delegates to recording detail."""
        return RedirectResponse(url=f"/recordings/{run_id}", status_code=302)

    @app.get("/costs", response_class=HTMLResponse)
    async def costs_page(request: Request):
        """Cost analysis dashboard."""
        store = _get_store(app.state.config)
        try:
            stats = store.stats()
            by_model = _cost_by_model(store)
            over_time = _cost_over_time(store)
            top_expensive = _top_expensive(store)

            return templates.TemplateResponse("costs.html", {
                "request": request,
                "stats": stats,
                "cost_by_model": by_model,
                "cost_over_time": over_time,
                "top_expensive": top_expensive,
                "page": "costs",
            })
        finally:
            store.close()

    # ------------------------------------------------------------------
    # JSON API routes
    # ------------------------------------------------------------------

    @app.get("/api/recordings")
    async def api_recordings(
        q: Optional[str] = Query(None),
        framework: Optional[str] = Query(None),
        model: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
    ):
        """JSON API for recordings list."""
        store = _get_store(app.state.config)
        try:
            recordings = store.search(
                name=q,
                framework=framework if framework else None,
                model=model if model else None,
                status=status if status else None,
                limit=limit,
                offset=offset,
            )
            return JSONResponse(content={
                "recordings": recordings,
                "total": store.count(),
                "limit": limit,
                "offset": offset,
            })
        finally:
            store.close()

    @app.get("/api/recordings/{recording_id}")
    async def api_recording_detail(recording_id: str):
        """JSON API for a single recording with full trace."""
        store = _get_store(app.state.config)
        try:
            recording = _load_recording(store, recording_id)
            return JSONResponse(content=recording.to_dict())
        finally:
            store.close()

    @app.get("/api/stats")
    async def api_stats():
        """JSON API for aggregate stats."""
        store = _get_store(app.state.config)
        try:
            stats = store.stats()
            stats["pass_rate"] = _compute_pass_rate(store)
            return JSONResponse(content=stats)
        finally:
            store.close()

    @app.get("/api/costs")
    async def api_costs():
        """JSON API for cost data."""
        store = _get_store(app.state.config)
        try:
            return JSONResponse(content={
                "stats": store.stats(),
                "by_model": _cost_by_model(store),
                "over_time": _cost_over_time(store),
                "top_expensive": _top_expensive(store),
            })
        finally:
            store.close()

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def start_dashboard(port: int = 9847, host: str = "127.0.0.1") -> None:
    """Start the dashboard server."""
    try:
        import uvicorn
    except ImportError:
        raise RuntimeError(
            "uvicorn is required to run the dashboard. "
            "Install it with: pip install uvicorn[standard]"
        )

    app = create_app()
    logger.info("Starting AgentProbe dashboard at http://%s:%d", host, port)
    print(f"\n  AgentProbe Dashboard")
    print(f"  http://{host}:{port}\n")
    uvicorn.run(app, host=host, port=port, log_level="info")
