import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { DefinitionDetail, DefinitionSummary, api } from "./api";

function previewBody(raw: string, maxLines = 8): string {
  const withoutFrontmatter = raw.replace(/^---[\s\S]*?---\n?/, "").trim();
  const lines = withoutFrontmatter.split("\n").slice(0, maxLines);
  const text = lines.join("\n");
  if (withoutFrontmatter.split("\n").length > maxLines) {
    return `${text}\n…`;
  }
  return text || "(empty)";
}

export function SpawnPickerPage() {
  const navigate = useNavigate();
  const [definitions, setDefinitions] = useState<DefinitionSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<DefinitionDetail | null>(null);
  const [error, setError] = useState("");
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    api.listDefinitions()
      .then((items) => {
        setDefinitions(items);
        if (items.length > 0) {
          setSelectedId((current) => current || items[0].definition_id);
        }
      })
      .catch((exc) => setError(String(exc)));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    setLoadingDetail(true);
    api.getDefinition(selectedId)
      .then((data) => {
        setDetail(data);
        setError("");
      })
      .catch((exc) => setError(String(exc)))
      .finally(() => setLoadingDetail(false));
  }, [selectedId]);

  const selected = useMemo(
    () => definitions.find((item) => item.definition_id === selectedId) ?? null,
    [definitions, selectedId],
  );

  return (
    <div className="card spawn-picker-page">
      <p><Link to="/">← Fleet</Link></p>
      <h2>🚀 Spawn instance</h2>
      <p className="hint">
        Choose an agent definition from the gateway catalog, review its persona and skills,
        then continue to instance configuration.
      </p>
      {error && <p className="error">🔴 {error}</p>}

      {definitions.length === 0 ? (
        <p>
          No definitions in the catalog yet.{" "}
          <Link to="/definitions/new">Create a definition</Link> first, or{" "}
          <Link to="/instances/new">create a standalone instance</Link>.
        </p>
      ) : (
        <div className="spawn-picker-split">
          <section className="spawn-picker-list">
            <h3>Definitions</h3>
            <ul className="definition-picker-list">
              {definitions.map((item) => (
                <li key={item.definition_id}>
                  <button
                    type="button"
                    className={`definition-picker-item ${selectedId === item.definition_id ? "selected" : ""}`}
                    onClick={() => setSelectedId(item.definition_id)}
                  >
                    <strong>{item.definition_id}</strong>
                    {item.persona_name && item.persona_name !== item.definition_id && (
                      <span className="hint"> — {item.persona_name}</span>
                    )}
                    <br />
                    <span className={`badge ${item.spawnable ? "state-ready" : "state-review"}`}>
                      {item.spawnable ? "✅ Spawnable" : "🟠 Needs review"}
                    </span>
                    {!item.uses_memory && (
                      <span className="badge state-info">No memory</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className="spawn-picker-preview">
            <h3>Preview</h3>
            {!selected ? (
              <p className="hint">Select a definition.</p>
            ) : loadingDetail && !detail ? (
              <p className="hint">Loading definition…</p>
            ) : detail ? (
              <>
                <div className="row">
                  <strong>{detail.definition_id}</strong>
                  {(selected.persona_name || selected.persona_role) && (
                    <span className="hint">
                      {selected.persona_name ? ` — ${selected.persona_name}` : ""}
                      {selected.persona_role ? ` · ${selected.persona_role}` : ""}
                    </span>
                  )}
                </div>
                <p>
                  <span className={`badge ${detail.spawnable ? "state-ready" : "state-review"}`}>
                    {detail.spawnable ? "✅ Spawnable" : "🟠 Needs review"}
                  </span>
                  {" "}
                  <span className={`badge ${detail.uses_memory ? "state-info" : "state-muted"}`}>
                    {detail.uses_memory ? "Uses memory" : "No memory"}
                  </span>
                </p>
                <h4>Persona</h4>
                <pre className="preview-block">{previewBody(detail.persona_raw)}</pre>
                <h4>Skills</h4>
                <pre className="preview-block">{previewBody(detail.skills_raw)}</pre>
                <div className="row">
                  <Link className="secondary button" to={`/definitions/${detail.definition_id}`}>
                    View full definition
                  </Link>
                  {detail.spawnable ? (
                    <button
                      type="button"
                      className="button"
                      onClick={() => navigate(`/definitions/${detail.definition_id}/spawn`)}
                    >
                      Continue to spawn →
                    </button>
                  ) : (
                    <button type="button" className="amber" disabled>
                      🟠 Review persona & skills first
                    </button>
                  )}
                </div>
              </>
            ) : null}
          </section>
        </div>
      )}

      <p className="hint">
        Need a one-off agent without a definition?{" "}
        <Link to="/instances/new">Create standalone instance</Link>
      </p>
    </div>
  );
}
