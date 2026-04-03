"use client";

import { useEffect, useState, useCallback } from "react";
import { phoneAnalysis } from "@/lib/api";

type Tab = "calllog" | "contacts" | "heatmap" | "anomalies" | "monthly" | "newcontacts";

const CALL_TYPES = [
  { value: "", label: "All Types" },
  { value: "Local", label: "Local" },
  { value: "STD", label: "STD" },
  { value: "ISD", label: "ISD" },
];

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds && seconds !== 0) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function formatPhone(num: string | null | undefined): string {
  if (!num) return "--";
  const digits = num.replace(/\D/g, "");
  if (digits.length === 10) {
    return `${digits.slice(0, 5)} ${digits.slice(5)}`;
  }
  if (digits.length === 12 && digits.startsWith("91")) {
    return `+91 ${digits.slice(2, 7)} ${digits.slice(7)}`;
  }
  return num;
}

function anomalyColor(score: number): string {
  if (score > 0.4) return "#ef4444";
  if (score > 0.2) return "#f97316";
  if (score > 0.1) return "#eab308";
  return "#94a3b8";
}

export default function PhoneAnalysisPage() {
  const [tab, setTab] = useState<Tab>("calllog");
  const [stats, setStats] = useState<any>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState<string | null>(null);

  // Call Log state
  const [records, setRecords] = useState<any[]>([]);
  const [recordsTotal, setRecordsTotal] = useState(0);
  const [recordsPage, setRecordsPage] = useState(1);
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [recordsError, setRecordsError] = useState<string | null>(null);
  const [phoneFilter, setPhoneFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [anomalyOnly, setAnomalyOnly] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<any>(null);

  // Contacts state
  const [contacts, setContacts] = useState<any[]>([]);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [contactsError, setContactsError] = useState<string | null>(null);
  const [numberTimeline, setNumberTimeline] = useState<any>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);

  // Heatmap state
  const [heatmap, setHeatmap] = useState<any>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [heatmapError, setHeatmapError] = useState<string | null>(null);

  // Anomalies state
  const [anomalies, setAnomalies] = useState<any[]>([]);
  const [anomaliesLoading, setAnomaliesLoading] = useState(false);
  const [anomaliesError, setAnomaliesError] = useState<string | null>(null);

  // Monthly state
  const [monthly, setMonthly] = useState<any[]>([]);
  const [patternChanges, setPatternChanges] = useState<any[]>([]);
  const [monthlyLoading, setMonthlyLoading] = useState(false);
  const [monthlyError, setMonthlyError] = useState<string | null>(null);

  // New contacts state
  const [newContacts, setNewContacts] = useState<any[]>([]);
  const [newContactsLoading, setNewContactsLoading] = useState(false);
  const [newContactsError, setNewContactsError] = useState<string | null>(null);

  const pageSize = 50;

  // Fetch stats on mount
  useEffect(() => {
    (async () => {
      setStatsLoading(true);
      try {
        const s = await phoneAnalysis.getStats();
        setStats(s);
      } catch (err: any) {
        setStatsError(err.message);
      } finally {
        setStatsLoading(false);
      }
    })();
  }, []);

  // Fetch call log records
  const fetchRecords = useCallback(async () => {
    setRecordsLoading(true);
    setRecordsError(null);
    try {
      const params: Record<string, string> = {
        page: String(recordsPage),
        page_size: String(pageSize),
      };
      if (phoneFilter) params.phone_number = phoneFilter;
      if (typeFilter) params.call_type = typeFilter;
      if (dateStart) params.date_start = dateStart;
      if (dateEnd) params.date_end = dateEnd;
      if (anomalyOnly) params.anomaly_only = "true";

      const data = await phoneAnalysis.listRecords(params);
      setRecords(data.items || []);
      setRecordsTotal(data.total || 0);
    } catch (err: any) {
      setRecordsError(err.message);
    } finally {
      setRecordsLoading(false);
    }
  }, [recordsPage, phoneFilter, typeFilter, dateStart, dateEnd, anomalyOnly]);

  useEffect(() => {
    if (tab === "calllog") fetchRecords();
  }, [tab, fetchRecords]);

  // Fetch contacts
  useEffect(() => {
    if (tab !== "contacts") return;
    (async () => {
      setContactsLoading(true);
      setContactsError(null);
      try {
        const data = await phoneAnalysis.getContacts();
        setContacts(data.contacts || data || []);
      } catch (err: any) {
        setContactsError(err.message);
      } finally {
        setContactsLoading(false);
      }
    })();
  }, [tab]);

  // Fetch heatmap
  useEffect(() => {
    if (tab !== "heatmap") return;
    (async () => {
      setHeatmapLoading(true);
      setHeatmapError(null);
      try {
        const data = await phoneAnalysis.getHeatmap();
        setHeatmap(data);
      } catch (err: any) {
        setHeatmapError(err.message);
      } finally {
        setHeatmapLoading(false);
      }
    })();
  }, [tab]);

  // Fetch anomalies
  useEffect(() => {
    if (tab !== "anomalies") return;
    (async () => {
      setAnomaliesLoading(true);
      setAnomaliesError(null);
      try {
        const data = await phoneAnalysis.getAnomalies();
        setAnomalies(data.anomalies || data || []);
      } catch (err: any) {
        setAnomaliesError(err.message);
      } finally {
        setAnomaliesLoading(false);
      }
    })();
  }, [tab]);

  // Fetch monthly + pattern changes
  useEffect(() => {
    if (tab !== "monthly") return;
    (async () => {
      setMonthlyLoading(true);
      setMonthlyError(null);
      try {
        const [m, p] = await Promise.all([
          phoneAnalysis.getMonthly(),
          phoneAnalysis.getPatternChanges(),
        ]);
        setMonthly(m.months || m || []);
        setPatternChanges(p.changes || p || []);
      } catch (err: any) {
        setMonthlyError(err.message);
      } finally {
        setMonthlyLoading(false);
      }
    })();
  }, [tab]);

  // Fetch new contacts
  useEffect(() => {
    if (tab !== "newcontacts") return;
    (async () => {
      setNewContactsLoading(true);
      setNewContactsError(null);
      try {
        const data = await phoneAnalysis.getNewContacts();
        setNewContacts(data.months || data || []);
      } catch (err: any) {
        setNewContactsError(err.message);
      } finally {
        setNewContactsLoading(false);
      }
    })();
  }, [tab]);

  const handleSelectRecord = async (rec: any) => {
    try {
      const full = await phoneAnalysis.getRecord(rec.id);
      setSelectedRecord(full);
    } catch {
      setSelectedRecord(rec);
    }
  };

  const handleNumberClick = async (number: string) => {
    setTimelineLoading(true);
    try {
      const data = await phoneAnalysis.getNumberTimeline(number);
      setNumberTimeline(data);
    } catch {
      setNumberTimeline(null);
    } finally {
      setTimelineLoading(false);
    }
  };

  const totalPages = Math.ceil(recordsTotal / pageSize);

  const TABS: { key: Tab; label: string }[] = [
    { key: "calllog", label: "Call Log" },
    { key: "contacts", label: "Contacts" },
    { key: "heatmap", label: "Heatmap" },
    { key: "anomalies", label: "Anomalies" },
    { key: "monthly", label: "Monthly" },
    { key: "newcontacts", label: "New Contacts" },
  ];

  // Find pattern change months for highlight
  const patternChangeMonths = new Set(
    patternChanges.map((pc: any) => pc.month || pc.period)
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Phone Analysis</h1>
      </div>

      {/* Stats bar */}
      {statsLoading && (
        <p className="text-slate-500 text-sm mb-4">Loading stats...</p>
      )}
      {statsError && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{statsError}</p>
        </div>
      )}
      {stats && (
        <div className="grid grid-cols-5 gap-3 mb-4">
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Total Calls</p>
            <p className="text-lg font-bold">
              {(stats.total_records ?? 0).toLocaleString()}
            </p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Unique Contacts</p>
            <p className="text-lg font-bold text-blue-400">
              {(stats.unique_contacts ?? 0).toLocaleString()}
            </p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Date Range</p>
            <p className="text-xs text-slate-300">
              {stats.date_range?.start?.slice(0, 10) ?? "--"} to{" "}
              {stats.date_range?.end?.slice(0, 10) ?? "--"}
            </p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Total Duration</p>
            <p className="text-lg font-bold text-green-400">
              {formatDuration(stats.total_duration_seconds)}
            </p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Anomalies Found</p>
            <p className="text-lg font-bold text-red-400">
              {(stats.anomaly_count ?? 0).toLocaleString()}
            </p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-4 bg-forensic-surface rounded-lg border border-forensic-border p-1">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              tab === t.key
                ? "bg-forensic-accent text-forensic-bg"
                : "text-slate-400 hover:text-slate-200 hover:bg-forensic-bg/50"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ─── Call Log Tab ──────────────────────────────────── */}
      {tab === "calllog" && (
        <>
          {/* Filters */}
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4 mb-4">
            <div className="flex items-center gap-3 flex-wrap">
              <input
                type="text"
                placeholder="Search phone number..."
                value={phoneFilter}
                onChange={(e) => setPhoneFilter(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setRecordsPage(1);
                    fetchRecords();
                  }
                }}
                className="flex-1 min-w-[200px] bg-forensic-bg border border-forensic-border rounded px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-forensic-accent"
              />
              <select
                value={typeFilter}
                onChange={(e) => {
                  setTypeFilter(e.target.value);
                  setRecordsPage(1);
                }}
                className="bg-forensic-bg border border-forensic-border rounded px-2 py-2 text-sm text-slate-300"
              >
                {CALL_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              <input
                type="date"
                value={dateStart}
                onChange={(e) => {
                  setDateStart(e.target.value);
                  setRecordsPage(1);
                }}
                className="bg-forensic-bg border border-forensic-border rounded px-2 py-2 text-sm text-slate-300"
              />
              <span className="text-slate-500 text-sm">to</span>
              <input
                type="date"
                value={dateEnd}
                onChange={(e) => {
                  setDateEnd(e.target.value);
                  setRecordsPage(1);
                }}
                className="bg-forensic-bg border border-forensic-border rounded px-2 py-2 text-sm text-slate-300"
              />
              <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={anomalyOnly}
                  onChange={(e) => {
                    setAnomalyOnly(e.target.checked);
                    setRecordsPage(1);
                  }}
                  className="accent-red-500"
                />
                Anomalies Only
              </label>
              <button
                onClick={() => {
                  setRecordsPage(1);
                  fetchRecords();
                }}
                className="bg-forensic-accent text-forensic-bg px-4 py-2 rounded text-sm font-medium hover:bg-forensic-accent/90"
              >
                Filter
              </button>
            </div>
          </div>

          {recordsError && (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
              <p className="text-red-400 text-sm">{recordsError}</p>
            </div>
          )}

          {/* Records table + detail panel */}
          <div className="flex gap-4 flex-1 min-h-0">
            <div
              className="flex-1 overflow-y-auto"
              style={{ maxHeight: "calc(100vh - 420px)" }}
            >
              {recordsLoading && records.length === 0 && (
                <p className="text-slate-500 text-sm p-4">Loading records...</p>
              )}
              {!recordsLoading && records.length === 0 && (
                <div className="bg-forensic-surface rounded-lg border border-forensic-border p-8 text-center">
                  <p className="text-slate-400">No call records found.</p>
                </div>
              )}
              {records.length > 0 && (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-slate-500 border-b border-forensic-border">
                      <th className="pb-2 pr-3">Date/Time</th>
                      <th className="pb-2 pr-3">Caller</th>
                      <th className="pb-2 pr-3">Called</th>
                      <th className="pb-2 pr-3">Duration</th>
                      <th className="pb-2 pr-3">Type</th>
                      <th className="pb-2 pr-3">Charges</th>
                      <th className="pb-2">Anomaly</th>
                    </tr>
                  </thead>
                  <tbody>
                    {records.map((rec: any) => (
                      <tr
                        key={rec.id}
                        onClick={() => handleSelectRecord(rec)}
                        className={`border-b border-forensic-border/50 cursor-pointer transition-colors hover:bg-forensic-accent/5 ${
                          selectedRecord?.id === rec.id
                            ? "bg-forensic-accent/10"
                            : ""
                        }`}
                      >
                        <td className="py-2 pr-3 text-slate-300 whitespace-nowrap">
                          {rec.call_datetime?.slice(0, 16) || "--"}
                        </td>
                        <td className="py-2 pr-3 text-white font-mono text-xs">
                          {formatPhone(rec.caller_number)}
                        </td>
                        <td className="py-2 pr-3 text-white font-mono text-xs">
                          {formatPhone(rec.called_number)}
                        </td>
                        <td className="py-2 pr-3 text-slate-300">
                          {formatDuration(rec.duration_seconds || rec.duration)}
                        </td>
                        <td className="py-2 pr-3">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                              rec.call_type === "ISD"
                                ? "bg-purple-900/30 text-purple-400"
                                : rec.call_type === "STD"
                                ? "bg-blue-900/30 text-blue-400"
                                : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {rec.call_type || "--"}
                          </span>
                        </td>
                        <td className="py-2 pr-3 text-slate-300">
                          {rec.charges != null
                            ? `$${Number(rec.charges).toFixed(2)}`
                            : "--"}
                        </td>
                        <td className="py-2">
                          {rec.is_anomaly && (
                            <span
                              className="px-1.5 py-0.5 rounded text-[10px] font-bold"
                              style={{
                                backgroundColor: `${anomalyColor(rec.anomaly_score || 0)}22`,
                                color: anomalyColor(rec.anomaly_score || 0),
                              }}
                            >
                              {((rec.anomaly_score || 0) * 100).toFixed(0)}%
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Detail panel */}
            {selectedRecord && (
              <div
                className="w-80 bg-forensic-surface rounded-lg border border-forensic-border p-4 overflow-y-auto shrink-0"
                style={{ maxHeight: "calc(100vh - 420px)" }}
              >
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-sm font-semibold text-white">
                    Call Details
                  </h3>
                  <button
                    onClick={() => setSelectedRecord(null)}
                    className="text-slate-500 hover:text-white text-xs"
                  >
                    Close
                  </button>
                </div>
                <div className="space-y-3">
                  <div>
                    <span className="text-xs text-slate-500">Date/Time</span>
                    <p className="text-sm text-white">
                      {selectedRecord.call_datetime || "--"}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-slate-500">Caller</span>
                    <p className="text-sm text-white font-mono">
                      {formatPhone(selectedRecord.caller_number)}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-slate-500">Called</span>
                    <p className="text-sm text-slate-300 font-mono">
                      {formatPhone(selectedRecord.called_number)}
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <span className="text-xs text-slate-500">Duration</span>
                      <p className="text-sm text-slate-300">
                        {formatDuration(
                          selectedRecord.duration_seconds ||
                            selectedRecord.duration
                        )}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-slate-500">Type</span>
                      <p className="text-sm text-slate-300">
                        {selectedRecord.call_type || "--"}
                      </p>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <span className="text-xs text-slate-500">Charges</span>
                      <p className="text-sm text-slate-300">
                        {selectedRecord.charges != null
                          ? `$${Number(selectedRecord.charges).toFixed(2)}`
                          : "--"}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-slate-500">IMEI</span>
                      <p className="text-sm text-slate-300 font-mono text-xs break-all">
                        {selectedRecord.imei || "--"}
                      </p>
                    </div>
                  </div>
                  {selectedRecord.cell_id && (
                    <div>
                      <span className="text-xs text-slate-500">Cell ID</span>
                      <p className="text-sm text-slate-300 font-mono">
                        {selectedRecord.cell_id}
                      </p>
                    </div>
                  )}
                  {selectedRecord.is_anomaly && (
                    <div className="pt-2 border-t border-forensic-border">
                      <span className="text-xs text-red-400 font-semibold">
                        Anomaly Detected
                      </span>
                      <p className="text-xs text-slate-400 mt-1">
                        Score:{" "}
                        <span
                          className="font-bold"
                          style={{
                            color: anomalyColor(
                              selectedRecord.anomaly_score || 0
                            ),
                          }}
                        >
                          {(
                            (selectedRecord.anomaly_score || 0) * 100
                          ).toFixed(0)}
                          %
                        </span>
                      </p>
                      {selectedRecord.anomaly_reasons &&
                        selectedRecord.anomaly_reasons.length > 0 && (
                          <div className="mt-2 flex flex-wrap gap-1">
                            {selectedRecord.anomaly_reasons.map(
                              (r: string, i: number) => (
                                <span
                                  key={i}
                                  className="px-2 py-0.5 rounded text-[10px] bg-red-900/30 text-red-400"
                                >
                                  {r}
                                </span>
                              )
                            )}
                          </div>
                        )}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4">
              <p className="text-sm text-slate-400">
                {recordsTotal.toLocaleString()} records -- Page {recordsPage} of{" "}
                {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setRecordsPage(Math.max(1, recordsPage - 1))}
                  disabled={recordsPage === 1}
                  className="px-3 py-1 rounded bg-forensic-surface border border-forensic-border text-sm disabled:opacity-50 hover:border-forensic-accent/50"
                >
                  Prev
                </button>
                <button
                  onClick={() => setRecordsPage(recordsPage + 1)}
                  disabled={recordsPage >= totalPages}
                  className="px-3 py-1 rounded bg-forensic-surface border border-forensic-border text-sm disabled:opacity-50 hover:border-forensic-accent/50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* ─── Contacts Tab ──────────────────────────────────── */}
      {tab === "contacts" && (
        <div className="flex gap-4 flex-1 min-h-0">
          <div
            className="flex-1 overflow-y-auto"
            style={{ maxHeight: "calc(100vh - 340px)" }}
          >
            {contactsLoading && (
              <p className="text-slate-500 text-sm p-4">Loading contacts...</p>
            )}
            {contactsError && (
              <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
                <p className="text-red-400 text-sm">{contactsError}</p>
              </div>
            )}
            {!contactsLoading && contacts.length === 0 && (
              <div className="bg-forensic-surface rounded-lg border border-forensic-border p-8 text-center">
                <p className="text-slate-400">No contacts found.</p>
              </div>
            )}
            {contacts.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 border-b border-forensic-border">
                    <th className="pb-2 pr-3">Phone Number</th>
                    <th className="pb-2 pr-3">Total Calls</th>
                    <th className="pb-2 pr-3">Total Duration</th>
                    <th className="pb-2 pr-3">Avg Duration</th>
                    <th className="pb-2 pr-3">First Call</th>
                    <th className="pb-2">Last Call</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.map((c: any, idx: number) => (
                    <tr
                      key={idx}
                      onClick={() =>
                        handleNumberClick(c.phone_number || c.number)
                      }
                      className="border-b border-forensic-border/50 cursor-pointer transition-colors hover:bg-forensic-accent/5"
                    >
                      <td className="py-2 pr-3 text-forensic-accent font-mono text-xs underline">
                        {formatPhone(c.phone_number || c.number)}
                      </td>
                      <td className="py-2 pr-3 text-white font-bold">
                        {c.total_calls ?? c.call_count ?? 0}
                      </td>
                      <td className="py-2 pr-3 text-slate-300">
                        {formatDuration(
                          c.total_duration_seconds || c.total_duration
                        )}
                      </td>
                      <td className="py-2 pr-3 text-slate-300">
                        {formatDuration(
                          c.avg_duration_seconds || c.avg_duration
                        )}
                      </td>
                      <td className="py-2 pr-3 text-slate-400 text-xs">
                        {(c.first_call || c.first_seen || "")?.slice(0, 10)}
                      </td>
                      <td className="py-2 text-slate-400 text-xs">
                        {(c.last_call || c.last_seen || "")?.slice(0, 10)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Number timeline panel */}
          {numberTimeline && (
            <div
              className="w-96 bg-forensic-surface rounded-lg border border-forensic-border p-4 overflow-y-auto shrink-0"
              style={{ maxHeight: "calc(100vh - 340px)" }}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-white">
                  Number Timeline
                </h3>
                <button
                  onClick={() => setNumberTimeline(null)}
                  className="text-slate-500 hover:text-white text-xs"
                >
                  Close
                </button>
              </div>
              {timelineLoading && (
                <p className="text-slate-500 text-sm">Loading...</p>
              )}
              {numberTimeline.number && (
                <p className="text-forensic-accent font-mono text-sm mb-3">
                  {formatPhone(numberTimeline.number)}
                </p>
              )}
              {numberTimeline.calls && (
                <div className="space-y-2">
                  {numberTimeline.calls.map((call: any, i: number) => (
                    <div
                      key={i}
                      className="bg-forensic-bg rounded p-2 text-xs"
                    >
                      <div className="flex justify-between text-slate-300">
                        <span>
                          {(call.date_time || call.date || "")?.slice(0, 16)}
                        </span>
                        <span>{formatDuration(call.duration_seconds || call.duration)}</span>
                      </div>
                      <div className="text-slate-500 mt-0.5">
                        {call.call_type} | {call.direction || ""}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {numberTimeline.summary && (
                <div className="mt-3 pt-3 border-t border-forensic-border text-xs text-slate-400">
                  <p>Total: {numberTimeline.summary.total_calls} calls</p>
                  <p>
                    Duration:{" "}
                    {formatDuration(numberTimeline.summary.total_duration)}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ─── Heatmap Tab ──────────────────────────────────── */}
      {tab === "heatmap" && (
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
          {heatmapLoading && (
            <p className="text-slate-500 text-sm">Loading heatmap...</p>
          )}
          {heatmapError && (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
              <p className="text-red-400 text-sm">{heatmapError}</p>
            </div>
          )}
          {heatmap && (
            <>
              <h3 className="text-sm font-semibold text-slate-300 mb-3">
                Call Activity by Hour and Day
              </h3>
              <div className="overflow-x-auto">
                {/* Day headers */}
                <div className="grid gap-1" style={{ gridTemplateColumns: "50px repeat(7, 1fr)" }}>
                  <div />
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                    (day) => (
                      <div
                        key={day}
                        className="text-center text-xs text-slate-500 pb-1"
                      >
                        {day}
                      </div>
                    )
                  )}

                  {/* Hour rows */}
                  {Array.from({ length: 24 }, (_, hour) => {
                    const grid = heatmap.grid || heatmap;
                    const row = grid[hour] || grid[String(hour)] || [];
                    const maxCount = heatmap.max_count || 1;

                    return (
                      <div key={hour} className="contents">
                        <div className="text-xs text-slate-500 text-right pr-2 py-1">
                          {String(hour).padStart(2, "0")}:00
                        </div>
                        {Array.from({ length: 7 }, (_, day) => {
                          const count =
                            Array.isArray(row) ? row[day] || 0 : 0;
                          const intensity = maxCount > 0 ? count / maxCount : 0;
                          const r = Math.round(239 * intensity);
                          const g = Math.round(68 * intensity);
                          const b = Math.round(68 * intensity);
                          const bgColor =
                            count === 0
                              ? "rgba(30, 30, 40, 0.5)"
                              : `rgba(${Math.max(r, 40)}, ${Math.max(g, 20)}, ${Math.max(b, 20)}, ${0.3 + intensity * 0.7})`;

                          return (
                            <div
                              key={day}
                              className="rounded text-center text-[10px] py-1 min-h-[28px] flex items-center justify-center"
                              style={{ backgroundColor: bgColor }}
                              title={`${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day]} ${String(hour).padStart(2, "0")}:00 - ${count} calls`}
                            >
                              {count > 0 && (
                                <span
                                  className="font-mono"
                                  style={{
                                    color:
                                      intensity > 0.5
                                        ? "#fff"
                                        : "#94a3b8",
                                  }}
                                >
                                  {count}
                                </span>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="flex items-center gap-2 mt-3 text-xs text-slate-500">
                <span>Less</span>
                {[0, 0.2, 0.4, 0.6, 0.8, 1].map((v) => (
                  <div
                    key={v}
                    className="w-4 h-4 rounded"
                    style={{
                      backgroundColor:
                        v === 0
                          ? "rgba(30, 30, 40, 0.5)"
                          : `rgba(${Math.round(239 * v)}, ${Math.round(68 * v)}, ${Math.round(68 * v)}, ${0.3 + v * 0.7})`,
                    }}
                  />
                ))}
                <span>More</span>
              </div>
            </>
          )}
        </div>
      )}

      {/* ─── Anomalies Tab ──────────────────────────────────── */}
      {tab === "anomalies" && (
        <div className="space-y-2">
          {anomaliesLoading && (
            <p className="text-slate-500 text-sm p-4">Loading anomalies...</p>
          )}
          {anomaliesError && (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
              <p className="text-red-400 text-sm">{anomaliesError}</p>
            </div>
          )}
          {!anomaliesLoading && anomalies.length === 0 && (
            <div className="bg-forensic-surface rounded-lg border border-forensic-border p-8 text-center">
              <p className="text-slate-400">No anomalies detected.</p>
            </div>
          )}
          <div
            className="space-y-2 overflow-y-auto"
            style={{ maxHeight: "calc(100vh - 340px)" }}
          >
            {anomalies.map((a: any, idx: number) => {
              const score = a.anomaly_score || a.score || 0;
              const color = anomalyColor(score);
              return (
                <div
                  key={idx}
                  className="bg-forensic-surface rounded-lg border border-forensic-border p-4"
                >
                  <div className="flex items-start gap-3">
                    <div
                      className="px-2 py-1 rounded text-xs font-bold shrink-0"
                      style={{
                        backgroundColor: `${color}22`,
                        color: color,
                      }}
                    >
                      {(score * 100).toFixed(0)}%
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-3 text-sm">
                        <span className="text-slate-400">
                          {(a.call_datetime || "")?.slice(0, 16)}
                        </span>
                        <span className="text-white font-mono text-xs">
                          {formatPhone(a.caller_number)}
                        </span>
                        <span className="text-slate-600">-&gt;</span>
                        <span className="text-white font-mono text-xs">
                          {formatPhone(a.called_number)}
                        </span>
                        <span className="text-slate-400">
                          {formatDuration(a.duration_seconds || a.duration)}
                        </span>
                      </div>
                      {(a.anomaly_reasons || a.reasons) && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {(a.anomaly_reasons || a.reasons || []).map(
                            (r: string, i: number) => {
                              const tagColor =
                                score > 0.4
                                  ? "bg-red-900/30 text-red-400"
                                  : score > 0.2
                                  ? "bg-orange-900/30 text-orange-400"
                                  : "bg-yellow-900/30 text-yellow-400";
                              return (
                                <span
                                  key={i}
                                  className={`px-2 py-0.5 rounded text-[10px] ${tagColor}`}
                                >
                                  {r}
                                </span>
                              );
                            }
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ─── Monthly Tab ──────────────────────────────────── */}
      {tab === "monthly" && (
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
          {monthlyLoading && (
            <p className="text-slate-500 text-sm">Loading monthly data...</p>
          )}
          {monthlyError && (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
              <p className="text-red-400 text-sm">{monthlyError}</p>
            </div>
          )}
          {!monthlyLoading && monthly.length === 0 && (
            <div className="text-center p-8">
              <p className="text-slate-400">No monthly data available.</p>
            </div>
          )}
          {monthly.length > 0 && (
            <div className="space-y-3">
              {(() => {
                const maxCalls = Math.max(
                  ...monthly.map((m: any) => m.call_count || m.calls || 0)
                );
                const maxDuration = Math.max(
                  ...monthly.map(
                    (m: any) =>
                      m.total_duration_seconds || m.total_duration || 0
                  )
                );
                return monthly.map((m: any, idx: number) => {
                  const month = m.month || m.period || "";
                  const calls = m.call_count || m.calls || 0;
                  const duration =
                    m.total_duration_seconds || m.total_duration || 0;
                  const uniqueContacts =
                    m.unique_contacts || m.contacts || 0;
                  const hasChange = patternChangeMonths.has(month);
                  const change = patternChanges.find(
                    (pc: any) => (pc.month || pc.period) === month
                  );

                  return (
                    <div
                      key={idx}
                      className={`rounded p-3 ${
                        hasChange
                          ? "border border-red-800/50 bg-red-900/10"
                          : "bg-forensic-bg"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-white">
                            {month}
                          </span>
                          {hasChange && (
                            <span
                              className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                change?.direction === "increase" ||
                                change?.type === "increase"
                                  ? "bg-red-900/30 text-red-400"
                                  : "bg-green-900/30 text-green-400"
                              }`}
                            >
                              Pattern Change
                            </span>
                          )}
                        </div>
                        <span className="text-xs text-slate-500">
                          {uniqueContacts} contacts
                        </span>
                      </div>
                      {/* Calls bar */}
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs text-slate-500 w-14">
                          Calls
                        </span>
                        <div className="flex-1 bg-forensic-surface rounded-full h-4 overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${maxCalls > 0 ? (calls / maxCalls) * 100 : 0}%`,
                              backgroundColor: hasChange
                                ? "#ef4444"
                                : "#22d3ee",
                            }}
                          />
                        </div>
                        <span className="text-xs text-slate-300 w-12 text-right">
                          {calls}
                        </span>
                      </div>
                      {/* Duration bar */}
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500 w-14">
                          Duration
                        </span>
                        <div className="flex-1 bg-forensic-surface rounded-full h-4 overflow-hidden">
                          <div
                            className="h-full rounded-full transition-all"
                            style={{
                              width: `${maxDuration > 0 ? (duration / maxDuration) * 100 : 0}%`,
                              backgroundColor: hasChange
                                ? "#f97316"
                                : "#a78bfa",
                            }}
                          />
                        </div>
                        <span className="text-xs text-slate-300 w-12 text-right">
                          {formatDuration(duration)}
                        </span>
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          )}
        </div>
      )}

      {/* ─── New Contacts Tab ──────────────────────────────── */}
      {tab === "newcontacts" && (
        <div
          className="space-y-4 overflow-y-auto"
          style={{ maxHeight: "calc(100vh - 340px)" }}
        >
          {newContactsLoading && (
            <p className="text-slate-500 text-sm p-4">
              Loading new contacts...
            </p>
          )}
          {newContactsError && (
            <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
              <p className="text-red-400 text-sm">{newContactsError}</p>
            </div>
          )}
          {!newContactsLoading && newContacts.length === 0 && (
            <div className="bg-forensic-surface rounded-lg border border-forensic-border p-8 text-center">
              <p className="text-slate-400">No new contact data available.</p>
            </div>
          )}
          {newContacts.map((nc: any, idx: number) => {
            const month = nc.month || nc.period || "";
            const contacts = nc.contacts || nc.numbers || [];
            const hasAnomaly = patternChangeMonths.has(month);

            return (
              <div
                key={idx}
                className={`bg-forensic-surface rounded-lg border p-4 ${
                  hasAnomaly
                    ? "border-red-800/50"
                    : "border-forensic-border"
                }`}
              >
                <div className="flex items-center gap-2 mb-3">
                  <h3 className="text-sm font-semibold text-white">{month}</h3>
                  <span className="text-xs text-slate-500">
                    {contacts.length} new contact
                    {contacts.length !== 1 ? "s" : ""}
                  </span>
                  {hasAnomaly && (
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-900/30 text-red-400">
                      Pattern Anomaly
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {contacts.map((num: any, i: number) => {
                    const phoneNum =
                      typeof num === "string" ? num : num.number || num.phone_number || "";
                    return (
                      <span
                        key={i}
                        className={`px-2 py-1 rounded text-xs font-mono ${
                          hasAnomaly
                            ? "bg-red-900/20 text-red-400 border border-red-800/30"
                            : "bg-forensic-bg text-slate-300"
                        }`}
                      >
                        {formatPhone(phoneNum)}
                      </span>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
