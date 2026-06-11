"""Per-instance run state: goal, plan, artifacts, and products."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class RunStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    DONE = "done"
    ERROR = "error"


class StepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


ArtifactType = Literal["file", "json", "db"]


class PlanStep(BaseModel):
    id: str
    title: str
    status: StepStatus = StepStatus.PENDING
    order: int = 0


class PlanDocument(BaseModel):
    steps: list[PlanStep] = Field(default_factory=list)


class RunDocument(BaseModel):
    conversation_id: str
    goal: str = ""
    status: RunStatus = RunStatus.PENDING
    current_step_id: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utcnow_iso)
    updated_at: str = Field(default_factory=utcnow_iso)
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None


class ArtifactDocument(BaseModel):
    artifact_id: str
    step_id: str | None = None
    type: ArtifactType
    summary: str = ""
    ref: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utcnow_iso)


class ProductsDocument(BaseModel):
    product_artifact_ids: list[str] = Field(default_factory=list)


class RunStore:
    """Read/write run data under `{instance_root}/conversations/{conversation_id}/`."""

    def __init__(self, instance_root: Path) -> None:
        self.instance_root = instance_root.expanduser().resolve()

    @staticmethod
    def conversations_root(instance_root: Path) -> Path:
        return instance_root.expanduser().resolve() / "conversations"

    def conversation_dir(self, conversation_id: str) -> Path:
        return self.conversations_root(self.instance_root) / conversation_id

    def _run_path(self, conversation_id: str) -> Path:
        return self.conversation_dir(conversation_id) / "run.json"

    def _plan_path(self, conversation_id: str) -> Path:
        return self.conversation_dir(conversation_id) / "plan.json"

    def _products_path(self, conversation_id: str) -> Path:
        return self.conversation_dir(conversation_id) / "products.json"

    def _artifacts_dir(self, conversation_id: str) -> Path:
        return self.conversation_dir(conversation_id) / "artifacts"

    def create_run(
        self,
        conversation_id: str,
        *,
        goal: str = "",
        options: dict[str, Any] | None = None,
    ) -> RunDocument:
        conv_dir = self.conversation_dir(conversation_id)
        conv_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir(conversation_id).mkdir(parents=True, exist_ok=True)
        run = RunDocument(
            conversation_id=conversation_id,
            goal=goal.strip(),
            options=dict(options or {}),
        )
        self._write_json(self._run_path(conversation_id), run.model_dump())
        self._write_json(self._plan_path(conversation_id), PlanDocument().model_dump())
        self._write_json(
            self._products_path(conversation_id),
            ProductsDocument().model_dump(),
        )
        return run

    def get_run(self, conversation_id: str) -> RunDocument:
        data = self._read_json(self._run_path(conversation_id))
        return RunDocument.model_validate(data)

    def save_run(self, run: RunDocument) -> RunDocument:
        run.updated_at = utcnow_iso()
        self._write_json(self._run_path(run.conversation_id), run.model_dump())
        return run

    def update_run_status(
        self,
        conversation_id: str,
        status: RunStatus,
        *,
        error: str | None = None,
    ) -> RunDocument:
        run = self.get_run(conversation_id)
        run.status = status
        run.error = error
        if status == RunStatus.EXECUTING and run.started_at is None:
            run.started_at = utcnow_iso()
        if status == RunStatus.DONE:
            run.completed_at = utcnow_iso()
        return self.save_run(run)

    def set_goal(self, conversation_id: str, goal: str) -> RunDocument:
        run = self.get_run(conversation_id)
        run.goal = goal.strip()
        return self.save_run(run)

    def get_plan(self, conversation_id: str) -> PlanDocument:
        path = self._plan_path(conversation_id)
        if not path.exists():
            return PlanDocument()
        return PlanDocument.model_validate(self._read_json(path))

    def save_plan(self, conversation_id: str, plan: PlanDocument) -> PlanDocument:
        self._write_json(self._plan_path(conversation_id), plan.model_dump())
        run = self.get_run(conversation_id)
        if run.status == RunStatus.PENDING:
            run.status = RunStatus.PLANNING
            self.save_run(run)
        return plan

    def set_plan_steps(self, conversation_id: str, steps: list[dict[str, Any]]) -> PlanDocument:
        parsed: list[PlanStep] = []
        for index, step in enumerate(steps):
            step_id = str(step.get("id") or f"step-{index + 1}")
            title = str(step.get("title") or step_id)
            parsed.append(PlanStep(id=step_id, title=title, order=index))
        plan = PlanDocument(steps=parsed)
        self.save_plan(conversation_id, plan)
        if parsed:
            run = self.get_run(conversation_id)
            run.current_step_id = parsed[0].id
            run.status = RunStatus.EXECUTING
            self.save_run(run)
            plan.steps[0].status = StepStatus.IN_PROGRESS
            self.save_plan(conversation_id, plan)
        return plan

    def advance_step(self, conversation_id: str, step_id: str) -> PlanDocument:
        plan = self.get_plan(conversation_id)
        found = False
        next_pending: PlanStep | None = None
        for step in sorted(plan.steps, key=lambda s: s.order):
            if step.id == step_id:
                step.status = StepStatus.DONE
                found = True
                continue
            if found and step.status == StepStatus.PENDING and next_pending is None:
                next_pending = step
        if not found:
            raise ValueError(f"unknown step: {step_id}")
        if next_pending is not None:
            next_pending.status = StepStatus.IN_PROGRESS
            run = self.get_run(conversation_id)
            run.current_step_id = next_pending.id
            run.status = RunStatus.EXECUTING
            self.save_run(run)
        self.save_plan(conversation_id, plan)
        return plan

    def record_artifact(
        self,
        conversation_id: str,
        *,
        artifact_type: ArtifactType,
        summary: str,
        ref: dict[str, Any],
        step_id: str | None = None,
    ) -> ArtifactDocument:
        run = self.get_run(conversation_id)
        if step_id is None:
            step_id = run.current_step_id
        artifact_id = uuid.uuid4().hex[:12]
        artifact = ArtifactDocument(
            artifact_id=artifact_id,
            step_id=step_id,
            type=artifact_type,
            summary=summary,
            ref=ref,
        )
        path = self._artifacts_dir(conversation_id) / f"{artifact_id}.json"
        self._write_json(path, artifact.model_dump())
        if run.status in {RunStatus.PENDING, RunStatus.PLANNING}:
            run.status = RunStatus.EXECUTING
            self.save_run(run)
        return artifact

    def get_artifact(self, conversation_id: str, artifact_id: str) -> ArtifactDocument:
        path = self._artifacts_dir(conversation_id) / f"{artifact_id}.json"
        if not path.exists():
            raise FileNotFoundError(artifact_id)
        return ArtifactDocument.model_validate(self._read_json(path))

    def list_artifacts(self, conversation_id: str) -> list[ArtifactDocument]:
        artifacts_dir = self._artifacts_dir(conversation_id)
        if not artifacts_dir.exists():
            return []
        items: list[ArtifactDocument] = []
        for path in sorted(artifacts_dir.glob("*.json")):
            items.append(ArtifactDocument.model_validate(self._read_json(path)))
        return items

    def get_products(self, conversation_id: str) -> ProductsDocument:
        path = self._products_path(conversation_id)
        if not path.exists():
            return ProductsDocument()
        return ProductsDocument.model_validate(self._read_json(path))

    def mark_goal_done(self, conversation_id: str, product_artifact_ids: list[str]) -> RunDocument:
        artifacts = {item.artifact_id: item for item in self.list_artifacts(conversation_id)}
        for artifact_id in product_artifact_ids:
            if artifact_id not in artifacts:
                raise ValueError(f"unknown artifact: {artifact_id}")
        products = ProductsDocument(product_artifact_ids=list(product_artifact_ids))
        self._write_json(self._products_path(conversation_id), products.model_dump())
        plan = self.get_plan(conversation_id)
        for step in plan.steps:
            if step.status != StepStatus.DONE:
                step.status = StepStatus.DONE
        self.save_plan(conversation_id, plan)
        run = self.get_run(conversation_id)
        run.status = RunStatus.DONE
        run.completed_at = utcnow_iso()
        return self.save_run(run)

    def list_runs(self) -> list[RunDocument]:
        root = self.conversations_root(self.instance_root)
        if not root.exists():
            return []
        runs: list[RunDocument] = []
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "run.json").exists():
                runs.append(self.get_run(child.name))
        return runs

    def run_summary(self, conversation_id: str) -> dict[str, Any]:
        run = self.get_run(conversation_id)
        plan = self.get_plan(conversation_id)
        artifacts = self.list_artifacts(conversation_id)
        products = self.get_products(conversation_id)
        return {
            "run": run.model_dump(),
            "plan": plan.model_dump(),
            "artifacts": [item.model_dump() for item in artifacts],
            "products": products.model_dump(),
        }

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
