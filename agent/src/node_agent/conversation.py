"""Conversation loop for slim agents."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from shared.schemas import Message, Task
from node_agent.conversation_store import ConversationStore
from node_agent.gateway_client import GatewayClient
from node_agent.markdown_config import AgentSettings, llm_options_for_run, render_system_prompt
from node_agent.tools.definitions import tools_for_agent
from node_agent.tools.registry import ToolRegistry


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ResponseTimeout(Exception):
    pass


async def poll_for_response(
    *,
    gateway: GatewayClient,
    settings: AgentSettings,
    agent_id: str,
    conversation_id: str,
    round: int,
) -> Message:
    deadline = asyncio.get_event_loop().time() + settings.response_timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        responses = await gateway.get_responses(agent_id, max=10)
        for response in responses:
            if response.conversation_id == conversation_id and response.round == round:
                if response.error:
                    raise RuntimeError(response.error)
                if response.message is None:
                    raise RuntimeError("empty response from puller")
                return response.message
        await asyncio.sleep(settings.response_poll_interval_seconds)
    raise ResponseTimeout(
        f"No response for {conversation_id} round {round} within {settings.response_timeout_seconds}s"
    )


async def run_conversation_turn(
    *,
    settings: AgentSettings,
    gateway: GatewayClient,
    store: ConversationStore,
    tools: ToolRegistry,
    conversation_id: str,
    user_input: str,
    run_options: dict[str, Any] | None = None,
) -> str:
    existing = await store.get_messages(conversation_id)
    if not existing:
        await store.append_message(
            conversation_id,
            0,
            Message(role="system", content=render_system_prompt(settings)),
        )
        current_round = 1
    else:
        current_round = await store.get_max_round(conversation_id) + 1

    await store.append_message(
        conversation_id,
        current_round,
        Message(role="user", content=user_input),
    )

    while current_round <= settings.max_rounds_per_conversation:
        messages = await store.get_messages(conversation_id)
        task = Task(
            agent_id=settings.agent_id,
            conversation_id=conversation_id,
            round=current_round,
            target_puller=settings.default_target_puller,
            model=settings.default_model,
            messages=messages,
            tools=tools_for_agent(uses_memory=settings.uses_memory),
            options=llm_options_for_run(settings, run_options or {}),
            submitted_at=utcnow_iso(),
        )
        await gateway.post_task(task)
        assistant_message = await poll_for_response(
            gateway=gateway,
            settings=settings,
            agent_id=settings.agent_id,
            conversation_id=conversation_id,
            round=current_round,
        )
        await store.append_message(conversation_id, current_round, assistant_message)

        if not assistant_message.tool_calls:
            return assistant_message.content or ""

        for tool_call in assistant_message.tool_calls:
            tool_message = await tools.execute(tool_call)
            await store.append_message(conversation_id, current_round, tool_message)

        current_round += 1

    raise RuntimeError("max conversation rounds exceeded")
