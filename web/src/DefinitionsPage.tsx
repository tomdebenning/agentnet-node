import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { DefinitionDetail, DefinitionSummary, api } from "./api";
import { useSpawnDefaults } from "./useSpawnDefaults";
import { FullscreenEditor } from "./FullscreenEditor";
import { ReviewFileCard } from "./ReviewFileCard";

type EditorKind = "persona" | "skills" | "memory" | null;

export function defaultSkillsMarkdown(): string {
  return `---
version: 1
---
# Skills

Define what this agent is equipped to do and how it should use its tools.

## Capabilities

- Read and write files in \`workspace/\`
- Query local SQLite databases
- Search the web and fetch URLs (when configured)

## Procedures

(Add domain-specific skills, workflows, or tool usage notes here.)
`;
}

export function defaultMemoryMarkdown(): string {
  return `---
---
# Memory

(No memories yet.)
`;
}

export function defaultPersonaMarkdown(name: string, role: string): string {
  return `---
name: ${name}
role: ${role}
---
# Persona

You are **${name}**, a ${role}.

- Answer clearly and helpfully.
- Use your tools when they help.
- Persist important facts to memory.
`;
}

function ReadyBanner({
  personaReviewed,
  skillsReviewed,
  spawnable,
}: {
  personaReviewed: boolean;
  skillsReviewed: boolean;
  spawnable?: boolean;
}) {
  const ready = spawnable ?? (personaReviewed && skillsReviewed);
  return (
    <div className={`ready-banner ${ready ? "done" : "pending"}`}>
      {ready ? (
        <>✅ Definition is spawnable — persona and skills have been reviewed.</>
      ) : (
        <>
          🟠 Review required before this definition can spawn instances.
          {" "}
          {!personaReviewed && "Persona not reviewed. "}
          {!skillsReviewed && "Skills not reviewed."}
        </>
      )}
    </div>
  );
}

export function DefinitionsPage() {
  const [definitions, setDefinitions] = useState<DefinitionSummary[]>([]);
  const [error, setError] = useState("");

  async function refresh() {
    try {
      setDefinitions(await api.listDefinitions());
      setError("");
    } catch (exc) {
      setError(String(exc));
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 5000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="card">
      <h2>📋 Agent definitions</h2>
      {error && <p className="error">🔴 {error}</p>}
      <div className="row">
        <Link className="button" to="/definitions/new">➕ Create definition</Link>
        <button type="button" className="secondary" onClick={refresh}>Refresh</button>
      </div>
      {definitions.length === 0 ? (
        <p className="hint">No definitions yet.</p>
      ) : (
        <ul>
          {definitions.map((def) => (
            <li key={def.definition_id} style={{ marginBottom: 10 }}>
              <Link to={`/definitions/${def.definition_id}`}>{def.definition_id}</Link>
              {" "}
              <span className={`badge ${def.spawnable ? "state-ready" : "state-review"}`}>
                {def.spawnable ? "✅ Spawnable" : "🟠 Needs review"}
              </span>
              {" · "}
              {def.spawnable ? (
                <Link to={`/definitions/${def.definition_id}/spawn`}>🚀 Spawn</Link>
              ) : (
                <span className="hint">Spawn locked until reviewed</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CreateDefinitionPage() {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [personaMd, setPersonaMdRaw] = useState(defaultPersonaMarkdown("Agent", "helpful assistant"));
  const [skillsMd, setSkillsMdRaw] = useState(defaultSkillsMarkdown());
  const [memoryMd, setMemoryMdRaw] = useState(defaultMemoryMarkdown());
  const [usesMemory, setUsesMemory] = useState(true);
  const [personaReviewed, setPersonaReviewed] = useState(false);
  const [skillsReviewed, setSkillsReviewed] = useState(false);
  const [openEditor, setOpenEditor] = useState<EditorKind>(null);

  const canCreate = personaReviewed && skillsReviewed;

  function setPersonaMd(value: string) {
    setPersonaMdRaw(value);
    setPersonaReviewed(false);
  }

  function setSkillsMd(value: string) {
    setSkillsMdRaw(value);
    setSkillsReviewed(false);
  }

  function setMemoryMd(value: string) {
    setMemoryMdRaw(value);
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreate) return;
    const form = new FormData(event.currentTarget);
    try {
      const created = await api.createDefinition({
        definition_id: String(form.get("definition_id") || ""),
        persona_content: personaMd,
        skills_content: skillsMd,
        ...(usesMemory ? { memory_content: memoryMd } : { uses_memory: false }),
        persona_reviewed: true,
        skills_reviewed: true,
      });
      navigate(`/definitions/${created.definition_id}/spawn`);
    } catch (exc) {
      setError(String(exc));
    }
  }

  function applyPersonaDefaults() {
    const form = document.getElementById("create-definition-form") as HTMLFormElement | null;
    if (!form) return;
    const name = String(new FormData(form).get("persona_name") || "Agent");
    const role = String(new FormData(form).get("persona_role") || "helpful assistant");
    setPersonaMd(defaultPersonaMarkdown(name, role));
  }

  return (
    <div className="card">
      <h2>➕ Create agent definition</h2>
      <p className="hint">
        Definitions include <code>persona.md</code> and <code>skills.md</code>.
        Optionally include <code>memory.md</code> for agents that need persistent memory.
        Model, puller, and instance naming are configured when you spawn an instance.
        Review persona and skills before creating.
      </p>
      <ReadyBanner personaReviewed={personaReviewed} skillsReviewed={skillsReviewed} />
      {error && <p className="error">🔴 {error}</p>}
      <form className="form-grid" id="create-definition-form" onSubmit={onSubmit}>
        <label>Definition ID<input name="definition_id" required /></label>
        <div className="row">
          <label>Persona name<input name="persona_name" defaultValue="Agent" /></label>
          <label>Persona role<input name="persona_role" defaultValue="helpful assistant" /></label>
          <button type="button" className="secondary" onClick={applyPersonaDefaults}>
            Apply to persona editor
          </button>
        </div>
        <div className="row">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={usesMemory}
              onChange={(event) => setUsesMemory(event.target.checked)}
            />
            {" "}
            This agent needs persistent memory
          </label>
        </div>
        <div className="review-checklist">
          <ReviewFileCard
            label="Persona"
            filename="persona.md"
            reviewed={personaReviewed}
            preview={personaMd}
            onOpen={() => setOpenEditor("persona")}
          />
          <ReviewFileCard
            label="Skills"
            filename="skills.md"
            reviewed={skillsReviewed}
            preview={skillsMd}
            onOpen={() => setOpenEditor("skills")}
          />
          {usesMemory && (
            <ReviewFileCard
              label="Memory"
              filename="memory.md"
              reviewed
              preview={memoryMd}
              onOpen={() => setOpenEditor("memory")}
            />
          )}
        </div>
        <button type="submit" disabled={!canCreate}>
          {canCreate ? "✅ Create spawnable definition" : "🟠 Review persona & skills first"}
        </button>
      </form>

      {openEditor === "persona" && (
        <FullscreenEditor
          mode="review"
          title="Persona (persona.md)"
          subtitle="Review who this agent is before creating the definition."
          filename="persona.md"
          value={personaMd}
          onChange={setPersonaMd}
          reviewed={personaReviewed}
          showReviewBadge
          onClose={() => setOpenEditor(null)}
          onMarkReviewed={() => {
            setPersonaReviewed(true);
            setOpenEditor(null);
          }}
        />
      )}
      {openEditor === "skills" && (
        <FullscreenEditor
          mode="review"
          title="Skills (skills.md)"
          subtitle="Review what this agent can do before creating the definition."
          filename="skills.md"
          value={skillsMd}
          onChange={setSkillsMd}
          reviewed={skillsReviewed}
          showReviewBadge
          onClose={() => setOpenEditor(null)}
          onMarkReviewed={() => {
            setSkillsReviewed(true);
            setOpenEditor(null);
          }}
        />
      )}
      {openEditor === "memory" && usesMemory && (
        <FullscreenEditor
          mode="review"
          title="Memory (memory.md)"
          subtitle="Seed long-term context copied to each spawned instance."
          filename="memory.md"
          value={memoryMd}
          onChange={setMemoryMd}
          onClose={() => setOpenEditor(null)}
        />
      )}
    </div>
  );
}

export function DefinitionDetailPage() {
  const { definitionId = "" } = useParams();
  const navigate = useNavigate();
  const [personaMd, setPersonaMdRaw] = useState("");
  const [skillsMd, setSkillsMdRaw] = useState("");
  const [memoryMd, setMemoryMdRaw] = useState("");
  const [usesMemory, setUsesMemory] = useState(true);
  const [personaReviewed, setPersonaReviewed] = useState(false);
  const [skillsReviewed, setSkillsReviewed] = useState(false);
  const [spawnable, setSpawnable] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [openEditor, setOpenEditor] = useState<EditorKind>(null);

  function applyReview(data: DefinitionDetail) {
    setPersonaMdRaw(data.persona_raw);
    setSkillsMdRaw(data.skills_raw);
    setMemoryMdRaw(data.memory_raw);
    setUsesMemory(data.uses_memory);
    setPersonaReviewed(data.persona_reviewed);
    setSkillsReviewed(data.skills_reviewed);
    setSpawnable(data.spawnable);
  }

  useEffect(() => {
    api.getDefinition(definitionId).then(applyReview).catch((exc) => setError(String(exc)));
  }, [definitionId]);

  function setPersonaMd(value: string) {
    setPersonaMdRaw(value);
    setPersonaReviewed(false);
    setSpawnable(false);
  }

  function setSkillsMd(value: string) {
    setSkillsMdRaw(value);
    setSkillsReviewed(false);
    setSpawnable(false);
  }

  function setMemoryMd(value: string) {
    setMemoryMdRaw(value);
  }

  async function savePersona(markReviewed: boolean, close = false) {
    try {
      const result = await api.writeDefinitionPersona(definitionId, personaMd, markReviewed);
      setPersonaReviewed(result.persona_reviewed);
      setSkillsReviewed(result.skills_reviewed);
      setSpawnable(result.spawnable);
      setStatus(
        markReviewed ? "✅ Persona reviewed and saved to definition." : "💾 Persona saved to definition.",
      );
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function saveSkills(markReviewed: boolean, close = false) {
    try {
      const result = await api.writeDefinitionSkills(definitionId, skillsMd, markReviewed);
      setPersonaReviewed(result.persona_reviewed);
      setSkillsReviewed(result.skills_reviewed);
      setSpawnable(result.spawnable);
      setStatus(
        markReviewed ? "✅ Skills reviewed and saved to definition." : "💾 Skills saved to definition.",
      );
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function toggleUsesMemory(checked: boolean) {
    try {
      const result = await api.setDefinitionUsesMemory(definitionId, checked);
      setUsesMemory(result.uses_memory);
      setMemoryMdRaw(result.memory_raw);
      setPersonaReviewed(result.persona_reviewed);
      setSkillsReviewed(result.skills_reviewed);
      setSpawnable(result.spawnable);
      setStatus(
        checked
          ? "✅ Memory enabled for this definition."
          : "Memory disabled — spawned instances will not use persistent memory.",
      );
      setError("");
      if (!checked && openEditor === "memory") {
        setOpenEditor(null);
      }
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function saveMemory(close = false) {
    try {
      await api.writeDefinitionMemory(definitionId, memoryMd);
      setStatus("💾 Memory saved to definition.");
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function markPersonaReviewed() {
    await savePersona(true, true);
  }

  async function markSkillsReviewed() {
    await saveSkills(true, true);
  }

  return (
    <div className="card">
      <p><Link to="/definitions">← Definitions</Link></p>
      <h2>{definitionId}</h2>
      <ReadyBanner
        personaReviewed={personaReviewed}
        skillsReviewed={skillsReviewed}
        spawnable={spawnable}
      />
      {error && <p className="error">🔴 {error}</p>}
      {status && <p className="status-msg">{status}</p>}
      <div className="row">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={usesMemory}
            onChange={(event) => toggleUsesMemory(event.target.checked)}
          />
          {" "}
          This agent needs persistent memory
        </label>
      </div>
      <div className="review-checklist">
        <ReviewFileCard
          label="Persona"
          filename="persona.md"
          reviewed={personaReviewed}
          preview={personaMd}
          onOpen={() => setOpenEditor("persona")}
        />
        <ReviewFileCard
          label="Skills"
          filename="skills.md"
          reviewed={skillsReviewed}
          preview={skillsMd}
          onOpen={() => setOpenEditor("skills")}
        />
        {usesMemory && (
          <ReviewFileCard
            label="Memory"
            filename="memory.md"
            reviewed
            preview={memoryMd}
            onOpen={() => setOpenEditor("memory")}
          />
        )}
      </div>
      <div className="row">
        {spawnable ? (
          <Link className="button" to={`/definitions/${definitionId}/spawn`}>🚀 Spawn instance</Link>
        ) : (
          <button type="button" className="amber" disabled>
            🟠 Spawn locked — review persona & skills
          </button>
        )}
        <button
          type="button"
          className="danger"
          onClick={async () => {
            if (!window.confirm(`Delete definition "${definitionId}"? This cannot be undone.`)) return;
            try {
              await api.deleteDefinition(definitionId);
              navigate("/definitions");
            } catch (exc) {
              setError(String(exc));
            }
          }}
        >
          Delete definition
        </button>
      </div>

      {openEditor === "persona" && (
        <FullscreenEditor
          mode="definition"
          title="Persona (persona.md)"
          filename="persona.md"
          value={personaMd}
          onChange={setPersonaMd}
          reviewed={personaReviewed}
          showReviewBadge
          onClose={() => setOpenEditor(null)}
          onSaveToDefinition={(close) => savePersona(false, close)}
          onMarkReviewed={markPersonaReviewed}
        />
      )}
      {openEditor === "skills" && (
        <FullscreenEditor
          mode="definition"
          title="Skills (skills.md)"
          filename="skills.md"
          value={skillsMd}
          onChange={setSkillsMd}
          reviewed={skillsReviewed}
          showReviewBadge
          onClose={() => setOpenEditor(null)}
          onSaveToDefinition={(close) => saveSkills(false, close)}
          onMarkReviewed={markSkillsReviewed}
        />
      )}
      {openEditor === "memory" && usesMemory && (
        <FullscreenEditor
          mode="definition"
          title="Memory (memory.md)"
          filename="memory.md"
          value={memoryMd}
          onChange={setMemoryMd}
          onClose={() => setOpenEditor(null)}
          onSaveToDefinition={(close) => saveMemory(close)}
        />
      )}
    </div>
  );
}

export function SpawnInstancePage() {
  const { definitionId = "" } = useParams();
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [definitionPersona, setDefinitionPersona] = useState("");
  const [personaMd, setPersonaMdRaw] = useState("");
  const [definitionSkills, setDefinitionSkills] = useState("");
  const [skillsMd, setSkillsMdRaw] = useState("");
  const [spawnable, setSpawnable] = useState(false);
  const [personaReviewed, setPersonaReviewed] = useState(false);
  const [skillsReviewed, setSkillsReviewed] = useState(false);
  const [openEditor, setOpenEditor] = useState<EditorKind>(null);
  const { spawnDefaults, loading, setSpawnDefaults } = useSpawnDefaults();

  useEffect(() => {
    api.getDefinition(definitionId)
      .then((data) => {
        setDefinitionPersona(data.persona_raw);
        setPersonaMdRaw(data.persona_raw);
        setDefinitionSkills(data.skills_raw);
        setSkillsMdRaw(data.skills_raw);
        setSpawnable(data.spawnable);
        setPersonaReviewed(data.persona_reviewed);
        setSkillsReviewed(data.skills_reviewed);
      })
      .catch((exc) => setError(String(exc)));
  }, [definitionId]);

  function setPersonaMd(value: string) {
    setPersonaMdRaw(value);
  }

  function setSkillsMd(value: string) {
    setSkillsMdRaw(value);
  }

  const personaDiffersFromDefinition = useMemo(
    () => personaMd !== definitionPersona,
    [personaMd, definitionPersona],
  );

  const skillsDiffersFromDefinition = useMemo(
    () => skillsMd !== definitionSkills,
    [skillsMd, definitionSkills],
  );

  async function savePersonaToDefinition(markReviewed = false, close = false) {
    try {
      const result = await api.writeDefinitionPersona(definitionId, personaMd, markReviewed);
      setDefinitionPersona(personaMd);
      setPersonaReviewed(result.persona_reviewed);
      setSkillsReviewed(result.skills_reviewed);
      setSpawnable(result.spawnable);
      setStatus(markReviewed ? "✅ Persona reviewed and saved to definition." : "💾 Persona saved to definition.");
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function saveSkillsToDefinition(markReviewed = false, close = false) {
    try {
      const result = await api.writeDefinitionSkills(definitionId, skillsMd, markReviewed);
      setDefinitionSkills(skillsMd);
      setPersonaReviewed(result.persona_reviewed);
      setSkillsReviewed(result.skills_reviewed);
      setSpawnable(result.spawnable);
      setStatus(markReviewed ? "✅ Skills reviewed and saved to definition." : "💾 Skills saved to definition.");
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  function resetPersonaToDefinition() {
    setPersonaMd(definitionPersona);
    setStatus("Reverted persona to definition version.");
  }

  function resetSkillsToDefinition() {
    setSkillsMd(definitionSkills);
    setStatus("Reverted skills to definition version.");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!spawnable) return;
    const form = new FormData(event.currentTarget);
    const mode = String(form.get("mode") || "autonomous") as "autonomous" | "interactive";
    try {
      const spawned = await api.spawnInstance(definitionId, {
        mode,
        base_name: String(form.get("base_name") || definitionId),
        target_puller: spawnDefaults.target_puller,
        model: spawnDefaults.model,
        temperature: spawnDefaults.temperature,
        num_ctx: spawnDefaults.num_ctx,
        goal: String(form.get("goal") || ""),
        resume: form.get("resume") === "on",
        auto_start: mode === "autonomous",
        persona_content: personaDiffersFromDefinition ? personaMd : undefined,
        skills_content: skillsDiffersFromDefinition ? skillsMd : undefined,
      });
      if (mode === "interactive") {
        navigate(`/instances/${spawned.instance_id}/interactive`);
      } else {
        navigate(`/instances/${spawned.instance_id}`);
      }
    } catch (exc) {
      setError(String(exc));
    }
  }

  return (
    <div className="card spawn-page">
      <p><Link to={`/definitions/${definitionId}`}>← {definitionId}</Link></p>
      <h2>🚀 Spawn from {definitionId}</h2>
      <ReadyBanner
        personaReviewed={personaReviewed}
        skillsReviewed={skillsReviewed}
        spawnable={spawnable}
      />
      {error && <p className="error">🔴 {error}</p>}
      {status && <p className="status-msg">{status}</p>}

      <div className="spawn-split">
        <section className="spawn-panel spawn-panel-definition">
          <h3>📄 Definition</h3>
          <p className="hint">
            Persona and skills from the definition library.
            Open full screen to review or override for this instance only.
          </p>
          {personaDiffersFromDefinition && (
            <p className="hint persona-override">🟠 Instance-only persona override (definition unchanged)</p>
          )}
          <ReviewFileCard
            label="Persona"
            filename="persona.md"
            reviewed={personaReviewed}
            preview={personaMd}
            onOpen={() => setOpenEditor("persona")}
          />
          {skillsDiffersFromDefinition && (
            <p className="hint persona-override">🟠 Instance-only skills override (definition unchanged)</p>
          )}
          <ReviewFileCard
            label="Skills"
            filename="skills.md"
            reviewed={skillsReviewed}
            preview={skillsMd}
            onOpen={() => setOpenEditor("skills")}
          />
        </section>

        <section className="spawn-panel spawn-panel-instance">
          <h3>🤖 Instance configuration</h3>
          <p className="hint">
            Required before the instance can run.
            {loading && " Loading defaults from gateway config…"}
          </p>
          <form className="form-grid" onSubmit={onSubmit}>
            <label>
              Base name (instance id prefix)
              <input name="base_name" defaultValue={definitionId} required disabled={!spawnable} />
            </label>
            <label>
              Target puller
              <input
                name="target_puller"
                value={spawnDefaults.target_puller}
                onChange={(event) =>
                  setSpawnDefaults((current) => ({ ...current, target_puller: event.target.value }))
                }
                required
                disabled={!spawnable}
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
                required
                disabled={!spawnable}
              />
            </label>
            <label>
              Temperature (this run)
              <input
                name="temperature"
                type="number"
                step="0.1"
                min="0"
                max="2"
                value={spawnDefaults.temperature}
                onChange={(event) =>
                  setSpawnDefaults((current) => ({
                    ...current,
                    temperature: Number(event.target.value),
                  }))
                }
                disabled={!spawnable}
              />
            </label>
            <label>
              Context window (num_ctx)
              <input
                name="num_ctx"
                type="number"
                step="1024"
                min="1024"
                value={spawnDefaults.num_ctx}
                onChange={(event) =>
                  setSpawnDefaults((current) => ({
                    ...current,
                    num_ctx: Number(event.target.value),
                  }))
                }
                disabled={!spawnable}
              />
            </label>
            <label>
              Mode
              <select name="mode" defaultValue="autonomous" disabled={!spawnable}>
                <option value="autonomous">Autonomous (run goal)</option>
                <option value="interactive">Interactive (first message = goal)</option>
              </select>
            </label>
            <label className="checkbox">
              <input type="checkbox" name="resume" disabled={!spawnable} /> Resume paused run (autonomous)
            </label>
            <label>
              Goal
              <textarea name="goal" rows={10} placeholder="What should this run accomplish?" disabled={!spawnable} />
            </label>
            <button type="submit" disabled={!spawnable}>
              {spawnable ? "🚀 Spawn instance" : "🟠 Review definition files first"}
            </button>
          </form>
        </section>
      </div>

      {openEditor === "persona" && (
        <FullscreenEditor
          mode="spawn"
          title="Persona (persona.md)"
          filename="persona.md"
          value={personaMd}
          onChange={setPersonaMd}
          reviewed={personaReviewed}
          showReviewBadge
          onClose={() => setOpenEditor(null)}
          onSaveToDefinition={(close) => savePersonaToDefinition(false, close)}
          onRevertToDefinition={() => {
            resetPersonaToDefinition();
            setOpenEditor(null);
          }}
        />
      )}
      {openEditor === "skills" && (
        <FullscreenEditor
          mode="spawn"
          title="Skills (skills.md)"
          filename="skills.md"
          value={skillsMd}
          onChange={setSkillsMd}
          reviewed={skillsReviewed}
          showReviewBadge
          onClose={() => setOpenEditor(null)}
          onSaveToDefinition={(close) => saveSkillsToDefinition(false, close)}
          onRevertToDefinition={() => {
            resetSkillsToDefinition();
            setOpenEditor(null);
          }}
        />
      )}
    </div>
  );
}
