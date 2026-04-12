"use client";

import { useEffect, useState, useCallback } from "react";
import { alerts, watchlist } from "@/lib/api";

const SEVERITY_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#94a3b8",
  info: "#6366f1",
};

type Tab = "alerts" | "watchlist";

export default function AlertsPage() {
  const [tab, setTab] = useState<Tab>("alerts");
  const [stats, setStats] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState("");
  const [showDismissed, setShowDismissed] = useState(false);
  const [scanning, setScanning] = useState(false);

  // Watchlist state
  const [watchlistItems, setWatchlistItems] = useState<any[]>([]);
  const [newTerm, setNewTerm] = useState("");
  const [newCategory, setNewCategory] = useState("");
  const [newIsRegex, setNewIsRegex] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const data = await alerts.stats();
      setStats(data);
    } catch {}
  }, []);

  const fetchAlerts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {
        page: String(page),
        page_size: "50",
      };
      if (!showDismissed) params.dismissed = "false";
      if (severityFilter) params.severity = severityFilter;
      const data = await alerts.list(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [page, severityFilter, showDismissed]);

  const fetchWatchlist = useCallback(async () => {
    try {
      const data = await watchlist.list();
      setWatchlistItems(data || []);
    } catch {}
  }, []);

  useEffect(() => {
    fetchStats();
    if (tab === "alerts") fetchAlerts();
    if (tab === "watchlist") fetchWatchlist();
  }, [tab, fetchStats, fetchAlerts, fetchWatchlist]);

  const handleDismiss = async (id: string) => {
    await alerts.dismiss(id);
    fetchAlerts();
    fetchStats();
  };

  const handleRunScan = async () => {
    setScanning(true);
    try {
      await alerts.run();
      fetchAlerts();
      fetchStats();
    } finally {
      setScanning(false);
    }
  };

  const handleAddWatchlist = async () => {
    if (!newTerm.trim()) return;
    await watchlist.add({
      term: newTerm,
      category: newCategory || null,
      is_regex: newIsRegex,
    });
    setNewTerm("");
    setNewCategory("");
    setNewIsRegex(false);
    fetchWatchlist();
  };

  const handleRemoveWatchlist = async (id: string) => {
    await watchlist.remove(id);
    fetchWatchlist();
  };

  return (
    <div style={{ padding: "24px", maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Forensic Alerts</h1>
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
          {scanning ? "Scanning..." : "Run Alert Scan"}
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
          {["critical", "high", "medium", "low"].map((sev) => (
            <div
              key={sev}
              style={{
                background: `${SEVERITY_COLORS[sev]}20`,
                border: `1px solid ${SEVERITY_COLORS[sev]}`,
                borderRadius: 8,
                padding: "12px 20px",
                minWidth: 100,
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: 28, fontWeight: 700, color: SEVERITY_COLORS[sev] }}>
                {stats.by_severity?.[sev] || 0}
              </div>
              <div style={{ fontSize: 12, textTransform: "uppercase", color: "#94a3b8" }}>{sev}</div>
            </div>
          ))}
          <div style={{ background: "rgba(16,185,129,0.10)", border: "1px solid #10b981", borderRadius: 8, padding: "12px 20px", minWidth: 120, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#10b981" }}>{stats.unreviewed || 0}</div>
            <div style={{ fontSize: 12, textTransform: "uppercase", color: "#94a3b8" }}>Active</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "1px solid #334155" }}>
        {(["alerts", "watchlist"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "8px 20px",
              border: "none",
              borderBottom: tab === t ? "2px solid #6366f1" : "2px solid transparent",
              background: "transparent",
              color: tab === t ? "#e2e8f0" : "#64748b",
              cursor: "pointer",
              fontWeight: tab === t ? 600 : 400,
              textTransform: "capitalize",
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Alerts Tab */}
      {tab === "alerts" && (
        <>
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
            <label style={{ display: "flex", alignItems: "center", gap: 6, color: "#94a3b8", fontSize: 13 }}>
              <input
                type="checkbox"
                checked={showDismissed}
                onChange={(e) => setShowDismissed(e.target.checked)}
              />
              Show dismissed
            </label>
          </div>

          {error && <div style={{ color: "#ef4444", marginBottom: 12 }}>{error}</div>}
          {loading && <div style={{ color: "#94a3b8" }}>Loading...</div>}

          {!loading && items.map((a: any) => (
            <div
              key={a.id}
              style={{
                background: a.dismissed ? "#0f172a" : "#1e293b",
                borderLeft: `4px solid ${SEVERITY_COLORS[a.severity] || "#94a3b8"}`,
                borderRadius: 6,
                padding: "12px 16px",
                marginBottom: 8,
                opacity: a.dismissed ? 0.5 : 1,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <span
                    style={{
                      color: SEVERITY_COLORS[a.severity],
                      fontWeight: 700,
                      fontSize: 11,
                      textTransform: "uppercase",
                      marginRight: 8,
                    }}
                  >
                    {a.severity}
                  </span>
                  <span style={{ color: "#e2e8f0", fontWeight: 600 }}>{a.title}</span>
                  <span style={{ color: "#64748b", fontSize: 12, marginLeft: 12 }}>{a.alert_type}</span>
                </div>
                {!a.dismissed && (
                  <button
                    onClick={() => handleDismiss(a.id)}
                    style={{
                      background: "#334155",
                      color: "#94a3b8",
                      border: "none",
                      borderRadius: 4,
                      padding: "4px 10px",
                      cursor: "pointer",
                      fontSize: 11,
                    }}
                  >
                    Dismiss
                  </button>
                )}
              </div>
              {a.description && (
                <div style={{ color: "#94a3b8", fontSize: 13, marginTop: 6 }}>{a.description}</div>
              )}
              {a.file_name && (
                <div style={{ fontSize: 12, marginTop: 4 }}>
                  Source: <a href={`/evidence/${a.evidence_file_id}`} style={{ color: "#6366f1", textDecoration: "underline" }}>
                    {a.file_name}
                  </a>
                  {a.original_path && (
                    <span style={{ color: "#475569", marginLeft: 6 }}>({a.original_path})</span>
                  )}
                </div>
              )}
              <div style={{ color: "#475569", fontSize: 11, marginTop: 4 }}>
                {a.created_at ? new Date(a.created_at).toLocaleString() : ""} | Rule: {a.rule_name || "manual"}
              </div>
            </div>
          ))}

          {total > 50 && (
            <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 16 }}>
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} style={{ background: "#334155", color: "#e2e8f0", border: "none", borderRadius: 4, padding: "6px 12px", cursor: "pointer" }}>Prev</button>
              <span style={{ color: "#94a3b8", padding: "6px 12px" }}>Page {page}</span>
              <button onClick={() => setPage(page + 1)} style={{ background: "#334155", color: "#e2e8f0", border: "none", borderRadius: 4, padding: "6px 12px", cursor: "pointer" }}>Next</button>
            </div>
          )}
        </>
      )}

      {/* Watchlist Tab */}
      {tab === "watchlist" && (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
            <input
              type="text"
              placeholder="Term or regex pattern..."
              value={newTerm}
              onChange={(e) => setNewTerm(e.target.value)}
              style={{ flex: 1, background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "8px 12px" }}
            />
            <select
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "8px 12px" }}
            >
              <option value="">Category</option>
              <option value="person">Person</option>
              <option value="phone">Phone</option>
              <option value="email">Email</option>
              <option value="keyword">Keyword</option>
              <option value="account">Account</option>
              <option value="location">Location</option>
            </select>
            <label style={{ display: "flex", alignItems: "center", gap: 4, color: "#94a3b8", fontSize: 13, whiteSpace: "nowrap" }}>
              <input type="checkbox" checked={newIsRegex} onChange={(e) => setNewIsRegex(e.target.checked)} />
              Regex
            </label>
            <button
              onClick={handleAddWatchlist}
              style={{ background: "#6366f1", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: "pointer", fontWeight: 600, whiteSpace: "nowrap" }}
            >
              Add
            </button>
          </div>

          {watchlistItems.length === 0 ? (
            <div style={{ color: "#64748b", textAlign: "center", padding: 40 }}>
              No watchlist entries. Add terms above to get alerts when they appear in evidence.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #334155", color: "#94a3b8", fontSize: 12, textTransform: "uppercase" }}>
                  <th style={{ textAlign: "left", padding: "8px 12px" }}>Term</th>
                  <th style={{ textAlign: "left", padding: "8px 12px" }}>Category</th>
                  <th style={{ textAlign: "left", padding: "8px 12px" }}>Type</th>
                  <th style={{ textAlign: "left", padding: "8px 12px" }}>Severity</th>
                  <th style={{ textAlign: "center", padding: "8px 12px" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {watchlistItems.map((w: any) => (
                  <tr key={w.id} style={{ borderBottom: "1px solid #1e293b" }}>
                    <td style={{ padding: "8px 12px", fontFamily: "monospace", color: "#67e8f9" }}>{w.term}</td>
                    <td style={{ padding: "8px 12px", color: "#94a3b8" }}>{w.category || "--"}</td>
                    <td style={{ padding: "8px 12px", color: "#94a3b8" }}>{w.is_regex ? "Regex" : "Keyword"}</td>
                    <td style={{ padding: "8px 12px" }}>
                      <span style={{ color: SEVERITY_COLORS[w.severity] || "#94a3b8", fontWeight: 600, fontSize: 12, textTransform: "uppercase" }}>
                        {w.severity}
                      </span>
                    </td>
                    <td style={{ padding: "8px 12px", textAlign: "center" }}>
                      <button
                        onClick={() => handleRemoveWatchlist(w.id)}
                        style={{ background: "#7f1d1d", color: "#fca5a5", border: "none", borderRadius: 4, padding: "4px 10px", cursor: "pointer", fontSize: 11 }}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
