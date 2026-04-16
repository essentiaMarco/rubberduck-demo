"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";

const financial = {
  transactions: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/financial/transactions?${qs}`);
  },
  stats: () => apiFetch<any>("/api/financial/stats"),
  anomalies: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any>(`/api/financial/anomalies?${qs}`);
  },
  detectAnomalies: () => apiFetch<any>("/api/financial/detect-anomalies", { method: "POST" }),
};

function formatAmount(amount: number | null): string {
  if (amount === null || amount === undefined) return "--";
  const sign = amount >= 0 ? "+" : "";
  return `${sign}$${Math.abs(amount).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function amountColor(amount: number): string {
  if (amount > 0) return "#10b981";
  if (amount < 0) return "#ef4444";
  return "#94a3b8";
}

type Tab = "transactions" | "anomalies";

export default function FinancialPage() {
  const [tab, setTab] = useState<Tab>("transactions");
  const [stats, setStats] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");

  const fetchStats = useCallback(async () => {
    try {
      const data = await financial.stats();
      setStats(data);
    } catch {}
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { page: String(page), page_size: "50" };
      if (categoryFilter) params.category = categoryFilter;
      if (typeFilter) params.transaction_type = typeFilter;

      const data = tab === "anomalies"
        ? await financial.anomalies(params)
        : await financial.transactions(params);
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch {}
    setLoading(false);
  }, [page, tab, categoryFilter, typeFilter]);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { fetchData(); }, [fetchData]);

  return (
    <div style={{ padding: "24px", maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Financial Intelligence</h1>
        <button
          onClick={async () => { await financial.detectAnomalies(); fetchData(); fetchStats(); }}
          style={{ background: "#6366f1", color: "#fff", border: "none", borderRadius: 6, padding: "8px 16px", cursor: "pointer", fontWeight: 600 }}
        >
          Detect Anomalies
        </button>
      </div>

      {/* Stats cards */}
      {stats && (
        <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
          <div style={{ background: "#1e293b", borderRadius: 8, padding: "12px 20px", minWidth: 130, textAlign: "center", border: "1px solid #334155" }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#e2e8f0" }}>{stats.total_transactions || 0}</div>
            <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase" }}>Transactions</div>
          </div>
          <div style={{ background: "#1e293b", borderRadius: 8, padding: "12px 20px", minWidth: 130, textAlign: "center", border: "1px solid #10b981" }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#10b981" }}>${(stats.total_inflow || 0).toLocaleString()}</div>
            <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase" }}>Inflow</div>
          </div>
          <div style={{ background: "#1e293b", borderRadius: 8, padding: "12px 20px", minWidth: 130, textAlign: "center", border: "1px solid #ef4444" }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#ef4444" }}>${(stats.total_outflow || 0).toLocaleString()}</div>
            <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase" }}>Outflow</div>
          </div>
          <div style={{ background: "#1e293b", borderRadius: 8, padding: "12px 20px", minWidth: 130, textAlign: "center", border: "1px solid #f97316" }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: "#f97316" }}>{stats.anomaly_count || 0}</div>
            <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase" }}>Anomalies</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, marginBottom: 16, borderBottom: "1px solid #334155" }}>
        {(["transactions", "anomalies"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => { setTab(t); setPage(1); }}
            style={{
              padding: "8px 20px", border: "none",
              borderBottom: tab === t ? "2px solid #6366f1" : "2px solid transparent",
              background: "transparent", color: tab === t ? "#e2e8f0" : "#64748b",
              cursor: "pointer", fontWeight: tab === t ? 600 : 400, textTransform: "capitalize",
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setPage(1); }}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px" }}
        >
          <option value="">All Categories</option>
          {["salary", "rent", "transfer", "cash", "crypto", "insurance", "utilities", "food", "purchase", "unknown"].map(c => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <select
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px" }}
        >
          <option value="">All Types</option>
          <option value="credit">Credit</option>
          <option value="debit">Debit</option>
          <option value="transfer">Transfer</option>
        </select>
      </div>

      {loading && <div style={{ color: "#94a3b8" }}>Loading...</div>}

      {!loading && (
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #334155", color: "#94a3b8", fontSize: 12, textTransform: "uppercase" }}>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Date</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Description</th>
              <th style={{ textAlign: "right", padding: "8px 12px" }}>Amount</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Category</th>
              <th style={{ textAlign: "left", padding: "8px 12px" }}>Type</th>
              {tab === "anomalies" && <th style={{ textAlign: "left", padding: "8px 12px" }}>Reasons</th>}
              <th style={{ textAlign: "right", padding: "8px 12px" }}>Balance</th>
            </tr>
          </thead>
          <tbody>
            {items.map((tx: any) => (
              <tr
                key={tx.id}
                style={{
                  borderBottom: "1px solid #1e293b",
                  background: tx.is_anomaly ? "rgba(249,115,22,0.08)" : "transparent",
                }}
              >
                <td style={{ padding: "8px 12px", color: "#94a3b8", fontSize: 13 }}>
                  {tx.transaction_date ? new Date(tx.transaction_date).toLocaleDateString() : "--"}
                </td>
                <td style={{ padding: "8px 12px", color: "#e2e8f0", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {tx.description || "--"}
                </td>
                <td style={{ padding: "8px 12px", textAlign: "right", fontWeight: 600, fontFamily: "monospace", color: amountColor(tx.amount) }}>
                  {formatAmount(tx.amount)}
                </td>
                <td style={{ padding: "8px 12px", color: "#94a3b8", fontSize: 12 }}>{tx.category || "--"}</td>
                <td style={{ padding: "8px 12px", color: "#94a3b8", fontSize: 12 }}>{tx.transaction_type || "--"}</td>
                {tab === "anomalies" && (
                  <td style={{ padding: "8px 12px", color: "#f97316", fontSize: 12, maxWidth: 250 }}>
                    {(tx.anomaly_reasons || []).join("; ").slice(0, 100)}
                  </td>
                )}
                <td style={{ padding: "8px 12px", textAlign: "right", color: "#64748b", fontFamily: "monospace", fontSize: 12 }}>
                  {tx.balance_after != null ? `$${tx.balance_after.toLocaleString()}` : "--"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {!loading && items.length === 0 && (
        <div style={{ textAlign: "center", color: "#64748b", padding: 40 }}>
          No financial transactions yet. Import a CSV bank statement to begin analysis.
        </div>
      )}

      {total > 50 && (
        <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 16 }}>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} style={{ background: "#334155", color: "#e2e8f0", border: "none", borderRadius: 4, padding: "6px 12px", cursor: "pointer" }}>Prev</button>
          <span style={{ color: "#94a3b8", padding: "6px 12px" }}>Page {page} of {Math.ceil(total / 50)}</span>
          <button onClick={() => setPage(page + 1)} style={{ background: "#334155", color: "#e2e8f0", border: "none", borderRadius: 4, padding: "6px 12px", cursor: "pointer" }}>Next</button>
        </div>
      )}
    </div>
  );
}
