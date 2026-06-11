export type InstanceSummary = {
  instance_id: string;
  definition_id: string | null;
  mode: string | null;
  instance_status: string | null;
  spawned_at: string | null;
  path: string;
  process_state: string;
  pid: number | null;
  error: string | null;
  config: Record<string, unknown>;
  current_conversation_id?: string | null;
  current_run?: RunSummary | null;
};

export type RunDocument = {
  conversation_id: string;
  goal: string;
  status: string;
  current_step_id: string | null;
  options: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
};

export type RunPlanStep = {
  id: string;
  title: string;
  status: string;
  order: number;
};

export type RunPlan = { steps: RunPlanStep[] };

export type RunArtifact = {
  artifact_id: string;
  step_id: string | null;
  type: string;
  summary: string;
  ref: Record<string, unknown>;
  created_at: string;
};

export type RunProducts = { product_artifact_ids: string[] };

export type RunSummary = {
  instance_id: string;
  conversation_id: string;
  run: RunDocument;
  plan: RunPlan;
  artifacts: RunArtifact[];
  products: RunProducts;
};

export type DefinitionReviewStatus = {
  persona_reviewed: boolean;
  skills_reviewed: boolean;
  spawnable: boolean;
};

export type DefinitionSummary = {
  definition_id: string;
  path: string;
  uses_memory: boolean;
  persona_name?: string | null;
  persona_role?: string | null;
  created_at?: string;
  updated_at?: string;
} & DefinitionReviewStatus;

export type DefinitionDetail = {
  definition_id: string;
  meta: Record<string, unknown>;
  uses_memory: boolean;
  persona_raw: string;
  skills_raw: string;
  memory_raw: string;
} & DefinitionReviewStatus;

export type CompletionEvent = {
  instance_id: string;
  definition_id: string | null;
  completed_at: string;
  success: boolean;
  error: string | null;
  mode: string;
};

export type MarkdownFile = {
  instance_id: string;
  kind: string;
  frontmatter: Record<string, unknown>;
  body: string;
  raw: string;
};

export type InteractivePoll = {
  instance_id: string;
  state: string;
  last_reply: string | null;
  error: string | null;
};

export type SpawnDefaults = {
  model: string;
  target_puller: string;
  temperature: number;
  num_ctx: number;
};

const API = "/api";
const FLEET = `${API}/fleet`;
const DEFINITIONS = `${API}/definitions`;

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

async function fleetRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${FLEET}${path}`, {
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

async function definitionRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${DEFINITIONS}${path}`, {
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
  spawnDefaults: () => request<SpawnDefaults>("/spawn-defaults"),
  status: () =>
    request<{
      node_id: string;
      agent_count: number;
      definition_count: number;
      instance_count: number;
      running_agent_count: number;
      interactive_session_count: number;
      control_plane_url: string;
      control_plane_connected: boolean;
      control_plane_error: string | null;
    }>("/status"),
  listDefinitions: () =>
    definitionRequest<{ definitions: DefinitionSummary[] }>("").then((d) => d.definitions),
  getDefinition: (id: string) => definitionRequest<DefinitionDetail>(`/${id}`),
  createDefinition: (payload: {
    definition_id: string;
    persona_name?: string;
    persona_role?: string;
    persona_content?: string;
    skills_content?: string;
    memory_content?: string;
    uses_memory?: boolean;
    persona_reviewed?: boolean;
    skills_reviewed?: boolean;
  }) =>
    definitionRequest<{ definition_id: string } & DefinitionReviewStatus>("", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  writeDefinitionPersona: (id: string, content: string, markReviewed = false) =>
    definitionRequest<{ definition_id: string; persona: { raw: string } } & DefinitionReviewStatus>(
      `/${id}/files/persona`,
      {
        method: "PUT",
        body: JSON.stringify({ content, mark_reviewed: markReviewed }),
      },
    ),
  writeDefinitionSkills: (id: string, content: string, markReviewed = false) =>
    definitionRequest<{ definition_id: string; skills: { raw: string } } & DefinitionReviewStatus>(
      `/${id}/files/skills`,
      {
        method: "PUT",
        body: JSON.stringify({ content, mark_reviewed: markReviewed }),
      },
    ),
  writeDefinitionMemory: (id: string, content: string) =>
    definitionRequest<{ definition_id: string; memory: { raw: string } }>(
      `/${id}/files/memory`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    ),
  setDefinitionUsesMemory: (id: string, usesMemory: boolean) =>
    definitionRequest<{ definition_id: string; uses_memory: boolean; memory_raw: string } & DefinitionReviewStatus>(
      `/${id}/uses-memory`,
      {
        method: "PUT",
        body: JSON.stringify({ uses_memory: usesMemory }),
      },
    ),
  deleteDefinition: (id: string) =>
    definitionRequest<{ deleted: boolean }>(`/${id}`, { method: "DELETE" }),
  spawnInstance: (
    definitionId: string,
    payload: {
      mode: "autonomous" | "interactive";
      base_name: string;
      target_puller?: string;
      model?: string;
      temperature?: number;
      num_ctx?: number;
      goal?: string;
      task_body?: string;
      conversation_id?: string;
      resume?: boolean;
      auto_start?: boolean;
      persona_content?: string;
      skills_content?: string;
    },
  ) =>
    definitionRequest<InstanceSummary>(`/${definitionId}/spawn`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listInstances: () =>
    fleetRequest<{ instances: InstanceSummary[] }>("/instances").then((d) => d.instances),
  getInstance: (id: string) => fleetRequest<InstanceSummary>(`/instances/${id}`),
  createInstance: (payload: {
    instance_id: string;
    target_puller?: string;
    model?: string;
    temperature?: number;
    num_ctx?: number;
    persona_name?: string;
    persona_role?: string;
  }) =>
    fleetRequest<InstanceSummary>("/instances", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deleteInstance: (id: string) =>
    fleetRequest<{ deleted: boolean }>(`/instances/${id}`, { method: "DELETE" }),
  startInstance: (id: string) =>
    fleetRequest<InstanceSummary>(`/instances/${id}/start`, { method: "POST" }),
  stopInstance: (id: string) =>
    fleetRequest<InstanceSummary>(`/instances/${id}/stop`, { method: "POST" }),
  pauseInstance: (id: string) =>
    fleetRequest<InstanceSummary>(`/instances/${id}/pause`, { method: "POST" }),
  resumeInstance: (id: string) =>
    fleetRequest<InstanceSummary>(`/instances/${id}/resume`, { method: "POST" }),
  listRuns: (id: string) =>
    fleetRequest<{ runs: RunSummary[] }>(`/instances/${id}/runs`).then((d) => d.runs),
  getCurrentRun: (id: string) =>
    fleetRequest<RunSummary>(`/instances/${id}/runs/current`),
  startRun: (
    id: string,
    goal: string,
    options?: { temperature?: number; num_ctx?: number },
  ) =>
    fleetRequest<RunSummary>(`/instances/${id}/runs`, {
      method: "POST",
      body: JSON.stringify({ goal, ...options }),
    }),
  recentCompletions: (limit = 50) =>
    fleetRequest<{ completions: CompletionEvent[] }>(`/completions/recent?limit=${limit}`).then(
      (d) => d.completions,
    ),
  postInteractiveMessage: (instanceId: string, message: string) =>
    fleetRequest<InteractivePoll>(`/instances/${instanceId}/interactive/messages`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  pollInteractive: (instanceId: string) =>
    fleetRequest<InteractivePoll>(`/instances/${instanceId}/interactive`),
  readFile: (id: string, kind: string) =>
    fleetRequest<MarkdownFile>(`/instances/${id}/files/${kind}`),
  writeFile: (id: string, kind: string, content: string) =>
    fleetRequest<MarkdownFile>(`/instances/${id}/files/${kind}`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),
  listConversations: (id: string) =>
    fleetRequest<{ conversations: { conversation_id: string; message_count: number; status: string }[] }>(
      `/instances/${id}/conversations`,
    ).then((d) => d.conversations),
  getConversation: (id: string, conversationId: string) =>
    fleetRequest<{ formatted: string; messages: unknown[] }>(
      `/instances/${id}/conversations/${conversationId}`,
    ),
  listWorkspace: (id: string, path = ".") =>
    fleetRequest<{ path: string; entries: { path: string; name: string; is_dir: boolean; size: number | null }[] }>(
      `/instances/${id}/workspace?path=${encodeURIComponent(path)}`,
    ),
  readWorkspaceFile: (id: string, path: string) =>
    fleetRequest<{ path: string; content: string; truncated: boolean }>(
      `/instances/${id}/workspace/file?path=${encodeURIComponent(path)}`,
    ),
  listDatabases: (id: string) =>
    fleetRequest<{ databases: string[] }>(`/instances/${id}/databases`).then((d) => d.databases),
  getDatabase: (id: string, dbName: string) =>
    fleetRequest<{
      db_name: string;
      path: string;
      tables: {
        name: string;
        row_count: number;
        columns: string[];
        preview_rows: unknown[][];
      }[];
    }>(`/instances/${id}/databases/${dbName}`),
};
