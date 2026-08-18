"""Claim control-plane harness sessions targeted at builder-01 and run tools.

Factory reporter/editor stay on puller-01. This worker only consumes the
builder-01 puller queue, then sends LLM turns to the configured LLM puller.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import structlog

from node_agent.conversation import run_conversation_turn
from node_agent.conversation_store import ConversationStore
from node_agent.cp_client import ControlPlaneClient
from node_agent.markdown_config import load_agent_settings
from node_agent.tools.registry import ToolRegistry
from shared.markdown_io import (
    default_config_markdown,
    parse_markdown_document,
    render_markdown_document,
)
from shared.schemas import Message, PullerHeartbeat, Response, Task

logger = structlog.get_logger(__name__)

BUILDER_DEFINITION = "builder"
BUILDER_PULLER_NAME = "builder-01"
DEFAULT_LLM_PULLER = "puller-01"
DEFAULT_MODEL = "qwen3.5:27b"
DEFAULT_AGENT_ID = "builder-01"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_builder_target(
    *,
    definition: str | None,
    target_puller: str | None,
    default_puller: str = "puller-01",
) -> str:
    """Match control-plane session routing for the builder definition."""
    if target_puller and target_puller.strip():
        return target_puller.strip()
    if definition and definition.strip() == BUILDER_DEFINITION:
        return BUILDER_PULLER_NAME
    return default_puller


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_builder_instance(
    *,
    agents_root: Path,
    definitions_root: Path,
    agent_id: str,
    llm_puller: str,
    model: str,
) -> Path:
    instance = agents_root / agent_id
    definition = definitions_root / BUILDER_DEFINITION
    instance.mkdir(parents=True, exist_ok=True)
    (instance / "workspace").mkdir(exist_ok=True)
    (instance / "databases").mkdir(exist_ok=True)

    config_path = instance / "config.md"
    if not config_path.exists():
        config_path.write_text(
            default_config_markdown(agent_id, llm_puller, model),
            encoding="utf-8",
        )
    else:
        meta, body = parse_markdown_document(config_path.read_text(encoding="utf-8"))
        meta["agent_id"] = agent_id
        meta["default_target_puller"] = llm_puller
        meta["default_model"] = model
        meta["uses_memory"] = True
        config_path.write_text(render_markdown_document(meta, body), encoding="utf-8")

    for name in ("persona.md", "skills.md", "memory.md"):
        dest = instance / name
        src = definition / name
        if not dest.exists() and src.exists():
            dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        elif not dest.exists() and name == "memory.md":
            dest.write_text(
                render_markdown_document({}, "# Memory\n\n(No memories yet.)\n"),
                encoding="utf-8",
            )
    return instance


def _goal_from_task(task: Task) -> str:
    for message in task.messages:
        if message.role == "user" and (message.content or "").strip():
            return message.content.strip()
    return ""


async def _complete_session(
    client: ControlPlaneClient,
    task: Task,
    *,
    content: str,
    error: str | None,
) -> None:
    await client.post_response(
        Response(
            agent_id=task.agent_id,
            conversation_id=task.conversation_id,
            round=task.round,
            puller_name=BUILDER_PULLER_NAME,
            message=None if error else Message(role="assistant", content=content),
            error=error,
            completed_at=utcnow_iso(),
        )
    )


async def handle_session_task(
    task: Task,
    *,
    client: ControlPlaneClient,
    instance_dir: Path,
) -> None:
    goal = _goal_from_task(task)
    if not goal:
        await _complete_session(client, task, content="", error="empty session goal")
        return

    settings = load_agent_settings(instance_dir)
    store = ConversationStore(settings.paths.conversation_db)
    await store.connect()
    conversation_id = f"session-{task.conversation_id}"
    tools = ToolRegistry(settings, client, conversation_id=conversation_id)
    try:
        reply = await run_conversation_turn(
            settings=settings,
            gateway=client,
            store=store,
            tools=tools,
            conversation_id=conversation_id,
            user_input=goal,
        )
        await _complete_session(client, task, content=reply, error=None)
    except Exception as exc:  # noqa: BLE001 — session must always be completed
        logger.exception("builder_session_failed", conversation_id=task.conversation_id)
        await _complete_session(client, task, content="", error=str(exc))


async def worker_loop(
    *,
    control_plane_url: str,
    agents_root: Path,
    definitions_root: Path,
    builder_puller: str,
    llm_puller: str,
    model: str,
    poll_seconds: float,
    once: bool = False,
) -> None:
    agents_root.mkdir(parents=True, exist_ok=True)
    instance_dir = _ensure_builder_instance(
        agents_root=agents_root,
        definitions_root=definitions_root,
        agent_id=DEFAULT_AGENT_ID,
        llm_puller=llm_puller,
        model=model,
    )
    client = ControlPlaneClient(control_plane_url)
    logger.info(
        "builder_worker_start",
        control_plane=control_plane_url,
        builder_puller=builder_puller,
        llm_puller=llm_puller,
        instance=str(instance_dir),
    )
    try:
        while True:
            heartbeat = PullerHeartbeat(
                puller_name=builder_puller,
                status="idle",
                supported_models=[model],
                descriptive_info={
                    "kind": "builder-session-worker",
                    "definition": BUILDER_DEFINITION,
                    "llm_target_puller": llm_puller,
                    "not_a_newsroom_desk": True,
                },
            )
            try:
                await client.post_puller_heartbeat(heartbeat)
                task = await client.fetch_next_task(builder_puller)
            except Exception as exc:
                logger.warning("builder_poll_failed", error=str(exc))
                task = None
            if task is not None:
                logger.info(
                    "builder_session_claimed",
                    agent_id=task.agent_id,
                    conversation_id=task.conversation_id,
                    round=task.round,
                )
                busy = heartbeat.model_copy(update={"status": "busy"})
                try:
                    await client.post_puller_heartbeat(busy)
                except Exception:
                    pass
                await handle_session_task(task, client=client, instance_dir=instance_dir)
            if once:
                return
            await asyncio.sleep(poll_seconds)
    finally:
        await client.aclose()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    repo = _repo_root()
    parser = argparse.ArgumentParser(description="Builder session worker")
    parser.add_argument(
        "--control-plane-url",
        default=os.environ.get("CONTROL_PLANE_URL", "http://sg02:8000"),
    )
    parser.add_argument(
        "--agents-root",
        default=os.environ.get("AGENTS_ROOT", str(repo / "agents")),
    )
    parser.add_argument(
        "--definitions-root",
        default=os.environ.get("DEFINITIONS_ROOT", str(repo / "definitions")),
    )
    parser.add_argument(
        "--builder-puller",
        default=os.environ.get("BUILDER_PULLER_NAME", BUILDER_PULLER_NAME),
    )
    parser.add_argument(
        "--llm-puller",
        default=os.environ.get("LLM_TARGET_PULLER", DEFAULT_LLM_PULLER),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("BUILDER_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    asyncio.run(
        worker_loop(
            control_plane_url=args.control_plane_url,
            agents_root=Path(args.agents_root),
            definitions_root=Path(args.definitions_root),
            builder_puller=args.builder_puller,
            llm_puller=args.llm_puller,
            model=args.model,
            poll_seconds=args.poll_seconds,
            once=args.once,
        )
    )


if __name__ == "__main__":
    main()
