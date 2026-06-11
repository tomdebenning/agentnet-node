export type ConnectivityInfo = {
  gateway_url?: string;
  gateway_connected: boolean;
  gateway_error?: string | null;
  control_plane_url?: string | null;
  control_plane_connected?: boolean;
  control_plane_error?: string | null;
  node_id?: string | null;
  agent_count?: number | null;
  running_agent_count?: number | null;
};

export function formatConnectionStatus(info: ConnectivityInfo): string[] {
  const lines: string[] = [];

  if (info.gateway_connected) {
    lines.push(`Gateway: ✅ connected · ${info.gateway_url ?? "?"}`);
  } else {
    const err = info.gateway_error || "unreachable";
    lines.push(`Gateway: 🔴 DISCONNECTED · ${info.gateway_url ?? "?"} (${err})`);
  }

  if (!info.gateway_connected) {
    lines.push("Control plane: (unknown — gateway unreachable)");
  } else if (info.control_plane_url) {
    if (info.control_plane_connected) {
      lines.push(`Control plane: ✅ connected · ${info.control_plane_url}`);
    } else {
      const err = info.control_plane_error || "unreachable";
      lines.push(`Control plane: 🔴 DISCONNECTED · ${info.control_plane_url} (${err})`);
    }
  } else {
    lines.push("Control plane: (not reported by gateway)");
  }

  if (info.node_id && info.gateway_connected) {
    const running = info.running_agent_count ?? "?";
    const total = info.agent_count ?? "?";
    lines.push(`Node: ${info.node_id} · ${running}/${total} agents running`);
  }

  return lines;
}

export async function fetchConnectivity(): Promise<ConnectivityInfo> {
  try {
    const status = await fetch("/api/status").then((r) => {
      if (!r.ok) throw new Error(r.statusText);
      return r.json();
    });
    return {
      gateway_url: window.location.origin,
      gateway_connected: true,
      control_plane_url: status.control_plane_url,
      control_plane_connected: Boolean(status.control_plane_connected),
      control_plane_error: status.control_plane_error,
      node_id: status.node_id,
      agent_count: status.agent_count,
      running_agent_count: status.running_agent_count,
    };
  } catch (exc) {
    return {
      gateway_url: window.location.origin,
      gateway_connected: false,
      gateway_error: String(exc),
      control_plane_connected: false,
    };
  }
}
