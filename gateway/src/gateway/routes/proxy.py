"""Proxy routes — agents talk to the gateway instead of the control plane."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from shared.schemas import AgentHeartbeat, Response, Task

router = APIRouter(prefix="/proxy", tags=["proxy"])


def _cp_client(request: Request):
    return request.app.state.control_plane_client


@router.post("/tasks", status_code=202)
async def proxy_submit_task(request: Request, task: Task) -> dict:
    client = _cp_client(request)
    try:
        return await client.post_task(task)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/responses", response_model=None)
async def proxy_get_responses(
    request: Request,
    agent_id: str,
    max: int = 10,
) -> dict | Response:
    client = _cp_client(request)
    try:
        responses = await client.get_responses(agent_id, max=max)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not responses:
        return Response(status_code=204)
    return {"responses": [item.model_dump(mode="json") for item in responses]}


@router.post("/heartbeat/agent")
async def proxy_agent_heartbeat(request: Request, body: AgentHeartbeat) -> dict:
    client = _cp_client(request)
    try:
        await client.post_agent_heartbeat(body)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"acknowledged": True}


@router.post("/tools/search")
async def proxy_search(request: Request, payload: dict) -> dict:
    from gateway.routes.admin import SearchBody, search_web

    body = SearchBody.model_validate(payload)
    return await search_web(request, body)


@router.post("/tools/fetch")
async def proxy_fetch(request: Request, payload: dict) -> dict:
    from gateway.routes.admin import FetchBody, fetch_web

    body = FetchBody.model_validate(payload)
    return await fetch_web(request, body)
