"""Gateway-wide admin endpoints (status, diagnostics, tools)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from gateway.frontend_static import frontend_asset_refs, validate_frontend_build
from gateway.routes import deps
from gateway.urls import static_dir

router = APIRouter(prefix="/api", tags=["admin"])


class SearchBody(BaseModel):
    query: str
    count: int = Field(default=5, ge=1, le=20)


class FetchBody(BaseModel):
    url: str


@router.get("/frontend-health")
async def frontend_health() -> dict[str, Any]:
    """Report whether the built SPA assets match index.html (JSON diagnostic)."""
    root = static_dir()
    if root is None:
        return {
            "ok": False,
            "problem": "not_built",
            "message": "Frontend dist/ not found. Run: cd web && npm install && npm run build",
            "web_ui": "/",
        }
    ok, missing = validate_frontend_build(root)
    return {
        "ok": ok,
        "dist": str(root),
        "assets": frontend_asset_refs(root),
        "missing": missing,
        "web_ui": "/",
        "message": None
        if ok
        else "Stale or incomplete frontend build — run: cd web && npm run build, restart gateway, hard-refresh browser",
    }


@router.get("/spawn-defaults")
async def get_spawn_defaults(request: Request) -> dict[str, Any]:
    """Defaults for spawn UX (model, puller, LLM options)."""
    return request.app.state.config.spawn_defaults.model_dump()


@router.get("/status")
async def gateway_status(request: Request) -> dict[str, Any]:
    manager = deps.manager(request)
    instance_store = deps.store(request)
    config = request.app.state.config
    cp_client = request.app.state.control_plane_client

    cp_ok, cp_error = await cp_client.check_health()

    try:
        instance_count = len(instance_store.list_instances())
    except Exception:
        instance_count = len(instance_store.list_agents())

    try:
        definition_count = len(deps.definitions(request).list_definitions())
    except Exception:
        definition_count = 0

    definitions_root = deps.definitions(request).root

    return {
        "node_id": config.node.id,
        "gateway_url": f"http://{config.server.host}:{config.server.port}",
        "agents_root": str(instance_store.root),
        "definitions_root": str(definitions_root),
        "agent_count": len(instance_store.list_agents()),
        "definition_count": definition_count,
        "instance_count": instance_count,
        "running_agent_count": manager.running_count(),
        "interactive_session_count": len(request.app.state.interactive_manager.list_sessions()),
        "control_plane_url": cp_client.base_url,
        "control_plane_connected": cp_ok,
        "control_plane_error": cp_error,
    }


@router.post("/tools/search")
async def search_web(request: Request, body: SearchBody) -> dict[str, Any]:
    from gateway.brave_search import brave_web_search, format_brave_results

    api_key = request.app.state.config.brave_api_key
    try:
        payload = await brave_web_search(api_key=api_key, query=body.query, count=body.count)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"query": body.query, "formatted": format_brave_results(payload), "raw": payload}


@router.post("/tools/fetch")
async def fetch_web(request: Request, body: FetchBody) -> dict[str, Any]:
    from gateway.url_fetch import fetch_url

    try:
        content = await fetch_url(body.url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"url": body.url, "content": content}
