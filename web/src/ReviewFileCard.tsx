type Props = {
  label: string;
  filename: string;
  reviewed: boolean;
  preview: string;
  onOpen: () => void;
  showReviewStatus?: boolean;
};

export function ReviewFileCard({
  label,
  filename,
  reviewed,
  preview,
  onOpen,
  showReviewStatus = true,
}: Props) {
  const badge = showReviewStatus ? (
    <span className={`badge ${reviewed ? "state-ready" : "state-review"}`}>
      {reviewed ? "✅ Reviewed" : "🟠 Needs review"}
    </span>
  ) : (
    <span className={`badge ${reviewed ? "state-ready" : "state-attention"}`}>
      {reviewed ? "✅ Saved" : "🟡 Unsaved changes"}
    </span>
  );

  return (
    <div className={`review-card ${reviewed ? "review-card-done" : "review-card-pending"}`}>
      <div className="review-card-header">
        <div>
          <strong>{label}</strong>
          <span className="hint"> ({filename})</span>
        </div>
        {badge}
      </div>
      <pre className="review-preview">{preview || "(empty)"}</pre>
      <button type="button" className={reviewed ? "secondary" : ""} onClick={onOpen}>
        {showReviewStatus && !reviewed ? "🔍 Review full screen" : "📝 Open full screen"}
      </button>
    </div>
  );
}
