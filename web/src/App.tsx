import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "./api";
import { useSpawnDefaults } from "./useSpawnDefaults";

type Props = {
  createMode?: boolean;
  detailMode?: boolean;
  redirectToInstance?: boolean;
};

export default function App({ createMode, detailMode, redirectToInstance }: Props) {
  const params = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const { spawnDefaults, loading, setSpawnDefaults } = useSpawnDefaults();
  const agentId = params.agentId || "";

  useEffect(() => {
    if (detailMode && redirectToInstance && agentId) {
      navigate(`/instances/${agentId}`, { replace: true });
    }
  }, [detailMode, redirectToInstance, agentId, navigate]);

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const created = await api.createInstance({
        instance_id: String(form.get("agent_id") || ""),
        target_puller: spawnDefaults.target_puller,
        model: spawnDefaults.model,
        temperature: spawnDefaults.temperature,
        num_ctx: spawnDefaults.num_ctx,
        persona_name: String(form.get("persona_name") || ""),
        persona_role: String(form.get("persona_role") || "helpful assistant"),
      });
      navigate(`/instances/${created.instance_id}`);
    } catch (exc) {
      setError(String(exc));
    }
  }

  if (detailMode && redirectToInstance) {
    return null;
  }

  if (createMode) {
    return (
      <div className="card">
        <p><Link to="/">← Fleet</Link></p>
        <h2>Create instance</h2>
        <p className="hint">
          Create a standalone instance without a definition.
          {loading && " Loading defaults from gateway config…"}
        </p>
        {error && <p className="error">{error}</p>}
        <form className="form-grid" onSubmit={onCreate}>
          <label>Instance ID<input name="agent_id" required /></label>
          <label>
            Target puller
            <input
              name="target_puller"
              value={spawnDefaults.target_puller}
              onChange={(event) =>
                setSpawnDefaults((current) => ({ ...current, target_puller: event.target.value }))
              }
            />
          </label>
          <label>
            Model
            <input
              name="model"
              value={spawnDefaults.model}
              onChange={(event) =>
                setSpawnDefaults((current) => ({ ...current, model: event.target.value }))
              }
            />
          </label>
          <label>
            Temperature
            <input
              name="temperature"
              type="number"
              step="0.1"
              value={spawnDefaults.temperature}
              onChange={(event) =>
                setSpawnDefaults((current) => ({
                  ...current,
                  temperature: Number(event.target.value),
                }))
              }
            />
          </label>
          <label>
            Context (num_ctx)
            <input
              name="num_ctx"
              type="number"
              step="1024"
              value={spawnDefaults.num_ctx}
              onChange={(event) =>
                setSpawnDefaults((current) => ({
                  ...current,
                  num_ctx: Number(event.target.value),
                }))
              }
            />
          </label>
          <label>Persona name<input name="persona_name" /></label>
          <label>Persona role<input name="persona_role" defaultValue="helpful assistant" /></label>
          <button type="submit">Create</button>
        </form>
      </div>
    );
  }

  return null;
}
