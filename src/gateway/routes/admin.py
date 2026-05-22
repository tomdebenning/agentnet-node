"""Admin REST API for agent management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from gateway.agent_manager import AgentProcessState
from gateway.agent_store import AgentFileKind, AgentStore

router = APIRouter(prefix="/api", tags=["admin"])


class CreateAgentBody(BaseModel):
    agent_id: str
    target_puller: str = "puller-01"
    model: str = "llama3.1:8b"
    persona_name: str | None = None
    persona_role: str = "helpful assistant"


class MarkdownUpdateBody(BaseModel):
    content: str | None = None
    frontmatter: dict[str, Any] | None = None
    body: str | None = None


class SearchBody(BaseModel):
    query: str
    count: int = Field(default=5, ge=1, le=20)


class FetchBody(BaseModel):
    url: str


def _store(request: Request) -> AgentStore:
    return request.app.state.agent_store


def _manager(request: Request):
    return request.app.state.agent_manager


def _agent_status(request: Request, agent_id: str) -> dict[str, Any]:
    store = _store(request)
    manager = _manager(request)
    try:
        store.agent_dir(agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    managed = manager.get(agent_id)
    if managed is None:
        managed = manager.register(agent_id, store.agent_dir(agent_id))

    parsed_config = store.read_parsed(agent_id, AgentFileKind.CONFIG)
    return {
        "agent_id": agent_id,
        "configured_agent_id": parsed_config["frontmatter"].get("agent_id", agent_id),
        "path": str(store.agent_dir(agent_id)),
        "process_state": managed.state.value,
        "pid": managed.pid,
        "return_code": managed.return_code,
        "error": managed.error,
        "config": parsed_config["frontmatter"],
    }


@router.get("/status")
async def gateway_status(request: Request) -> dict[str, Any]:
    manager = _manager(request)
    store = _store(request)
    config = request.app.state.config
    cp_client = request.app.state.control_plane_client

    cp_ok, cp_error = await cp_client.check_health()

    return {
        "node_id": config.node.id,
        "gateway_url": f"http://{config.server.host}:{config.server.port}",
        "agents_root": str(store.root),
        "agent_count": len(store.list_agents()),
        "running_agent_count": manager.running_count(),
        "control_plane_url": cp_client.base_url,
        "control_plane_connected": cp_ok,
        "control_plane_error": cp_error,
    }


@router.get("/agents")
async def list_agents(request: Request) -> dict[str, Any]:
    store = _store(request)
    manager = _manager(request)
    agents = []
    for summary in store.list_agents():
        managed = manager.get(summary.agent_id)
        if managed is None:
            managed = manager.register(summary.agent_id, summary.path)
        agents.append(
            {
                "agent_id": summary.agent_id,
                "path": str(summary.path),
                "process_state": managed.state.value,
                "pid": managed.pid,
            }
        )
    return {"agents": agents}


@router.post("/agents", status_code=201)
async def create_agent(request: Request, body: CreateAgentBody) -> dict[str, Any]:
    store = _store(request)
    manager = _manager(request)
    try:
        path = store.create_agent(
            body.agent_id,
            target_puller=body.target_puller,
            model=body.model,
            persona_name=body.persona_name,
            persona_role=body.persona_role,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    manager.register(body.agent_id, path)
    return _agent_status(request, body.agent_id)


@router.get("/agents/{agent_id}")
async def get_agent(request: Request, agent_id: str) -> dict[str, Any]:
    store = _store(request)
    if not store.agent_dir(agent_id).exists():
        raise HTTPException(status_code=404, detail="agent_not_found")
    return _agent_status(request, agent_id)


@router.delete("/agents/{agent_id}")
async def delete_agent(request: Request, agent_id: str) -> dict[str, Any]:
    store = _store(request)
    manager = _manager(request)
    managed = manager.get(agent_id)
    if managed and managed.state != AgentProcessState.STOPPED:
        await manager.stop(agent_id)
    try:
        store.delete_agent(agent_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="agent_not_found") from exc
    manager.unregister(agent_id)
    return {"deleted": True, "agent_id": agent_id}


@router.post("/agents/{agent_id}/start")
async def start_agent(request: Request, agent_id: str) -> dict[str, Any]:
    store = _store(request)
    if not store.agent_dir(agent_id).exists():
        raise HTTPException(status_code=404, detail="agent_not_found")
    manager = _manager(request)
    manager.register(agent_id, store.agent_dir(agent_id))
    try:
        await manager.start(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _agent_status(request, agent_id)


@router.post("/agents/{agent_id}/stop")
async def stop_agent(request: Request, agent_id: str) -> dict[str, Any]:
    manager = _manager(request)
    if manager.get(agent_id) is None:
        raise HTTPException(status_code=404, detail="agent_not_found")
    try:
        await manager.stop(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _agent_status(request, agent_id)


def _file_kind(name: str) -> AgentFileKind:
    try:
        return AgentFileKind(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid file kind") from exc


@router.get("/agents/{agent_id}/files/{kind}")
async def read_agent_file(request: Request, agent_id: str, kind: str) -> dict[str, Any]:
    store = _store(request)
    file_kind = _file_kind(kind)
    if not store.agent_dir(agent_id).exists():
        raise HTTPException(status_code=404, detail="agent_not_found")
    try:
        parsed = store.read_parsed(agent_id, file_kind)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"agent_id": agent_id, "kind": kind, **parsed}


@router.put("/agents/{agent_id}/files/{kind}")
async def write_agent_file(
    request: Request,
    agent_id: str,
    kind: str,
    body: MarkdownUpdateBody,
) -> dict[str, Any]:
    store = _store(request)
    file_kind = _file_kind(kind)
    if not store.agent_dir(agent_id).exists():
        raise HTTPException(status_code=404, detail="agent_not_found")

    try:
        if body.content is not None:
            store.write_file(agent_id, file_kind, body.content)
            parsed = store.read_parsed(agent_id, file_kind)
        else:
            rendered = store.write_parsed(
                agent_id,
                file_kind,
                frontmatter=body.frontmatter,
                body=body.body,
            )
            meta, text_body = store.read_parsed(agent_id, file_kind)["frontmatter"], body.body
            parsed = {"frontmatter": meta, "body": text_body or "", "raw": rendered}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"agent_id": agent_id, "kind": kind, **parsed}


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
