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

import type { ExportDraft, Insight, PastSession, PastSessionSummary } from "./types";

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
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const body = await r.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`model swap failed: ${detail}`);
  }
  return (await r.json()).model;
}

export type ApiKeyStatus = { openai: boolean; anthropic: boolean };

export async function getApiKeyStatus(): Promise<ApiKeyStatus> {
  const r = await fetch("/api/api-keys");
  if (!r.ok) throw new Error(`api-keys fetch failed: ${r.status}`);
  return r.json();
}

export async function setApiKey(
  provider: "openai" | "anthropic",
  key: string,
): Promise<ApiKeyStatus> {
  const r = await fetch("/api/api-keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, key }),
  });
  if (!r.ok) throw new Error(`api-key save failed: ${r.status}`);
  return r.json();
}

export type ExportStatus = {
  ready: boolean;
  draft: ExportDraft | null;
  model: string;
};

export async function getExport(): Promise<ExportStatus> {
  const r = await fetch("/api/export");
  if (!r.ok) throw new Error(`export fetch failed: ${r.status}`);
  return r.json();
}

export async function generateExport(): Promise<ExportDraft> {
  const r = await fetch("/api/export/generate", { method: "POST" });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const body = await r.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(`export generate failed: ${detail}`);
  }
  return (await r.json()).draft;
}

export async function updateExport(draft: ExportDraft): Promise<ExportDraft> {
  const r = await fetch("/api/export", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!r.ok) throw new Error(`export update failed: ${r.status}`);
  return (await r.json()).draft;
}

export type JiraConfig = {
  url_set: boolean;
  email_set: boolean;
  token_set: boolean;
  project_set: boolean;
  url: string;
  project: string;
};

export async function getJiraConfig(): Promise<JiraConfig> {
  const r = await fetch("/api/jira/config");
  if (!r.ok) throw new Error(`jira config fetch failed: ${r.status}`);
  return r.json();
}

export async function setJiraConfigField(
  field: "url" | "email" | "token" | "project",
  value: string,
): Promise<JiraConfig> {
  const r = await fetch("/api/jira/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
  if (!r.ok) throw new Error(`jira config save failed: ${r.status}`);
  return r.json();
}

export type JiraPushResult = {
  key: string;
  url: string;
};

export type JiraPushAllRow = {
  index: number;
  summary: string;
  key?: string;
  url?: string;
  error?: string;
};

async function _parseDetail(r: Response): Promise<string> {
  try {
    const body = await r.json();
    if (body?.detail) return String(body.detail);
  } catch {
    /* ignore */
  }
  return `${r.status}`;
}

export async function pushExportItem(index: number): Promise<JiraPushResult> {
  const r = await fetch("/api/export/push", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ index }),
  });
  if (!r.ok) throw new Error(await _parseDetail(r));
  return r.json();
}

export async function pushExportAll(): Promise<JiraPushAllRow[]> {
  const r = await fetch("/api/export/push-all", { method: "POST" });
  if (!r.ok) throw new Error(await _parseDetail(r));
  return (await r.json()).results;
}
