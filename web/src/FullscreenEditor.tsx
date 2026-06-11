import { useEffect } from "react";

export type FullscreenEditorMode = "review" | "definition" | "spawn" | "instance";

type Props = {
  mode: FullscreenEditorMode;
  title: string;
  subtitle?: string;
  value: string;
  onChange: (value: string) => void;
  onClose: () => void;
  filename: string;
  reviewed?: boolean;
  showReviewBadge?: boolean;
  /** Instance was spawned from a definition — enables save-to-definition actions. */
  hasDefinition?: boolean;
  onSaveToDefinition?: (close?: boolean) => void | Promise<void>;
  onSaveToInstance?: (close?: boolean) => void | Promise<void>;
  onMarkReviewed?: () => void | Promise<void>;
  onRevertToDefinition?: () => void | Promise<void>;
};

export function FullscreenEditor({
  mode,
  title,
  subtitle,
  value,
  onChange,
  onClose,
  filename,
  reviewed = false,
  showReviewBadge = false,
  hasDefinition = false,
  onSaveToDefinition,
  onSaveToInstance,
  onMarkReviewed,
  onRevertToDefinition,
}: Props) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const defaultSubtitle =
    mode === "instance"
      ? "Save to this instance only, or update the definition for future spawns."
      : mode === "spawn"
        ? "Close to keep edits as a one-time override for this spawn. Save to definition to update future spawns."
        : mode === "review"
          ? "Review the file, then mark reviewed or cancel."
          : "Save changes to the definition.";

  return (
    <div className="fullscreen-editor" role="dialog" aria-modal="true">
      <header className="fullscreen-editor-header">
        <div>
          <h2>{title}</h2>
          <p className="hint">{subtitle || defaultSubtitle}</p>
          <p className="hint editor-filename">{filename}</p>
        </div>
        {showReviewBadge && (
          <span className={`badge ${reviewed ? "state-ready" : "state-review"}`}>
            {reviewed ? "✅ Reviewed" : "🟠 Not reviewed yet"}
          </span>
        )}
      </header>
      <textarea
        className="fullscreen-editor-body"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
      />
      <footer className="fullscreen-editor-footer">
        <button type="button" className="secondary" onClick={onClose}>
          ← Cancel (Esc)
        </button>

        {mode === "review" && onMarkReviewed && (
          <button type="button" onClick={() => onMarkReviewed()}>
            ✓ Mark reviewed & close
          </button>
        )}

        {(mode === "definition" || mode === "spawn") && onSaveToDefinition && (
          <>
            <button type="button" onClick={() => onSaveToDefinition(false)}>
              💾 Save to definition
            </button>
            <button type="button" onClick={() => onSaveToDefinition(true)}>
              💾 Save to definition & close
            </button>
          </>
        )}

        {mode === "definition" && onMarkReviewed && (
          <button type="button" className="secondary" onClick={() => onMarkReviewed()}>
            ✓ Mark reviewed & close
          </button>
        )}

        {mode === "spawn" && onRevertToDefinition && (
          <button type="button" className="secondary" onClick={() => onRevertToDefinition()}>
            ↩ Revert to definition
          </button>
        )}

        {mode === "instance" && onSaveToInstance && (
          <>
            <button type="button" onClick={() => onSaveToInstance(false)}>
              💾 Save to this instance
            </button>
            <button type="button" onClick={() => onSaveToInstance(true)}>
              💾 Save to this instance & close
            </button>
          </>
        )}

        {mode === "instance" && hasDefinition && onSaveToDefinition && (
          <>
            <button type="button" className="secondary" onClick={() => onSaveToDefinition(false)}>
              💾 Save to definition (future spawns)
            </button>
            <button type="button" className="secondary" onClick={() => onSaveToDefinition(true)}>
              💾 Save to definition & close
            </button>
          </>
        )}
      </footer>
    </div>
  );
}
