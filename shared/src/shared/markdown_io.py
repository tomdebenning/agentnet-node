"""Read and write Markdown files with YAML frontmatter."""

from __future__ import annotations

import re
from typing import Any

import yaml

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


def parse_markdown_document(content: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter dict, markdown body)."""
    text = content if content.endswith("\n") or not content else content + "\n"
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, content
    meta_raw, body = match.group(1), match.group(2)
    meta = yaml.safe_load(meta_raw) or {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def render_markdown_document(meta: dict[str, Any], body: str) -> str:
    """Serialize frontmatter and body to a Markdown file."""
    dumped = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).strip()
    body_text = body.rstrip("\n")
    if body_text:
        return f"---\n{dumped}\n---\n{body_text}\n"
    return f"---\n{dumped}\n---\n"


def default_config_markdown(
    agent_id: str,
    target_puller: str,
    model: str,
    *,
    temperature: float = 0.7,
    num_ctx: int = 8192,
) -> str:
    return render_markdown_document(
        {
            "agent_id": agent_id,
            "default_target_puller": target_puller,
            "default_model": model,
            "temperature": temperature,
            "num_ctx": num_ctx,
            "max_rounds_per_conversation": 50,
            "response_poll_interval_seconds": 2,
            "response_timeout_seconds": 300,
        },
        "# Agent configuration\n\nEdit frontmatter keys above to tune LLM routing and conversation limits.\n",
    )


def default_persona_markdown(name: str, role: str) -> str:
    return render_markdown_document(
        {"name": name, "role": role},
        f"# Persona\n\nYou are **{name}**, a {role}.\n\n"
        "- Answer clearly and helpfully.\n"
        "- Use your tools when they help.\n"
        "- Persist important facts to memory.\n",
    )


def default_skills_markdown() -> str:
    return render_markdown_document(
        {"version": 1},
        "# Skills\n\n"
        "Define what this agent is equipped to do and how it should use its tools.\n\n"
        "## Capabilities\n\n"
        "- Read and write files in `workspace/`\n"
        "- Query local SQLite databases\n"
        "- Search the web and fetch URLs (when configured)\n\n"
        "## Procedures\n\n"
        "(Add domain-specific skills, workflows, or tool usage notes here.)\n",
    )


def default_memory_markdown() -> str:
    return render_markdown_document({}, "# Memory\n\n(No memories yet.)\n")


def default_task_markdown() -> str:
    return render_markdown_document(
        {"conversation_id": "task"},
        "# Task\n\nDescribe what this agent should do when started.\n",
    )
