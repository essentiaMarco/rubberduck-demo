/**
 * API client for the Rubberduck backend.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

// ── Cases ──────────────────────────────────────────────────
export const cases = {
  list: () => apiFetch<any[]>("/api/cases"),
  get: (id: string) => apiFetch<any>(`/api/cases/${id}`),
  create: (data: any) =>
    apiFetch<any>("/api/cases", { method: "POST", body: JSON.stringify(data) }),
};

// ── Evidence ───────────────────────────────────────────────
export const evidence = {
  listSources: (caseId?: string) =>
    apiFetch<any[]>(`/api/evidence/sources${caseId ? `?case_id=${caseId}` : ""}`),
  listFiles: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/evidence/files?${qs}`);
  },
  getFile: (id: string) => apiFetch<any>(`/api/evidence/files/${id}`),
  getContent: (id: string) => apiFetch<any>(`/api/evidence/files/${id}/content`),
  getCustody: (id: string) => apiFetch<any[]>(`/api/evidence/files/${id}/custody`),
  getStats: () => apiFetch<any>("/api/evidence/stats"),
  ingestDirectory: (sourceId: string, path: string) =>
    apiFetch<any>("/api/evidence/ingest/directory", {
      method: "POST",
      body: JSON.stringify({ source_id: sourceId, path }),
    }),
};

// ── Search ─────────────────────────────────────────────────
export const search = {
  query: (data: any) =>
    apiFetch<any>("/api/search", { method: "POST", body: JSON.stringify(data) }),
  suggest: (prefix: string) =>
    apiFetch<any[]>(`/api/search/suggest?prefix=${encodeURIComponent(prefix)}`),
};

// ── Entities ───────────────────────────────────────────────
export const entities = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/entities?${qs}`);
  },
  get: (id: string) => apiFetch<any>(`/api/entities/${id}`),
  getMentions: (id: string) => apiFetch<any>(`/api/entities/${id}/mentions`),
  getRelationships: (id: string) => apiFetch<any[]>(`/api/entities/${id}/relationships`),
};

// ── Timeline ───────────────────────────────────────────────
export const timeline = {
  getEvents: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/timeline/events?${qs}`);
  },
  getStats: () => apiFetch<any>("/api/timeline/stats"),
};

// ── Graph ──────────────────────────────────────────────────
export const graph = {
  getFull: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/graph?${qs}`);
  },
  getNeighborhood: (entityId: string, depth: number = 2) =>
    apiFetch<any>(`/api/graph/neighborhood/${entityId}?depth=${depth}`),
  getAnalysis: () => apiFetch<any>("/api/graph/analysis"),
};

// ── Hypotheses ─────────────────────────────────────────────
export const hypotheses = {
  list: (caseId?: string) =>
    apiFetch<any>(`/api/hypotheses${caseId ? `?case_id=${caseId}` : ""}`),
  get: (id: string) => apiFetch<any>(`/api/hypotheses/${id}`),
  create: (data: any) =>
    apiFetch<any>("/api/hypotheses", { method: "POST", body: JSON.stringify(data) }),
  evaluate: (id: string) =>
    apiFetch<any>(`/api/hypotheses/${id}/evaluate`, { method: "POST" }),
};

// ── Legal ──────────────────────────────────────────────────
export const legal = {
  listTemplates: () => apiFetch<any[]>("/api/legal/templates"),
  listDocuments: (caseId?: string) =>
    apiFetch<any>(`/api/legal/documents${caseId ? `?case_id=${caseId}` : ""}`),
  getDocument: (id: string) => apiFetch<any>(`/api/legal/documents/${id}`),
  getGapAnalysis: (caseId: string) => apiFetch<any>(`/api/legal/gap-analysis/${caseId}`),
  buildGoogleOrder: (data: any) =>
    apiFetch<any>("/api/legal/google-order", { method: "POST", body: JSON.stringify(data) }),
};

// ── Analysis ──────────────────────────────────────────────
export const analysis = {
  runFull: () =>
    apiFetch<any>("/api/analysis/run", { method: "POST" }),
};

// ── Jobs ───────────────────────────────────────────────────
export const jobs = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/jobs?${qs}`);
  },
  get: (id: string) => apiFetch<any>(`/api/jobs/${id}`),
  cancel: (id: string) =>
    apiFetch<any>(`/api/jobs/${id}/cancel`, { method: "POST" }),
};
