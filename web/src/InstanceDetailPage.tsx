import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AgentBrowsePanel } from "./AgentBrowsePanel";
import { InstanceSummary, api } from "./api";
import { FullscreenEditor } from "./FullscreenEditor";
import { ReviewFileCard } from "./ReviewFileCard";
import { RunWorkflowPanel } from "./RunWorkflowPanel";
import { badgeClassForState } from "./statusBadges";

type EditorKind = "persona" | "skills" | null;
type FileKind = "config" | "task" | "memory";
type PanelKind = FileKind | "conversations" | "workspace" | "databases";

const EDIT_KINDS = new Set<string>(["config", "task", "memory"]);
const BROWSE_KINDS = new Set<string>(["conversations", "workspace", "databases"]);

export function InstanceDetailPage() {
  const { instanceId = "" } = useParams();
  const navigate = useNavigate();
  const [instance, setInstance] = useState<InstanceSummary | null>(null);
  const [personaMd, setPersonaMd] = useState("");
  const [skillsMd, setSkillsMd] = useState("");
  const [savedPersonaMd, setSavedPersonaMd] = useState("");
  const [savedSkillsMd, setSavedSkillsMd] = useState("");
  const [fileKind, setFileKind] = useState<PanelKind>("config");
  const [editor, setEditor] = useState("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [openEditor, setOpenEditor] = useState<EditorKind>(null);

  const definitionId = instance?.definition_id ?? null;
  const isRunning = instance?.process_state === "running";
  const isBrowse = BROWSE_KINDS.has(fileKind);

  useEffect(() => {
    Promise.all([
      api.getInstance(instanceId),
      api.readFile(instanceId, "persona"),
      api.readFile(instanceId, "skills"),
      api.readFile(instanceId, "config"),
    ])
      .then(([info, persona, skills, config]) => {
        setInstance(info);
        setPersonaMd(persona.raw);
        setSkillsMd(skills.raw);
        setSavedPersonaMd(persona.raw);
        setSavedSkillsMd(skills.raw);
        setEditor(config.raw);
        setFileKind("config");
      })
      .catch((exc) => setError(String(exc)));
  }, [instanceId]);

  async function selectPanel(kind: PanelKind) {
    setFileKind(kind);
    setError("");
    if (EDIT_KINDS.has(kind)) {
      const file = await api.readFile(instanceId, kind);
      setEditor(file.raw);
    }
  }

  async function savePersonaToInstance(close = false) {
    try {
      await api.writeFile(instanceId, "persona", personaMd);
      setSavedPersonaMd(personaMd);
      setStatus("💾 Persona saved to this instance.");
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function saveSkillsToInstance(close = false) {
    try {
      await api.writeFile(instanceId, "skills", skillsMd);
      setSavedSkillsMd(skillsMd);
      setStatus("💾 Skills saved to this instance.");
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function savePersonaToDefinition(close = false) {
    if (!definitionId) return;
    try {
      await api.writeDefinitionPersona(definitionId, personaMd);
      setStatus(`💾 Persona saved to definition "${definitionId}".`);
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function saveSkillsToDefinition(close = false) {
    if (!definitionId) return;
    try {
      await api.writeDefinitionSkills(definitionId, skillsMd);
      setStatus(`💾 Skills saved to definition "${definitionId}".`);
      setError("");
      if (close) setOpenEditor(null);
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function saveCurrentFile() {
    if (!EDIT_KINDS.has(fileKind)) return;
    try {
      if (fileKind === "task" && isRunning) {
        const ok = window.confirm(
          "Agent is running. Stop it so the new task can run on next Start?",
        );
        if (!ok) return;
        const stopped = await api.stopInstance(instanceId);
        setInstance((prev) => (prev ? { ...prev, ...stopped } : prev));
      }
      await api.writeFile(instanceId, fileKind, editor);
      setStatus(`💾 ${fileKind} saved.`);
      setError("");
    } catch (exc) {
      setError(String(exc));
    }
  }

  async function refreshInstance() {
    setInstance(await api.getInstance(instanceId));
  }

  const personaDirty = personaMd !== savedPersonaMd;
  const skillsDirty = skillsMd !== savedSkillsMd;

  return (
    <div>
      <div className="card">
        <p><Link to="/">← Fleet</Link></p>
        <h2>{instanceId}</h2>
        {instance && (
          <p>
            <span className={`badge ${badgeClassForState(instance.instance_status || instance.process_state)}`}>
              {instance.instance_status || instance.process_state}
            </span>
            {" · PID: "}{instance.pid ?? "-"}
            {definitionId && (
              <>
                {" · definition: "}
                <Link to={`/definitions/${definitionId}`}>{definitionId}</Link>
              </>
            )}
            {instance.mode && <> · mode: {instance.mode}</>}
            {instance.mode === "interactive" && (
              <>
                {" · "}
                <Link to={`/instances/${instanceId}/interactive`}>Open chat</Link>
              </>
            )}
          </p>
        )}
        {error && <p className="error">🔴 {error}</p>}
        {status && <p className="status-msg">{status}</p>}

        <RunWorkflowPanel run={instance?.current_run} />

        <p className="hint">Persona & skills — view here, edit in full screen.</p>
        <div className="review-checklist">
          <ReviewFileCard
            label="Persona"
            filename="persona.md"
            reviewed={!personaDirty}
            preview={personaMd}
            onOpen={() => setOpenEditor("persona")}
            showReviewStatus={false}
          />
          <ReviewFileCard
            label="Skills"
            filename="skills.md"
            reviewed={!skillsDirty}
            preview={skillsMd}
            onOpen={() => setOpenEditor("skills")}
            showReviewStatus={false}
          />
        </div>
      </div>

      <div className="card">
        <p className="hint">Files (editable)</p>
        <div className="row tabs">
          {(["config", "task", "memory"] as FileKind[]).map((kind) => (
            <button
              key={kind}
              type="button"
              className={fileKind === kind ? "" : "secondary"}
              onClick={() => selectPanel(kind)}
            >
              {kind}
            </button>
          ))}
        </div>
        <p className="hint">Output (read-only)</p>
        <div className="row tabs">
          {(["conversations", "workspace", "databases"] as const).map((kind) => (
            <button
              key={kind}
              type="button"
              className={fileKind === kind ? "" : "secondary"}
              onClick={() => selectPanel(kind)}
            >
              {kind}
            </button>
          ))}
        </div>
        {fileKind === "task" && !isBrowse && (
          <p className="hint">Legacy task file — use Goal on the current run instead.</p>
        )}
        {isBrowse ? (
          <AgentBrowsePanel
            agentId={instanceId}
            mode={fileKind as "conversations" | "workspace" | "databases"}
          />
        ) : (
          <textarea value={editor} onChange={(e) => setEditor(e.target.value)} />
        )}
        <div className="row">
          {!isBrowse && (
            <button type="button" onClick={saveCurrentFile}>
              Save {fileKind}
            </button>
          )}
          <button
            type="button"
            className="secondary"
            onClick={async () => {
              try {
                await api.startInstance(instanceId);
                await refreshInstance();
                setStatus("Agent started.");
              } catch (exc) {
                setError(String(exc));
              }
            }}
          >
            Start
          </button>
          <button
            type="button"
            className="secondary"
            onClick={async () => {
              try {
                await api.pauseInstance(instanceId);
                await refreshInstance();
                setStatus("Run paused.");
              } catch (exc) {
                setError(String(exc));
              }
            }}
          >
            Pause
          </button>
          <button
            type="button"
            className="secondary"
            onClick={async () => {
              try {
                await api.resumeInstance(instanceId);
                await refreshInstance();
                setStatus("Run resumed.");
              } catch (exc) {
                setError(String(exc));
              }
            }}
          >
            Resume
          </button>
          <button
            type="button"
            className="secondary"
            onClick={async () => {
              try {
                await api.stopInstance(instanceId);
                await refreshInstance();
                setStatus("Instance stopped.");
              } catch (exc) {
                setError(String(exc));
              }
            }}
          >
            Stop
          </button>
          <button
            type="button"
            className="danger"
            onClick={async () => {
              if (!window.confirm(`Delete instance "${instanceId}"? This cannot be undone.`)) return;
              try {
                await api.deleteInstance(instanceId);
                navigate("/");
              } catch (exc) {
                setError(String(exc));
              }
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {openEditor === "persona" && (
        <FullscreenEditor
          mode="instance"
          title="Persona (persona.md)"
          filename="persona.md"
          value={personaMd}
          onChange={setPersonaMd}
          hasDefinition={Boolean(definitionId)}
          onClose={() => setOpenEditor(null)}
          onSaveToInstance={(close) => savePersonaToInstance(close)}
          onSaveToDefinition={(close) => savePersonaToDefinition(close)}
        />
      )}
      {openEditor === "skills" && (
        <FullscreenEditor
          mode="instance"
          title="Skills (skills.md)"
          filename="skills.md"
          value={skillsMd}
          onChange={setSkillsMd}
          hasDefinition={Boolean(definitionId)}
          onClose={() => setOpenEditor(null)}
          onSaveToInstance={(close) => saveSkillsToInstance(close)}
          onSaveToDefinition={(close) => saveSkillsToDefinition(close)}
        />
      )}
    </div>
  );
}
