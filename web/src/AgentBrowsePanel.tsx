import { useEffect, useState } from "react";
import { api } from "./api";

function formatDatabase(info: Awaited<ReturnType<typeof api.getDatabase>>): string {
  const lines = [`Database: ${info.db_name}`, `Path: ${info.path}`, ""];
  for (const table of info.tables) {
    lines.push(`## Table ${table.name} (${table.row_count} rows)`);
    lines.push(`Columns: ${table.columns.join(", ")}`, "");
    for (const row of table.preview_rows) {
      lines.push(row.map(String).join(" | "));
    }
    lines.push("");
  }
  return lines.join("\n");
}

type Props = {
  agentId: string;
  mode: "conversations" | "workspace" | "databases";
};

export function AgentBrowsePanel({ agentId, mode }: Props) {
  const [items, setItems] = useState<string[]>([]);
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("");
  const [workspacePath, setWorkspacePath] = useState(".");
  const [entries, setEntries] = useState<
    { path: string; name: string; is_dir: boolean; size: number | null }[]
  >([]);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    setContent("");
    setSelected("");
    if (mode === "conversations") {
      api
        .listConversations(agentId)
        .then((rows) => setItems(rows.map((r) => r.conversation_id)))
        .catch((e: unknown) => setError(String(e)));
    } else if (mode === "databases") {
      api.listDatabases(agentId).then(setItems).catch((e: unknown) => setError(String(e)));
    } else {
      setWorkspacePath(".");
    }
  }, [agentId, mode]);

  useEffect(() => {
    if (mode !== "workspace") return;
    api
      .listWorkspace(agentId, workspacePath)
      .then((d) => setEntries(d.entries))
      .catch((e: unknown) => setError(String(e)));
  }, [agentId, mode, workspacePath]);

  async function openConversation(id: string) {
    setSelected(id);
    const data = await api.getConversation(agentId, id);
    setContent(data.formatted);
  }

  async function openDatabase(name: string) {
    setSelected(name);
    const data = await api.getDatabase(agentId, name);
    setContent(formatDatabase(data));
  }

  async function openWorkspaceEntry(path: string, isDir: boolean) {
    if (isDir) {
      setWorkspacePath(path);
      setContent("");
      return;
    }
    setSelected(path);
    const data = await api.readWorkspaceFile(agentId, path);
    setContent(data.content);
  }

  if (error) return <p className="error">{error}</p>;

  if (mode === "conversations") {
    return (
      <div className="browse-grid">
        <ul className="browse-list">
          {items.map((id) => (
            <li key={id}>
              <button className={selected === id ? "" : "secondary"} onClick={() => openConversation(id)}>
                {id}
              </button>
            </li>
          ))}
          {items.length === 0 && <li>(no conversations yet)</li>}
        </ul>
        <textarea readOnly value={content} />
      </div>
    );
  }

  if (mode === "databases") {
    return (
      <div className="browse-grid">
        <ul className="browse-list">
          {items.map((name) => (
            <li key={name}>
              <button className={selected === name ? "" : "secondary"} onClick={() => openDatabase(name)}>
                {name}
              </button>
            </li>
          ))}
          {items.length === 0 && <li>(no databases yet)</li>}
        </ul>
        <textarea readOnly value={content} />
      </div>
    );
  }

  return (
    <div className="browse-grid">
      <div>
        <p className="hint">workspace/{workspacePath === "." ? "" : workspacePath}</p>
        {workspacePath !== "." && (
          <button
            className="secondary"
            onClick={() => {
              const parts = workspacePath.split("/");
              parts.pop();
              setWorkspacePath(parts.length ? parts.join("/") : ".");
            }}
          >
            .. parent
          </button>
        )}
        <ul className="browse-list">
          {entries.map((entry) => (
            <li key={entry.path}>
              <button
                className={selected === entry.path ? "" : "secondary"}
                onClick={() => openWorkspaceEntry(entry.path, entry.is_dir)}
              >
                {entry.name}
                {entry.is_dir ? "/" : ` (${entry.size ?? 0}b)`}
              </button>
            </li>
          ))}
          {entries.length === 0 && <li>(empty)</li>}
        </ul>
      </div>
      <textarea readOnly value={content} />
    </div>
  );
}
