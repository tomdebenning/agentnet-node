import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CompletionEvent, InstanceSummary, api } from "./api";
import { fetchConnectivity, formatConnectionStatus } from "./connectionStatus";
import { badgeClassForState } from "./statusBadges";

export function FleetPage() {
  const [instances, setInstances] = useState<InstanceSummary[]>([]);
  const [completions, setCompletions] = useState<CompletionEvent[]>([]);
  const [status, setStatus] = useState("");
  const [connectionLines, setConnectionLines] = useState<string[]>([]);
  const [error, setError] = useState("");

  async function refresh() {
    const errors: string[] = [];

    try {
      const connectivity = await fetchConnectivity();
      setConnectionLines(formatConnectionStatus(connectivity));
    } catch (exc) {
      errors.push(`Connection: ${exc}`);
      setConnectionLines([]);
    }

    try {
      const s = await api.status();
      setStatus(
        `${s.node_id} · ${s.instance_count ?? 0} instances · ${s.running_agent_count} running · ${s.interactive_session_count ?? 0} interactive`,
      );
    } catch (exc) {
      errors.push(`Gateway: ${exc}`);
      setStatus("");
    }

    try {
      setInstances(await api.listInstances());
    } catch (exc) {
      errors.push(`Instances: ${exc}`);
      setInstances([]);
    }

    try {
      setCompletions(await api.recentCompletions(20));
    } catch (exc) {
      errors.push(`Completions: ${exc}`);
      setCompletions([]);
    }

    setError(errors.length ? errors.join(" · ") : "");
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div>
      <div className="card info-panel connection-panel">
        {connectionLines.map((line) => (
          <p key={line} className="status-msg">{line}</p>
        ))}
        <p className="status-msg">ℹ️ {status || "Loading fleet…"}</p>
      </div>
      {error && <p className="error">🔴 {error}</p>}
      <div className="card">
        <h2>Fleet</h2>
        <div className="row" style={{ marginBottom: 12 }}>
          <Link className="button" to="/instances/spawn">🚀 Spawn instance</Link>
          <Link className="secondary button" to="/definitions/new">New definition</Link>
        </div>
        {instances.length === 0 ? (
          <p>No instances yet. <Link to="/instances/spawn">Spawn from a definition</Link> or <Link to="/instances/new">create a standalone instance</Link>.</p>
        ) : (
          <table className="fleet-table">
            <thead>
              <tr>
                <th>Instance</th>
                <th>Definition</th>
                <th>Mode</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {instances.map((item) => (
                <tr key={item.instance_id}>
                  <td><Link to={`/instances/${item.instance_id}`}>{item.instance_id}</Link></td>
                  <td>{item.definition_id ?? "-"}</td>
                  <td>{item.mode ?? "-"}</td>
                  <td>
                    <span className={`badge ${badgeClassForState(item.instance_status || item.process_state)}`}>
                      {item.instance_status || item.process_state}
                    </span>
                  </td>
                  <td className="row">
                    {item.mode === "interactive" && (
                      <Link className="button secondary" to={`/instances/${item.instance_id}/interactive`}>Chat</Link>
                    )}
                    <button
                      className="secondary"
                      onClick={async () => {
                        await api.stopInstance(item.instance_id);
                        refresh();
                      }}
                    >
                      Stop
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="card">
        <h2>Recent completions</h2>
        {completions.length === 0 ? (
          <p>No completions yet.</p>
        ) : (
          <ul className="completion-list">
            {completions.map((event, index) => (
              <li key={`${event.instance_id}-${event.completed_at}-${index}`}>
                <span className={`badge ${event.success ? "state-ready" : "state-error"}`}>
                  {event.success ? "✅ ok" : "🔴 fail"}
                </span>
                {" "}
                <Link to={`/instances/${event.instance_id}`}>{event.instance_id}</Link>
                {" "}
                <span className="hint">{new Date(event.completed_at).toLocaleString()}</span>
                {event.error && <span className="error"> — {event.error}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
