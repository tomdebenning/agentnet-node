import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AgentDetail, AgentSummary, api } from "./api";

type Props = {
  createMode?: boolean;
  detailMode?: boolean;
};

export default function App({ createMode, detailMode }: Props) {
  const params = useParams();
  const navigate = useNavigate();
  const [agents, setAgents] = useState<AgentSummary[]>([]);
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [fileKind, setFileKind] = useState("config");
  const [editor, setEditor] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const agentId = params.agentId || "";

  useEffect(() => {
    if (createMode) return;
    api.status().then((s) => setStatus(`${s.node_id} · ${s.running_agent_count}/${s.agent_count} running`)).catch(() => undefined);
    if (detailMode && agentId) {
      Promise.all([api.getAgent(agentId), api.readFile(agentId, "config")])
        .then(([info, file]) => {
          setDetail(info);
          setEditor(file.raw);
        })
        .catch((exc) => setError(String(exc)));
      return;
    }
    api.listAgents().then(setAgents).catch((exc) => setError(String(exc)));
  }, [createMode, detailMode, agentId, fileKind]);

  async function loadFile(kind: string) {
    if (!agentId) return;
    setFileKind(kind);
    const file = await api.readFile(agentId, kind);
    setEditor(file.raw);
  }

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const created = await api.createAgent({
        agent_id: String(form.get("agent_id") || ""),
        target_puller: String(form.get("target_puller") || "puller-01"),
        model: String(form.get("model") || "llama3.1:8b"),
        persona_name: String(form.get("persona_name") || ""),
        persona_role: String(form.get("persona_role") || "helpful assistant"),
      });
      navigate(`/agents/${created.agent_id}`);
    } catch (exc) {
      setError(String(exc));
    }
  }

  if (createMode) {
    return (
      <div className="card">
        <h2>Create agent</h2>
        {error && <p className="error">{error}</p>}
        <form className="form-grid" onSubmit={onCreate}>
          <label>Agent ID<input name="agent_id" required /></label>
          <label>Target puller<input name="target_puller" defaultValue="puller-01" /></label>
          <label>Model<input name="model" defaultValue="llama3.1:8b" /></label>
          <label>Persona name<input name="persona_name" /></label>
          <label>Persona role<input name="persona_role" defaultValue="helpful assistant" /></label>
          <button type="submit">Create</button>
        </form>
      </div>
    );
  }

  if (detailMode && agentId) {
    return (
      <div>
        <p>{status}</p>
        {error && <p className="error">{error}</p>}
        <div className="card">
          <h2>{agentId}</h2>
          {detail && (
            <p>
              <span className={`badge ${detail.process_state}`}>{detail.process_state}</span>
              {" "}PID: {detail.pid ?? "-"}
            </p>
          )}
          <div className="row tabs">
            {["config", "persona", "memory"].map((kind) => (
              <button key={kind} className={fileKind === kind ? "" : "secondary"} onClick={() => loadFile(kind)}>
                {kind}
              </button>
            ))}
          </div>
          <textarea value={editor} onChange={(e) => setEditor(e.target.value)} />
          <div className="row">
            <button onClick={async () => {
              try {
                await api.writeFile(agentId, fileKind, editor);
                setError("");
              } catch (exc) {
                setError(String(exc));
              }
            }}>Save</button>
            <button className="secondary" onClick={async () => {
              const info = await api.startAgent(agentId);
              setDetail(info);
            }}>Start</button>
            <button className="secondary" onClick={async () => {
              const info = await api.stopAgent(agentId);
              setDetail(info);
            }}>Stop</button>
            <button className="danger" onClick={async () => {
              await api.deleteAgent(agentId);
              navigate("/");
            }}>Delete</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <p>{status}</p>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <h2>Agents</h2>
        {agents.length === 0 ? <p>No agents yet.</p> : (
          <ul>
            {agents.map((agent) => (
              <li key={agent.agent_id}>
                <Link to={`/agents/${agent.agent_id}`}>{agent.agent_id}</Link>
                {" "}
                <span className={`badge ${agent.process_state}`}>{agent.process_state}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
