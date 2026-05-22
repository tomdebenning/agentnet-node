export type AgentSummary = {
  agent_id: string;
  path: string;
  process_state: string;
  pid: number | null;
};

export type AgentDetail = AgentSummary & {
  configured_agent_id: string;
  return_code: number | null;
  error: string | null;
  config: Record<string, unknown>;
};

export type MarkdownFile = {
  agent_id: string;
  kind: string;
  frontmatter: Record<string, unknown>;
  body: string;
  raw: string;
};

const API = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json();
}

export const api = {
  status: () => request<{ node_id: string; agent_count: number; running_agent_count: number }>("/status"),
  listAgents: () => request<{ agents: AgentSummary[] }>("/agents").then((d) => d.agents),
  getAgent: (id: string) => request<AgentDetail>(`/agents/${id}`),
  createAgent: (payload: {
    agent_id: string;
    target_puller?: string;
    model?: string;
    persona_name?: string;
    persona_role?: string;
  }) => request<AgentDetail>("/agents", { method: "POST", body: JSON.stringify(payload) }),
  deleteAgent: (id: string) => request<{ deleted: boolean }>(`/agents/${id}`, { method: "DELETE" }),
  startAgent: (id: string) => request<AgentDetail>(`/agents/${id}/start`, { method: "POST" }),
  stopAgent: (id: string) => request<AgentDetail>(`/agents/${id}/stop`, { method: "POST" }),
  readFile: (id: string, kind: string) => request<MarkdownFile>(`/agents/${id}/files/${kind}`),
  writeFile: (id: string, kind: string, content: string) =>
    request<MarkdownFile>(`/agents/${id}/files/${kind}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
};
