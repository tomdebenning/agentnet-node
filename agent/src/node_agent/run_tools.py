"""Agent tools for run planning, completion, and handoff."""

from __future__ import annotations

import json
from typing import Any

from shared.run_store import RunStore
from node_agent.gateway_client import GatewayClient
from node_agent.markdown_config import AgentSettings
from shared.run_store import utcnow_iso
from shared.schemas import Message, Task
from node_agent.tools.definitions import ALL_TOOLS


class RunToolContext:
    def __init__(
        self,
        *,
        settings: AgentSettings,
        gateway: GatewayClient,
        conversation_id: str,
    ) -> None:
        self.settings = settings
        self.gateway = gateway
        self.conversation_id = conversation_id
        self.store = RunStore(settings.paths.root)

    async def set_plan(self, steps: list[dict[str, Any]]) -> str:
        plan = self.store.set_plan_steps(self.conversation_id, steps)
        titles = ", ".join(step.title for step in plan.steps)
        return f"Plan set with {len(plan.steps)} steps: {titles}"

    async def advance_step(self, step_id: str) -> str:
        plan = self.store.advance_step(self.conversation_id, step_id)
        current = next(
            (step for step in plan.steps if step.status.value == "in_progress"),
            None,
        )
        if current is None:
            return f"Step {step_id} completed. No further steps."
        return f"Step {step_id} completed. Now on step {current.id}: {current.title}"

    async def mark_goal_done(self, product_artifact_ids: list[str]) -> str:
        run = self.store.mark_goal_done(self.conversation_id, product_artifact_ids)
        return (
            f"Goal marked done. Products: {', '.join(product_artifact_ids)}. "
            f"Run status: {run.status.value}"
        )

    async def send_artifact_to_agent(
        self,
        target_agent_id: str,
        artifact_id: str,
        prompt: str,
    ) -> str:
        artifact = self.store.get_artifact(self.conversation_id, artifact_id)
        handoff = {
            "artifact_id": artifact.artifact_id,
            "type": artifact.type,
            "summary": artifact.summary,
            "ref": artifact.ref,
            "from_agent_id": self.settings.agent_id,
            "from_conversation_id": self.conversation_id,
        }
        content = (
            f"{prompt.strip()}\n\n"
            f"---\nArtifact handoff:\n```json\n{json.dumps(handoff, indent=2)}\n```"
        )
        task = Task(
            agent_id=target_agent_id,
            conversation_id=f"handoff-{artifact_id}",
            round=1,
            target_puller=self.settings.default_target_puller,
            model=self.settings.default_model,
            messages=[Message(role="user", content=content)],
            tools=ALL_TOOLS,
            options={"temperature": self.settings.temperature, "num_ctx": self.settings.num_ctx},
            submitted_at=utcnow_iso(),
        )
        await self.gateway.post_task(task)
        return f"Artifact {artifact_id} sent to agent {target_agent_id}"
