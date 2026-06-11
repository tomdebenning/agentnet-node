import { RunArtifact, RunDocument, RunPlan, RunProducts, RunSummary } from "./api";

function stepBadge(status: string) {
  if (status === "done") return "✅";
  if (status === "in_progress") return "🏃";
  return "🟠";
}

export function RunWorkflowPanel({ run }: { run: RunSummary | null | undefined }) {
  if (!run) {
    return (
      <section className="run-panel">
        <h3>🎯 Run</h3>
        <p className="hint">No active run yet.</p>
      </section>
    );
  }

  const goal = run.run as RunDocument;
  const plan = run.plan as RunPlan;
  const artifacts = run.artifacts as RunArtifact[];
  const products = run.products as RunProducts;

  return (
    <section className="run-panel">
      <h3>🎯 Goal</h3>
      <p className="run-goal">{goal.goal || "(not set)"}</p>
      <p className="hint">
        Status: <span className={`badge ${goal.status === "done" ? "state-ready" : "state-info"}`}>{goal.status}</span>
        {" · "}
        Run: <code>{run.conversation_id}</code>
      </p>
      {Object.keys(goal.options || {}).length > 0 && (
        <p className="hint">
          Run options:{" "}
          {Object.entries(goal.options).map(([key, value]) => (
            <span key={key}>
              {key}=<code>{String(value)}</code>{" "}
            </span>
          ))}
        </p>
      )}

      <h4>📋 Plan</h4>
      {plan.steps.length === 0 ? (
        <p className="hint">No plan steps yet.</p>
      ) : (
        <ul className="plan-list">
          {plan.steps.map((step) => (
            <li key={step.id}>
              {stepBadge(step.status)} {step.title}{" "}
              <span className="hint">({step.id})</span>
            </li>
          ))}
        </ul>
      )}

      <h4>📦 Artifacts</h4>
      {artifacts.length === 0 ? (
        <p className="hint">No artifacts recorded yet.</p>
      ) : (
        <ul className="artifact-list">
          {artifacts.map((artifact) => (
            <li key={artifact.artifact_id}>
              <code>{artifact.artifact_id}</code> · {artifact.type} · {artifact.summary}
              {artifact.step_id ? ` · step ${artifact.step_id}` : ""}
            </li>
          ))}
        </ul>
      )}

      <h4>✅ Products</h4>
      {products.product_artifact_ids.length === 0 ? (
        <p className="hint">No products declared yet.</p>
      ) : (
        <ul>
          {products.product_artifact_ids.map((id) => (
            <li key={id}><code>{id}</code></li>
          ))}
        </ul>
      )}
    </section>
  );
}
