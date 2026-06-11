"""Shared FastAPI route dependencies for gateway admin APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from gateway.agent_manager import AgentProcessState
from gateway.agent_store import AgentFileKind
from gateway.instance_store import InstanceStore


def store(request: Request) -> InstanceStore:
    return request.app.state.agent_store


def manager(request: Request):
    return request.app.state.agent_manager


def lifecycle(request: Request):
    return request.app.state.instance_lifecycle


def definitions(request: Request):
    return request.app.state.definition_store


def definition_registry(request: Request):
    return request.app.state.definition_registry


def completions(request: Request):
    return request.app.state.completion_log


def file_kind(name: str) -> AgentFileKind:
    try:
        return AgentFileKind(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid file kind") from exc


def require_instance_dir(instance_store: InstanceStore, instance_id: str) -> Path:
    try:
        instance_dir = instance_store.agent_dir(instance_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not instance_dir.exists():
        raise HTTPException(status_code=404, detail="instance_not_found")
    return instance_dir


def instance_view_or_404(request: Request, instance_id: str) -> dict[str, Any]:
    lifecycle_mgr = lifecycle(request)
    try:
        return lifecycle_mgr.instance_view(instance_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc


async def stop_managed_instance(request: Request, instance_id: str) -> None:
    process_manager = manager(request)
    if process_manager.get(instance_id) is None:
        raise HTTPException(status_code=404, detail="instance_not_found")
    try:
        await process_manager.stop(instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc


async def delete_managed_instance(request: Request, instance_id: str) -> None:
    instance_store = store(request)
    process_manager = manager(request)
    managed = process_manager.get(instance_id)
    if managed and managed.state != AgentProcessState.STOPPED:
        await process_manager.stop(instance_id)
    try:
        instance_store.delete_agent(instance_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc
    process_manager.unregister(instance_id)
