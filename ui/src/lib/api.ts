import type { SessionExport } from "./types";

export async function startSession(): Promise<void> {
  const r = await fetch("/api/control/start", { method: "POST" });
  if (!r.ok) throw new Error(`start failed: ${r.status}`);
}

export async function stopSession(): Promise<void> {
  const r = await fetch("/api/control/stop", { method: "POST" });
  if (!r.ok) throw new Error(`stop failed: ${r.status}`);
}

export async function exportSession(): Promise<SessionExport> {
  const r = await fetch("/api/session/export");
  if (!r.ok) throw new Error(`export failed: ${r.status}`);
  return r.json();
}
