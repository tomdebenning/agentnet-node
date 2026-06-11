"""Fleet API — running agent instances."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from gateway.agent_manager import AgentProcessState
from shared.markdown_io import parse_markdown_document
from gateway.routes import deps
from gateway.spawn_defaults import explicit_run_options, resolved_instance_config

router = APIRouter(prefix="/api/fleet", tags=["fleet"])


class CreateInstanceBody(BaseModel):
    instance_id: str
    target_puller: str | None = None
    model: str | None = None
    temperature: float | None = None
    num_ctx: int | None = None
    persona_name: str | None = None
    persona_role: str = "helpful assistant"


class InteractiveMessageBody(BaseModel):
    message: str = Field(min_length=1)


class NewRunBody(BaseModel):
    goal: str = Field(min_length=1)
    temperature: float | None = None
    num_ctx: int | None = None


class MarkdownUpdateBody(BaseModel):
    content: str | None = None
    frontmatter: dict[str, Any] | None = None
    body: str | None = None


@router.get("/instances")
async def list_instances(request: Request) -> dict[str, Any]:
    try:
        instances = deps.lifecycle(request).fleet()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"instances_load_failed: {exc}") from exc
    return {"instances": instances}


@router.post("/instances", status_code=201)
async def create_instance(request: Request, body: CreateInstanceBody) -> dict[str, Any]:
    instance_store = deps.store(request)
    process_manager = deps.manager(request)
    config = request.app.state.config
    resolved = resolved_instance_config(
        config,
        model=body.model,
        target_puller=body.target_puller,
        temperature=body.temperature,
        num_ctx=body.num_ctx,
    )
    try:
        path = instance_store.create_agent(
            body.instance_id,
            target_puller=resolved["target_puller"],
            model=resolved["model"],
            temperature=resolved["temperature"],
            num_ctx=resolved["num_ctx"],
            persona_name=body.persona_name,
            persona_role=body.persona_role,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    process_manager.register(body.instance_id, path)
    return deps.instance_view_or_404(request, body.instance_id)


@router.get("/instances/{instance_id}")
async def get_instance(request: Request, instance_id: str) -> dict[str, Any]:
    return deps.instance_view_or_404(request, instance_id)


@router.delete("/instances/{instance_id}")
async def delete_instance(request: Request, instance_id: str) -> dict[str, Any]:
    await deps.delete_managed_instance(request, instance_id)
    return {"deleted": True, "instance_id": instance_id}


@router.post("/instances/{instance_id}/start")
async def start_instance(request: Request, instance_id: str) -> dict[str, Any]:
    instance_store = deps.store(request)
    if not instance_store.agent_dir(instance_id).exists():
        raise HTTPException(status_code=404, detail="instance_not_found")
    process_manager = deps.manager(request)
    process_manager.register(instance_id, instance_store.agent_dir(instance_id))
    managed = process_manager.get(instance_id)
    if managed and managed.state not in (
        AgentProcessState.STOPPED,
        AgentProcessState.ERROR,
    ):
        await process_manager.stop(instance_id)
    meta = {}
    try:
        meta = instance_store.read_instance_meta(instance_id)
    except FileNotFoundError:
        pass
    resume = bool(meta.get("resume_on_start"))
    try:
        await process_manager.start(instance_id, resume=resume)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc
    return deps.instance_view_or_404(request, instance_id)


@router.post("/instances/{instance_id}/stop")
async def stop_instance(request: Request, instance_id: str) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    try:
        await lifecycle_mgr.stop_instance(instance_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc
    return deps.instance_view_or_404(request, instance_id)


@router.get("/instances/{instance_id}/files/{kind}")
async def read_instance_file(request: Request, instance_id: str, kind: str) -> dict[str, Any]:
    instance_store = deps.store(request)
    file_kind = deps.file_kind(kind)
    if not instance_store.agent_dir(instance_id).exists():
        raise HTTPException(status_code=404, detail="instance_not_found")
    try:
        parsed = instance_store.read_parsed(instance_id, file_kind)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"instance_id": instance_id, "kind": kind, **parsed}


@router.put("/instances/{instance_id}/files/{kind}")
async def write_instance_file(
    request: Request,
    instance_id: str,
    kind: str,
    body: MarkdownUpdateBody,
) -> dict[str, Any]:
    instance_store = deps.store(request)
    file_kind = deps.file_kind(kind)
    if not instance_store.agent_dir(instance_id).exists():
        raise HTTPException(status_code=404, detail="instance_not_found")

    try:
        if body.content is not None:
            instance_store.write_file(instance_id, file_kind, body.content)
            parsed = instance_store.read_parsed(instance_id, file_kind)
        else:
            rendered = instance_store.write_parsed(
                instance_id,
                file_kind,
                frontmatter=body.frontmatter,
                body=body.body,
            )
            meta, text_body = instance_store.read_parsed(instance_id, file_kind)["frontmatter"], body.body
            parsed = {"frontmatter": meta, "body": text_body or "", "raw": rendered}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"instance_id": instance_id, "kind": kind, **parsed}


@router.post("/instances/{instance_id}/pause")
async def pause_instance(request: Request, instance_id: str) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    if not deps.store(request).agent_dir(instance_id).exists():
        raise HTTPException(status_code=404, detail="instance_not_found")
    await lifecycle_mgr.pause_instance(instance_id)
    return deps.instance_view_or_404(request, instance_id)


@router.post("/instances/{instance_id}/resume")
async def resume_instance(request: Request, instance_id: str) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    if not deps.store(request).agent_dir(instance_id).exists():
        raise HTTPException(status_code=404, detail="instance_not_found")
    await lifecycle_mgr.resume_instance(instance_id)
    return deps.instance_view_or_404(request, instance_id)


@router.get("/instances/{instance_id}/runs")
async def list_instance_runs(request: Request, instance_id: str) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    if not deps.store(request).agent_dir(instance_id).exists():
        raise HTTPException(status_code=404, detail="instance_not_found")
    return {"instance_id": instance_id, "runs": lifecycle_mgr.list_runs(instance_id)}


@router.get("/instances/{instance_id}/runs/current")
async def get_current_run(request: Request, instance_id: str) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    if not deps.store(request).agent_dir(instance_id).exists():
        raise HTTPException(status_code=404, detail="instance_not_found")
    current = lifecycle_mgr.current_run_view(instance_id)
    if current is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    return current


@router.get("/instances/{instance_id}/runs/{conversation_id}")
async def get_instance_run(
    request: Request, instance_id: str, conversation_id: str
) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    path = deps.store(request).agent_dir(instance_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="instance_not_found")
    run_path = path / "conversations" / conversation_id / "run.json"
    if not run_path.exists():
        raise HTTPException(status_code=404, detail="run_not_found")
    return lifecycle_mgr.run_view(instance_id, conversation_id)


@router.post("/instances/{instance_id}/runs", status_code=201)
async def start_instance_run(
    request: Request, instance_id: str, body: NewRunBody
) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    run_options = explicit_run_options(
        temperature=body.temperature,
        num_ctx=body.num_ctx,
    )
    try:
        return await lifecycle_mgr.start_new_run(
            instance_id,
            goal=body.goal,
            run_options=run_options,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc


@router.get("/instances/{instance_id}/conversations")
async def list_instance_conversations(request: Request, instance_id: str) -> dict[str, Any]:
    from gateway.agent_inspect import list_conversations

    instance_dir = deps.require_instance_dir(deps.store(request), instance_id)
    return {"instance_id": instance_id, "conversations": list_conversations(instance_dir)}


@router.get("/instances/{instance_id}/conversations/{conversation_id}")
async def get_instance_conversation(
    request: Request, instance_id: str, conversation_id: str
) -> dict[str, Any]:
    from gateway.agent_inspect import format_messages_for_display, get_conversation_messages

    instance_dir = deps.require_instance_dir(deps.store(request), instance_id)
    messages = get_conversation_messages(instance_dir, conversation_id)
    return {
        "instance_id": instance_id,
        "conversation_id": conversation_id,
        "messages": messages,
        "formatted": format_messages_for_display(messages),
    }


@router.get("/instances/{instance_id}/workspace")
async def list_instance_workspace(
    request: Request, instance_id: str, path: str = "."
) -> dict[str, Any]:
    from gateway.agent_inspect import list_workspace

    instance_dir = deps.require_instance_dir(deps.store(request), instance_id)
    try:
        entries = list_workspace(instance_dir, path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"instance_id": instance_id, "path": path, "entries": entries}


@router.get("/instances/{instance_id}/workspace/file")
async def read_instance_workspace_file(
    request: Request, instance_id: str, path: str
) -> dict[str, Any]:
    from gateway.agent_inspect import read_workspace_file

    instance_dir = deps.require_instance_dir(deps.store(request), instance_id)
    try:
        return {"instance_id": instance_id, **read_workspace_file(instance_dir, path)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, IsADirectoryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/instances/{instance_id}/databases")
async def list_instance_databases(request: Request, instance_id: str) -> dict[str, Any]:
    from gateway.agent_inspect import list_databases

    instance_dir = deps.require_instance_dir(deps.store(request), instance_id)
    return {"instance_id": instance_id, "databases": list_databases(instance_dir)}


@router.get("/instances/{instance_id}/databases/{db_name}")
async def get_instance_database(
    request: Request, instance_id: str, db_name: str
) -> dict[str, Any]:
    from gateway.agent_inspect import get_database_info

    instance_dir = deps.require_instance_dir(deps.store(request), instance_id)
    try:
        return {"instance_id": instance_id, **get_database_info(instance_dir, db_name)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/instances/{instance_id}/interactive/messages")
async def post_interactive_message(
    request: Request, instance_id: str, body: InteractiveMessageBody
) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    instance_store = deps.store(request)
    meta = {}
    try:
        meta = instance_store.read_instance_meta(instance_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc
    if meta.get("mode") != "interactive":
        raise HTTPException(status_code=422, detail="not_interactive_instance")
    try:
        await lifecycle_mgr.send_interactive(instance_id, body.message)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="instance_not_found") from exc
    session = request.app.state.interactive_manager.get(instance_id)
    return {
        "instance_id": instance_id,
        "state": session.state.value if session else "unknown",
        "last_reply": session.last_reply if session else None,
        "error": session.last_error if session else None,
    }


@router.get("/instances/{instance_id}/interactive")
async def poll_interactive(request: Request, instance_id: str) -> dict[str, Any]:
    session = request.app.state.interactive_manager.get(instance_id)
    if session is None:
        if not deps.store(request).agent_dir(instance_id).exists():
            raise HTTPException(status_code=404, detail="instance_not_found")
        return {
            "instance_id": instance_id,
            "state": "stopped",
            "last_reply": None,
            "error": None,
        }
    return {
        "instance_id": instance_id,
        "state": session.state.value,
        "last_reply": session.last_reply,
        "error": session.last_error,
    }


@router.get("/completions/recent")
async def recent_completions(request: Request, limit: int = 50) -> dict[str, Any]:
    events = deps.completions(request).recent(limit=limit)
    return {
        "completions": [
            {
                "instance_id": event.instance_id,
                "definition_id": event.definition_id,
                "completed_at": event.completed_at,
                "success": event.success,
                "error": event.error,
                "mode": event.mode,
            }
            for event in events
        ]
    }
