"""Agent definition library API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from shared.markdown_io import parse_markdown_document
from gateway.routes import deps
from gateway.spawn_defaults import resolved_instance_config, run_options_for_spawn

definition_ops = APIRouter()


class CreateDefinitionBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    definition_id: str = Field(validation_alias=AliasChoices("definition_id", "template_id"))
    persona_name: str | None = None
    persona_role: str = "helpful assistant"
    persona_content: str | None = None
    skills_content: str | None = None
    memory_content: str | None = None
    uses_memory: bool = True
    persona_reviewed: bool = False
    skills_reviewed: bool = False


class DefinitionFileUpdateBody(BaseModel):
    content: str
    mark_reviewed: bool = False


class SpawnInstanceBody(BaseModel):
    mode: Literal["autonomous", "interactive"] = "autonomous"
    base_name: str = Field(min_length=1)
    target_puller: str | None = None
    model: str | None = None
    temperature: float | None = None
    num_ctx: int | None = None
    goal: str = ""
    task_body: str = ""
    conversation_id: str | None = None
    resume: bool = False
    auto_start: bool = True
    persona_content: str | None = None
    skills_content: str | None = None


def _definition_id_from_path(definition_id: str) -> str:
    return definition_id.strip()


@definition_ops.get("")
async def list_definitions(request: Request) -> dict[str, Any]:
    registry = deps.definition_registry(request)
    items = [entry.to_dict() for entry in registry.list_all()]
    return {"definitions": items}


class DefinitionUsesMemoryBody(BaseModel):
    uses_memory: bool


@definition_ops.post("", status_code=201)
async def create_definition(request: Request, body: CreateDefinitionBody) -> dict[str, Any]:
    if not (body.persona_reviewed and body.skills_reviewed):
        raise HTTPException(
            status_code=422,
            detail="definition_not_ready: review persona and skills before creating",
        )
    store = deps.definitions(request)
    definition_id = _definition_id_from_path(body.definition_id)
    try:
        path = store.create_definition(
            definition_id,
            persona_name=body.persona_name,
            persona_role=body.persona_role,
            persona_content=body.persona_content,
            skills_content=body.skills_content,
            memory_content=body.memory_content,
            uses_memory=body.uses_memory,
            persona_reviewed=body.persona_reviewed,
            skills_reviewed=body.skills_reviewed,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    review = store.read_review_status(definition_id)
    uses_memory = store.read_uses_memory(definition_id)
    registry = deps.definition_registry(request)
    entry = registry.get(definition_id)
    result = {
        "definition_id": definition_id,
        "path": str(path),
        "uses_memory": uses_memory,
        **review,
    }
    if entry is not None:
        result["persona_name"] = entry.persona_name
        result["persona_role"] = entry.persona_role
    return result


@definition_ops.get("/{definition_id}")
async def get_definition(request: Request, definition_id: str) -> dict[str, Any]:
    store = deps.definitions(request)
    definition_id = _definition_id_from_path(definition_id)
    if not store.definition_dir(definition_id).exists():
        raise HTTPException(status_code=404, detail="definition_not_found")
    persona_raw = store.read_persona_raw(definition_id)
    persona_meta, persona_body = parse_markdown_document(persona_raw)
    skills_raw = store.read_skills_raw(definition_id)
    skills_meta, skills_body = parse_markdown_document(skills_raw)
    memory_raw = store.read_memory_raw(definition_id)
    memory_meta, memory_body = parse_markdown_document(memory_raw)
    review = store.read_review_status(definition_id)
    meta = store.read_meta(definition_id)
    uses_memory = store.read_uses_memory(definition_id)
    return {
        "definition_id": definition_id,
        "meta": meta,
        "uses_memory": uses_memory,
        "persona_raw": persona_raw,
        "persona": {"frontmatter": persona_meta, "body": persona_body, "raw": persona_raw},
        "skills_raw": skills_raw,
        "skills": {"frontmatter": skills_meta, "body": skills_body, "raw": skills_raw},
        "memory_raw": memory_raw,
        "memory": {"frontmatter": memory_meta, "body": memory_body, "raw": memory_raw},
        **review,
    }


@definition_ops.put("/{definition_id}/uses-memory")
async def set_definition_uses_memory(
    request: Request, definition_id: str, body: DefinitionUsesMemoryBody
) -> dict[str, Any]:
    store = deps.definitions(request)
    definition_id = _definition_id_from_path(definition_id)
    if not store.definition_dir(definition_id).exists():
        raise HTTPException(status_code=404, detail="definition_not_found")
    try:
        meta = store.set_uses_memory(definition_id, body.uses_memory)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    memory_raw = store.read_memory_raw(definition_id)
    return {
        "definition_id": definition_id,
        "uses_memory": bool(meta.get("uses_memory")),
        "memory_raw": memory_raw,
        **store.read_review_status(definition_id),
    }


@definition_ops.put("/{definition_id}/files/persona")
async def write_definition_persona(
    request: Request, definition_id: str, body: DefinitionFileUpdateBody
) -> dict[str, Any]:
    store = deps.definitions(request)
    definition_id = _definition_id_from_path(definition_id)
    if not store.definition_dir(definition_id).exists():
        raise HTTPException(status_code=404, detail="definition_not_found")
    store.write_persona_raw(definition_id, body.content)
    if body.mark_reviewed:
        store.set_review_flag(definition_id, persona_reviewed=True)
    persona_raw = store.read_persona_raw(definition_id)
    meta, text_body = parse_markdown_document(persona_raw)
    return {
        "definition_id": definition_id,
        "persona": {"frontmatter": meta, "body": text_body, "raw": persona_raw},
        **store.read_review_status(definition_id),
    }


@definition_ops.put("/{definition_id}/files/skills")
async def write_definition_skills(
    request: Request, definition_id: str, body: DefinitionFileUpdateBody
) -> dict[str, Any]:
    store = deps.definitions(request)
    definition_id = _definition_id_from_path(definition_id)
    if not store.definition_dir(definition_id).exists():
        raise HTTPException(status_code=404, detail="definition_not_found")
    store.write_skills_raw(definition_id, body.content)
    if body.mark_reviewed:
        store.set_review_flag(definition_id, skills_reviewed=True)
    skills_raw = store.read_skills_raw(definition_id)
    meta, text_body = parse_markdown_document(skills_raw)
    return {
        "definition_id": definition_id,
        "skills": {"frontmatter": meta, "body": text_body, "raw": skills_raw},
        **store.read_review_status(definition_id),
    }


@definition_ops.put("/{definition_id}/files/memory")
async def write_definition_memory(
    request: Request, definition_id: str, body: DefinitionFileUpdateBody
) -> dict[str, Any]:
    store = deps.definitions(request)
    definition_id = _definition_id_from_path(definition_id)
    if not store.definition_dir(definition_id).exists():
        raise HTTPException(status_code=404, detail="definition_not_found")
    try:
        store.write_memory_raw(definition_id, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    memory_raw = store.read_memory_raw(definition_id)
    meta, text_body = parse_markdown_document(memory_raw)
    return {
        "definition_id": definition_id,
        "memory": {"frontmatter": meta, "body": text_body, "raw": memory_raw},
        **store.read_review_status(definition_id),
    }


@definition_ops.post("/{definition_id}/mark-reviewed")
async def mark_definition_reviewed(
    request: Request, definition_id: str, body: dict[str, bool]
) -> dict[str, Any]:
    store = deps.definitions(request)
    definition_id = _definition_id_from_path(definition_id)
    if not store.definition_dir(definition_id).exists():
        raise HTTPException(status_code=404, detail="definition_not_found")
    review = store.set_review_flag(
        definition_id,
        persona_reviewed=body.get("persona_reviewed"),
        skills_reviewed=body.get("skills_reviewed"),
    )
    return {"definition_id": definition_id, **review}


@definition_ops.delete("/{definition_id}")
async def delete_definition(request: Request, definition_id: str) -> dict[str, Any]:
    store = deps.definitions(request)
    definition_id = _definition_id_from_path(definition_id)
    try:
        store.delete_definition(definition_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="definition_not_found") from exc
    return {"deleted": True, "definition_id": definition_id}


@definition_ops.post("/{definition_id}/spawn", status_code=201)
async def spawn_from_definition(
    request: Request, definition_id: str, body: SpawnInstanceBody
) -> dict[str, Any]:
    lifecycle_mgr = deps.lifecycle(request)
    definition_id = _definition_id_from_path(definition_id)
    if not deps.definitions(request).definition_dir(definition_id).exists():
        raise HTTPException(status_code=404, detail="definition_not_found")
    review = deps.definitions(request).read_review_status(definition_id)
    if not review["spawnable"]:
        raise HTTPException(
            status_code=422,
            detail="definition_not_spawnable: review persona and skills before spawning",
        )
    config = request.app.state.config
    resolved = resolved_instance_config(
        config,
        model=body.model,
        target_puller=body.target_puller,
        temperature=body.temperature,
        num_ctx=body.num_ctx,
    )
    run_options = run_options_for_spawn(
        config,
        temperature=body.temperature,
        num_ctx=body.num_ctx,
    )
    try:
        return await lifecycle_mgr.spawn(
            definition_id,
            base_name=body.base_name,
            target_puller=resolved["target_puller"],
            model=resolved["model"],
            temperature=resolved["temperature"],
            num_ctx=resolved["num_ctx"],
            mode=body.mode,
            goal=body.goal,
            task_body=body.task_body,
            conversation_id=body.conversation_id,
            resume=body.resume,
            auto_start=body.auto_start,
            persona_content=body.persona_content,
            skills_content=body.skills_content,
            run_options=run_options,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


router = APIRouter()
router.include_router(definition_ops, prefix="/api/definitions", tags=["definitions"])
