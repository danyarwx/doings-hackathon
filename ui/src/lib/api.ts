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

import type { Insight, PastSession, PastSessionSummary } from "./types";

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

export async function approveInsight(id: string): Promise<Insight> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}/approve`, { method: "POST" });
  if (!r.ok) throw new Error(`approve failed: ${r.status}`);
  return (await r.json()).insight;
}

export async function declineInsight(id: string): Promise<Insight> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}/decline`, { method: "POST" });
  if (!r.ok) throw new Error(`decline failed: ${r.status}`);
  return (await r.json()).insight;
}

export async function editInsight(id: string, text: string): Promise<Insight> {
  const r = await fetch(`/api/insights/${encodeURIComponent(id)}/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`edit failed: ${r.status}`);
  return (await r.json()).insight;
}

export async function getVocabulary(): Promise<string> {
  const r = await fetch("/api/vocabulary");
  if (!r.ok) throw new Error(`vocabulary fetch failed: ${r.status}`);
  return (await r.json()).text;
}

export async function setVocabulary(text: string): Promise<string> {
  const r = await fetch("/api/vocabulary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!r.ok) throw new Error(`vocabulary save failed: ${r.status}`);
  return (await r.json()).text;
}

export async function getModel(): Promise<{ model: string; allowed: string[] }> {
  const r = await fetch("/api/model");
  if (!r.ok) throw new Error(`model fetch failed: ${r.status}`);
  return r.json();
}

export async function setModel(model: string): Promise<string> {
  const r = await fetch("/api/model", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model }),
  });
  if (!r.ok) throw new Error(`model swap failed: ${r.status}`);
  return (await r.json()).model;
}
