"use client";

import { Fragment, useEffect, useState, useCallback } from "react";
import { secrets, alerts } from "@/lib/api";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#94a3b8",
};

const SEVERITY_BG: Record<string, string> = {
  critical: "rgba(239,68,68,0.15)",
  high: "rgba(249,115,22,0.15)",
  medium: "rgba(234,179,8,0.15)",
  low: "rgba(148,163,184,0.10)",
};

export default function SecretsPage() {
  const [stats, setStats] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [scanning, setScanning] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const data = await secrets.stats();
      setStats(data);
    } catch {}
  }, []);

  const fetchSecrets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {
        page: String(page),
        page_size: "50",
        dismissed: "false",
      };
      if (severityFilter) params.severity = severityFilter;
      if (categoryFilter) params.secret_category = categoryFilter;
      const data = await secrets.list(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [page, severityFilter, categoryFilter]);

  useEffect(() => {
    fetchStats();
    fetchSecrets();
  }, [fetchStats, fetchSecrets]);

  const handleExpand = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    try {
      const d = await secrets.get(id);
      setDetail(d);
      setExpandedId(id);
    } catch {}
  };

  const handleReview = async (id: string, dismissed: boolean) => {
    await secrets.review(id, { is_reviewed: true, dismissed });
    fetchSecrets();
    fetchStats();
  };

  const handleRunScan = async () => {
    setScanning(true);
    try {
      await secrets.scan();
      // Poll briefly for results to appear
      setTimeout(() => {
        fetchSecrets();
        fetchStats();
        setScanning(false);
      }, 3000);
    } catch {
      setScanning(false);
    }
  };

  return (
    <div style={{ padding: "24px", maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>
          Discovered Secrets & Credentials
        </h1>
        <button
          onClick={handleRunScan}
          disabled={scanning}
          style={{
            background: scanning ? "#334155" : "#6366f1",
            color: "#fff",
            border: "none",
            borderRadius: 6,
            padding: "8px 16px",
            cursor: scanning ? "default" : "pointer",
            fontWeight: 600,
          }}
        >
          {scanning ? "Scanning..." : "Run Secret Scan"}
        </button>
      </div>

      {/* Stats cards */}
      {stats && (
        <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
          {["critical", "high", "medium", "low"].map((sev) => (
            <div
              key={sev}
              style={{
                background: SEVERITY_BG[sev],
                border: `1px solid ${SEVERITY_COLORS[sev]}`,
                borderRadius: 8,
                padding: "12px 20px",
                minWidth: 120,
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: 28, fontWeight: 700, color: SEVERITY_COLORS[sev] }}>
                {stats.by_severity?.[sev] || 0}
              </div>
              <div style={{ fontSize: 12, textTransform: "uppercase", color: "#94a3b8" }}>
                {sev}
              </div>
            </div>
          ))}
          <div
            style={{
              background: "rgba(99,102,241,0.10)",
              border: "1px solid #6366f1",
              borderRadius: 8,
              padding: "12px 20px",
              minWidth: 120,
              textAlign: "center",
            }}
          >
            <div style={{ fontSize: 28, fontWeight: 700, color: "#6366f1" }}>
              {stats.unreviewed || 0}
            </div>
            <div style={{ fontSize: 12, textTransform: "uppercase", color: "#94a3b8" }}>
              Unreviewed
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <select
          value={severityFilter}
          onChange={(e) => { setSeverityFilter(e.target.value); setPage(1); }}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px" }}
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); }}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px" }}
        >
          <option value="">All Categories</option>
          <option value="credential">Credentials</option>
          <option value="crypto_wallet">Crypto Wallets</option>
          <option value="api_key">API Keys</option>
          <option value="private_key">Private Keys</option>
          <option value="token">Tokens</option>
        </select>
      </div>

      {error && <div style={{ color: "#ef4444", marginBottom: 12 }}>{error}</div>}
      {loading && <div style={{ color: "#94a3b8" }}>Loading...</div>}

      {/* Table */}
      {!loading && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #334155", color: "#94a3b8", fontSize: 12, textTransform: "uppercase" }}>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Severity</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Type</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Masked Value</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Source File</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Confidence</th>
              <th style={{ textAlign: "center", padding: "8px 12px" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s: any) => (
              <Fragment key={s.id}>
                <tr
                  onClick={() => handleExpand(s.id)}
                  style={{
                    borderBottom: "1px solid #1e293b",
                    cursor: "pointer",
                    background: expandedId === s.id ? "#1e293b" : "transparent",
                  }}
                >
                  <td style={{ padding: "8px 12px" }}>
                    <span
                      style={{
                        color: SEVERITY_COLORS[s.severity] || "#94a3b8",
                        fontWeight: 700,
                        fontSize: 12,
                        textTransform: "uppercase",
                      }}
                    >
                      {s.severity}
                    </span>
                  </td>
                  <td style={{ padding: "8px 12px", color: "#e2e8f0" }}>{s.secret_type}</td>
                  <td style={{ padding: "8px 12px", fontFamily: "monospace", color: "#67e8f9" }}>
                    {s.masked_value || "****"}
                  </td>
                  <td style={{ padding: "8px 12px" }}>
                    {s.file_name ? (
                      <a
                        href={`/evidence/${s.file_id}`}
                        onClick={(e) => e.stopPropagation()}
                        style={{ color: "#6366f1", textDecoration: "underline", fontSize: 13 }}
                        title={s.original_path || s.file_name}
                      >
                        {s.file_name.length > 30 ? s.file_name.slice(0, 27) + "..." : s.file_name}
                      </a>
                    ) : (
                      <span style={{ color: "#475569", fontSize: 12 }}>{s.file_id?.slice(0, 8)}...</span>
                    )}
                  </td>
                  <td style={{ padding: "8px 12px", color: "#94a3b8" }}>
                    {((s.confidence || 0) * 100).toFixed(0)}%
                  </td>
                  <td style={{ padding: "8px 12px", textAlign: "center" }}>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleReview(s.id, true); }}
                      style={{
                        background: "#334155",
                        color: "#94a3b8",
                        border: "none",
                        borderRadius: 4,
                        padding: "4px 8px",
                        cursor: "pointer",
                        fontSize: 11,
                      }}
                    >
                      Dismiss
                    </button>
                  </td>
                </tr>
                {expandedId === s.id && detail && (
                  <tr key={`${s.id}-detail`}>
                    <td colSpan={7} style={{ padding: "12px 24px", background: "#0f172a" }}>
                      <div style={{ marginBottom: 8 }}>
                        <strong style={{ color: "#94a3b8" }}>Full Value:</strong>{" "}
                        <code style={{ color: "#f97316", wordBreak: "break-all" }}>
                          {detail.detected_value}
                        </code>
                      </div>
                      <div style={{ marginBottom: 8 }}>
                        <strong style={{ color: "#94a3b8" }}>Context:</strong>
                        <pre style={{ color: "#e2e8f0", whiteSpace: "pre-wrap", fontSize: 12, marginTop: 4, background: "#1e293b", padding: 8, borderRadius: 4 }}>
                          {detail.context_snippet}
                        </pre>
                      </div>
                      <div style={{ fontSize: 12, color: "#64748b", marginTop: 8 }}>
                        File: <a href={`/evidence/${detail.file_id}`} style={{ color: "#6366f1" }}>
                          {(s as any).file_name || detail.file_id}
                        </a>
                        {(s as any).original_path && (
                          <span style={{ marginLeft: 8, color: "#475569" }}>
                            ({(s as any).original_path})
                          </span>
                        )}
                        {" "}| Offset: {detail.char_offset} | Category: {detail.secret_category} | Method: {detail.detection_method}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}

      {/* Pagination */}
      {total > 50 && (
        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 16 }}>
          <button
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
            style={{ background: "#334155", color: "#e2e8f0", border: "none", borderRadius: 4, padding: "6px 12px", cursor: page > 1 ? "pointer" : "default" }}
          >
            Prev
          </button>
          <span style={{ color: "#94a3b8", padding: "6px 12px" }}>
            Page {page} of {Math.ceil(total / 50)}
          </span>
          <button
            disabled={page >= Math.ceil(total / 50)}
            onClick={() => setPage(page + 1)}
            style={{ background: "#334155", color: "#e2e8f0", border: "none", borderRadius: 4, padding: "6px 12px", cursor: "pointer" }}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
