import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "./api";
import { badgeClassForState } from "./statusBadges";

type ChatLine = { role: "user" | "assistant" | "error"; text: string };

export function InteractivePage() {
  const { instanceId = "" } = useParams();
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [input, setInput] = useState("");
  const [state, setState] = useState("interactive_idle");
  const [error, setError] = useState("");
  const lastReplyRef = useRef<string | null>(null);

  useEffect(() => {
    const timer = window.setInterval(async () => {
      try {
        const poll = await api.pollInteractive(instanceId);
        setState(poll.state);
        if (poll.error) {
          setError(poll.error);
        }
        if (poll.last_reply && poll.last_reply !== lastReplyRef.current) {
          lastReplyRef.current = poll.last_reply;
          setLines((prev) => [...prev, { role: "assistant", text: poll.last_reply! }]);
        }
      } catch (exc) {
        setError(String(exc));
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [instanceId]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const message = input.trim();
    if (!message) return;
    setLines((prev) => [...prev, { role: "user", text: message }]);
    setInput("");
    setError("");
    try {
      const response = await api.postInteractiveMessage(instanceId, message);
      setState(response.state);
      if (response.error) {
        setError(response.error);
        setLines((prev) => [...prev, { role: "error", text: response.error! }]);
      }
    } catch (exc) {
      setError(String(exc));
    }
  }

  return (
    <div className="card interactive-panel">
      <p><Link to={`/instances/${instanceId}`}>← {instanceId}</Link></p>
      <h2>Interactive session</h2>
      <p>
        <span className={`badge ${badgeClassForState(state)}`}>
          {state === "interactive_busy" ? "🟡 " : state === "interactive_idle" ? "✅ " : ""}
          {state}
        </span>
      </p>
      {error && <p className="error">🔴 {error}</p>}
      <div className="chat-log">
        {lines.map((line, index) => (
          <div key={index} className={`chat-line ${line.role}`}>
            <strong>{line.role}:</strong> {line.text}
          </div>
        ))}
      </div>
      <form className="row" onSubmit={onSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message…"
          disabled={state === "interactive_busy"}
        />
        <button type="submit" disabled={state === "interactive_busy"}>Send</button>
      </form>
    </div>
  );
}
