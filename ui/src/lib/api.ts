export async function startSession(opts: { language?: string | null } = {}): Promise<void> {
  const r = await fetch("/api/control/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language: opts.language ?? null }),
  });
  if (!r.ok) throw new Error(`start failed: ${r.status}`);
}

export async function pauseSession(): Promise<void> {
  const r = await fetch("/api/control/pause", { method: "POST" });
  if (!r.ok) throw new Error(`pause failed: ${r.status}`);
}

export async function stopSession(): Promise<void> {
  const r = await fetch("/api/control/stop", { method: "POST" });
  if (!r.ok) throw new Error(`stop failed: ${r.status}`);
}

import type { PastSession, PastSessionSummary } from "./types";

export async function listHistory(): Promise<PastSessionSummary[]> {
  const r = await fetch("/api/history");
  if (!r.ok) throw new Error(`history failed: ${r.status}`);
  const body = (await r.json()) as { sessions: PastSessionSummary[] };
  return body.sessions;
}

export async function getHistorySession(id: string): Promise<PastSession> {
  const r = await fetch(`/api/history/${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error(`history fetch failed: ${r.status}`);
  return r.json();
}
