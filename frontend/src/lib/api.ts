/**
 * API client for the Rubberduck backend.
 */

// Use relative URLs so requests go through the Next.js rewrite proxy.
// This ensures the app works on LAN (any device hits Next.js, which proxies to the backend).
const API_BASE = "";

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
  getContent: (id: string, params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/evidence/files/${id}/content${qs ? `?${qs}` : ""}`);
  },
  searchContent: (id: string, query: string, params: Record<string, string> = {}) => {
    const qs = new URLSearchParams({ q: query, ...params }).toString();
    return apiFetch<any>(`/api/evidence/files/${id}/content/search?${qs}`);
  },
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
    apiFetch<any>("/api/search/", { method: "POST", body: JSON.stringify(data) }),
  suggest: (prefix: string) =>
    apiFetch<any[]>(`/api/search/suggest?prefix=${encodeURIComponent(prefix)}`),
};

// ── Entities ───────────────────────────────────────────────
export const entities = {
  list: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/entities/?${qs}`);
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
    return apiFetch<any>(`/api/graph/?${qs}`);
  },
  getNeighborhood: (entityId: string, depth: number = 2) =>
    apiFetch<any>(`/api/graph/neighborhood/${entityId}?depth=${depth}`),
  getAnalysis: () => apiFetch<any>("/api/graph/analysis"),
};

// ── Hypotheses ─────────────────────────────────────────────
export const hypotheses = {
  list: (caseId?: string) =>
    apiFetch<any>(`/api/hypotheses/${caseId ? `?case_id=${caseId}` : ""}`),
  get: (id: string) => apiFetch<any>(`/api/hypotheses/${id}`),
  create: (data: any) =>
    apiFetch<any>("/api/hypotheses", { method: "POST", body: JSON.stringify(data) }),
  evaluate: (id: string) =>
    apiFetch<any>(`/api/hypotheses/${id}/evaluate`, { method: "POST" }),
};

// ── Hypotheses ─────────────────────────────────────────────
// (extended with missing methods)
export const hypothesesExt = {
  addFinding: (hypId: string, data: any) =>
    apiFetch<any>(`/api/hypotheses/${hypId}/findings`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteFinding: (hypId: string, findingId: string) =>
    apiFetch<any>(`/api/hypotheses/${hypId}/findings/${findingId}`, { method: "DELETE" }),
  update: (hypId: string, data: any) =>
    apiFetch<any>(`/api/hypotheses/${hypId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};

// ── Legal ──────────────────────────────────────────────────
export const legal = {
  listTemplates: () => apiFetch<any[]>("/api/legal/templates"),
  listDocuments: (caseId?: string) =>
    apiFetch<any>(`/api/legal/documents${caseId ? `?case_id=${caseId}` : ""}`),
  getDocument: (id: string) => apiFetch<any>(`/api/legal/documents/${id}`),
  createDocument: (data: any) =>
    apiFetch<any>("/api/legal/documents", { method: "POST", body: JSON.stringify(data) }),
  renderDocument: (id: string) =>
    apiFetch<any>(`/api/legal/documents/${id}/render`, { method: "POST" }),
  getGapAnalysis: (caseId: string) => apiFetch<any>(`/api/legal/gap-analysis/${caseId}`),
  buildGoogleOrder: (data: any) =>
    apiFetch<any>("/api/legal/google-order", { method: "POST", body: JSON.stringify(data) }),
};

// ── OSINT ─────────────────────────────────────────────────
export const osint = {
  listPlans: (caseId?: string) => {
    const qs = caseId ? `?case_id=${caseId}` : "";
    return apiFetch<any[]>(`/api/osint/plans${qs}`);
  },
  createPlan: (data: any) =>
    apiFetch<any>("/api/osint/plans", { method: "POST", body: JSON.stringify(data) }),
  approvePlan: (planId: string) =>
    apiFetch<any>(`/api/osint/plans/${planId}/approve`, { method: "PATCH" }),
  listCaptures: (planId?: string) => {
    const qs = planId ? `?plan_id=${planId}` : "";
    return apiFetch<any[]>(`/api/osint/captures${qs}`);
  },
};

// ── Communications ───────────────────────────────────────
export const communications = {
  listMessages: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/communications/messages?${qs}`);
  },
  getMessage: (id: string) => apiFetch<any>(`/api/communications/messages/${id}`),
  getStats: () => apiFetch<any>("/api/communications/stats"),
  getThreads: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/communications/threads?${qs}`);
  },
  extractEmails: (reprocess: boolean = false) =>
    apiFetch<any>(`/api/communications/extract?reprocess=${reprocess}`, { method: "POST" }),
  extractFromFile: (fileId: string, reprocess: boolean = false) =>
    apiFetch<any>(`/api/communications/extract/${fileId}?reprocess=${reprocess}`, { method: "POST" }),
};

// ── Phone Analysis ──────────────────────────────────────
export const phoneAnalysis = {
  listRecords: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/phone-analysis/records?${qs}`);
  },
  getRecord: (id: string) => apiFetch<any>(`/api/phone-analysis/records/${id}`),
  getStats: () => apiFetch<any>("/api/phone-analysis/stats"),
  getContacts: () => apiFetch<any>("/api/phone-analysis/contacts"),
  getHeatmap: () => apiFetch<any>("/api/phone-analysis/heatmap"),
  getAnomalies: () => apiFetch<any>("/api/phone-analysis/anomalies"),
  getMonthly: () => apiFetch<any>("/api/phone-analysis/monthly"),
  getNewContacts: () => apiFetch<any>("/api/phone-analysis/new-contacts"),
  getPatternChanges: () => apiFetch<any>("/api/phone-analysis/pattern-changes"),
  getNumberTimeline: (number: string) => apiFetch<any>(`/api/phone-analysis/number/${number}`),
  ingest: (folderPath: string, reprocess: boolean = false) =>
    apiFetch<any>(`/api/phone-analysis/?folder_path=${encodeURIComponent(folderPath)}&reprocess=${reprocess}`, { method: "POST" }),
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
