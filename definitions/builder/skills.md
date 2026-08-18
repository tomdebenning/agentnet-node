---
version: 1
---
# Skills

Software-builder toolkit. Not a newsroom desk.

## Tools

- `read_file` / `write_file` / `list_files` — workspace files
- `run_command` — workspace-sandboxed shell (cwd must stay in workspace/)
- `read_memory` / `write_memory` — persistent `memory.md`
- `web_search` / `fetch_url` — look up docs or APIs when needed
- `set_plan` / `advance_step` / `mark_goal_done` — run a goal to completion
- SQLite tools — only if the goal needs a local database

## Procedures

1. Read the goal. Call `set_plan` with concrete build steps.
2. Inspect the workspace before editing (`list_files`, `read_file`).
3. Implement with `write_file` and `run_command` (tests, linters, builds).
4. Record durable facts in memory (repo layout, commands that work).
5. `mark_goal_done` with artifact ids when the software goal is met.
