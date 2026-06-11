/** Map backend status strings to theme badge classes. */
export function badgeClassForState(state: string | null | undefined): string {
  const s = (state || "unknown").toLowerCase();
  if (
    s === "running" ||
    s === "completed" ||
    s === "interactive_idle" ||
    s === "ok" ||
    s === "success" ||
    s === "spawnable" ||
    s === "ready"
  ) {
    return "state-ready";
  }
  if (
    s === "pending" ||
    s === "stopped" ||
    s === "not_spawnable" ||
    s === "needs_review"
  ) {
    return "state-review";
  }
  if (s === "error" || s === "failed" || s === "fail") {
    return "state-error";
  }
  if (s === "interactive_busy" || s === "working" || s === "attention") {
    return "state-attention";
  }
  if (s === "idle" || s === "info" || s === "unknown") {
    return "state-info";
  }
  return "state-info";
}
