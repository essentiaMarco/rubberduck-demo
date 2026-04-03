"use client";

import { useEffect, useState, useCallback } from "react";
import { communications } from "@/lib/api";
import DateRangeFilter from "@/components/filters/DateRangeFilter";

const CLASSIFICATIONS = [
  { value: "", label: "All", color: "#94a3b8" },
  { value: "personal", label: "Personal", color: "#22c55e" },
  { value: "notification", label: "Notification", color: "#eab308" },
  { value: "newsletter", label: "Newsletter", color: "#f97316" },
  { value: "spam", label: "Spam", color: "#ef4444" },
];

const COMM_TYPES = [
  { value: "", label: "All Types" },
  { value: "email", label: "Email" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "sms", label: "SMS" },
  { value: "call", label: "Call" },
  { value: "social_media", label: "Social Media" },
  { value: "calendar", label: "Calendar" },
];

interface Message {
  id: string;
  file_id: string;
  email_from: string | null;
  email_to: string | null;
  email_subject: string | null;
  email_date: string | null;
  is_spam: boolean;
  spam_score: number;
  classification: string;
  comm_type: string;
  has_attachments: boolean;
  attachment_count: number;
  body_length: number;
  body_preview: string;
}

export default function CommunicationsPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [classification, setClassification] = useState("");
  const [commType, setCommType] = useState("");
  const [senderFilter, setSenderFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [hideSpam, setHideSpam] = useState(true);
  const [dateStart, setDateStart] = useState<string | null>(null);
  const [dateEnd, setDateEnd] = useState<string | null>(null);

  // Selected message
  const [selected, setSelected] = useState<any>(null);

  const pageSize = 50;

  const fetchMessages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {
        page: String(page),
        page_size: String(pageSize),
      };
      if (classification) params.classification = classification;
      if (commType) params.comm_type = commType;
      if (senderFilter) params.sender = senderFilter;
      if (searchFilter) params.search = searchFilter;
      if (hideSpam && !classification) params.is_spam = "false";
      if (dateStart) params.date_start = dateStart;
      if (dateEnd) params.date_end = dateEnd;

      const data = await communications.listMessages(params);
      setMessages(data.items || []);
      setTotal(data.total || 0);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [page, classification, commType, senderFilter, searchFilter, hideSpam, dateStart, dateEnd]);

  const fetchStats = useCallback(async () => {
    try {
      const s = await communications.getStats();
      setStats(s);
    } catch {
      // stats are optional
    }
  }, []);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  useEffect(() => {
    fetchStats();
  }, []);

  const handleExtract = async (reprocess: boolean = false) => {
    setExtracting(true);
    setError(null);
    try {
      const result = await communications.extractEmails(reprocess);
      setError(null);
      // Refresh
      await fetchMessages();
      await fetchStats();
      alert(
        `Extraction complete!\n` +
        `Files processed: ${result.files_processed}\n` +
        `Total emails: ${result.total_emails}\n` +
        `Spam filtered: ${result.total_spam}\n` +
        `Personal: ${result.total_personal}`
      );
    } catch (err: any) {
      setError(err.message);
    } finally {
      setExtracting(false);
    }
  };

  const handleSelectMessage = async (msg: Message) => {
    try {
      const full = await communications.getMessage(msg.id);
      setSelected(full);
    } catch {
      setSelected(msg);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  const classColor = (cls: string) => {
    const found = CLASSIFICATIONS.find((c) => c.value === cls);
    return found?.color || "#94a3b8";
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Communications</h1>
        <div className="flex gap-2">
          {stats && stats.total_messages === 0 && (
            <button
              onClick={() => handleExtract(false)}
              disabled={extracting}
              className="bg-forensic-accent text-forensic-bg px-4 py-2 rounded text-sm font-medium hover:bg-forensic-accent/90 disabled:opacity-50"
            >
              {extracting ? "Extracting..." : "Extract Emails from Files"}
            </button>
          )}
          {stats && stats.total_messages > 0 && (
            <button
              onClick={() => handleExtract(true)}
              disabled={extracting}
              className="bg-forensic-surface border border-forensic-border text-slate-300 px-3 py-2 rounded text-sm hover:border-forensic-accent disabled:opacity-50"
            >
              {extracting ? "Re-extracting..." : "Re-extract All"}
            </button>
          )}
        </div>
      </div>

      {/* Stats bar */}
      {stats && stats.total_messages > 0 && (
        <div className="grid grid-cols-5 gap-3 mb-4">
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Total Messages</p>
            <p className="text-lg font-bold">{stats.total_messages.toLocaleString()}</p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Non-Spam</p>
            <p className="text-lg font-bold text-green-400">
              {stats.non_spam_count.toLocaleString()}
            </p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Spam/Newsletters</p>
            <p className="text-lg font-bold text-red-400">
              {stats.spam_count.toLocaleString()}
            </p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Date Range</p>
            <p className="text-xs text-slate-300">
              {stats.date_range?.start?.slice(0, 10)} to{" "}
              {stats.date_range?.end?.slice(0, 10)}
            </p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-3">
            <p className="text-xs text-slate-500">Comm Types</p>
            <p className="text-xs text-slate-300">
              {Object.entries(stats.by_comm_type || {})
                .map(([k, v]: [string, any]) => `${k}: ${v}`)
                .join(", ")}
            </p>
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4 mb-4 space-y-3">
        <div className="flex items-center gap-3 flex-wrap">
          {/* Classification chips */}
          {CLASSIFICATIONS.map((c) => (
            <button
              key={c.value}
              onClick={() => {
                setClassification(c.value);
                setPage(1);
                if (c.value === "spam") setHideSpam(false);
                else if (!c.value) setHideSpam(true);
              }}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                classification === c.value
                  ? "ring-2 ring-offset-1 ring-offset-forensic-bg"
                  : "opacity-60 hover:opacity-100"
              }`}
              style={{
                backgroundColor: `${c.color}22`,
                color: c.color,
                borderColor: classification === c.value ? c.color : "transparent",
                ringColor: c.color,
              }}
            >
              {c.label}
              {stats?.by_classification?.[c.value] !== undefined && (
                <span className="ml-1 opacity-70">
                  ({stats.by_classification[c.value]})
                </span>
              )}
            </button>
          ))}

          <span className="text-slate-600">|</span>

          {/* Comm type dropdown */}
          <select
            value={commType}
            onChange={(e) => { setCommType(e.target.value); setPage(1); }}
            className="bg-forensic-bg border border-forensic-border rounded px-2 py-1.5 text-xs text-slate-300"
          >
            {COMM_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>

          {/* Hide spam toggle */}
          {!classification && (
            <label className="flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                checked={hideSpam}
                onChange={(e) => { setHideSpam(e.target.checked); setPage(1); }}
                className="accent-forensic-accent"
              />
              Hide spam
            </label>
          )}
        </div>

        {/* Search and sender filter */}
        <div className="flex gap-3">
          <input
            type="text"
            placeholder="Search subject or body..."
            value={searchFilter}
            onChange={(e) => setSearchFilter(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { setPage(1); fetchMessages(); } }}
            className="flex-1 bg-forensic-bg border border-forensic-border rounded px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-forensic-accent"
          />
          <input
            type="text"
            placeholder="Filter by sender..."
            value={senderFilter}
            onChange={(e) => setSenderFilter(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { setPage(1); fetchMessages(); } }}
            className="w-64 bg-forensic-bg border border-forensic-border rounded px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:border-forensic-accent"
          />
          <button
            onClick={() => { setPage(1); fetchMessages(); }}
            className="bg-forensic-accent text-forensic-bg px-4 py-2 rounded text-sm font-medium hover:bg-forensic-accent/90"
          >
            Filter
          </button>
        </div>

        {/* Date filter */}
        <DateRangeFilter
          dateStart={dateStart}
          dateEnd={dateEnd}
          onChange={(s, e) => { setDateStart(s); setDateEnd(e); setPage(1); }}
        />
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Message list + detail panel */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Message list */}
        <div className="flex-1 space-y-1 overflow-y-auto" style={{ maxHeight: "calc(100vh - 400px)" }}>
          {loading && messages.length === 0 && (
            <p className="text-slate-500 text-sm p-4">Loading messages...</p>
          )}

          {!loading && messages.length === 0 && stats?.total_messages === 0 && (
            <div className="bg-forensic-surface rounded-lg border border-forensic-border p-8 text-center">
              <p className="text-xl text-slate-400 mb-2">No email messages extracted yet</p>
              <p className="text-sm text-slate-500 mb-4">
                Click &quot;Extract Emails from Files&quot; to process your email evidence files.
                This will classify each email as personal, newsletter, notification, or spam.
              </p>
            </div>
          )}

          {!loading && messages.length === 0 && stats?.total_messages > 0 && (
            <div className="bg-forensic-surface rounded-lg border border-forensic-border p-8 text-center">
              <p className="text-slate-400">No messages match your filters.</p>
            </div>
          )}

          {messages.map((msg) => (
            <div
              key={msg.id}
              onClick={() => handleSelectMessage(msg)}
              className={`bg-forensic-surface rounded border p-3 cursor-pointer transition-colors hover:border-forensic-accent/50 ${
                selected?.id === msg.id
                  ? "border-forensic-accent"
                  : "border-forensic-border"
              }`}
            >
              <div className="flex items-start gap-3">
                {/* Spam score indicator */}
                <div
                  className="w-1.5 h-full min-h-[40px] rounded-full shrink-0 mt-1"
                  style={{ backgroundColor: classColor(msg.classification) }}
                />

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-white truncate">
                      {msg.email_from?.split("<")[0]?.trim() || msg.email_from || "Unknown"}
                    </span>
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0"
                      style={{
                        backgroundColor: `${classColor(msg.classification)}22`,
                        color: classColor(msg.classification),
                      }}
                    >
                      {msg.classification}
                    </span>
                    {msg.comm_type !== "email" && (
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-purple-900/30 text-purple-400 shrink-0">
                        {msg.comm_type}
                      </span>
                    )}
                    {msg.has_attachments && (
                      <span className="text-xs text-slate-500 shrink-0">
                        📎 {msg.attachment_count}
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-slate-300 truncate">
                    {msg.email_subject || "(no subject)"}
                  </p>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-xs text-slate-500">
                      {msg.email_date?.slice(0, 16)}
                    </span>
                    <span className="text-xs text-slate-600 truncate">
                      {msg.body_preview?.slice(0, 80)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Detail panel */}
        {selected && (
          <div
            className="w-96 bg-forensic-surface rounded-lg border border-forensic-border p-4 overflow-y-auto shrink-0"
            style={{ maxHeight: "calc(100vh - 400px)" }}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white">Message Details</h3>
              <button
                onClick={() => setSelected(null)}
                className="text-slate-500 hover:text-white text-xs"
              >
                Close
              </button>
            </div>

            <div className="space-y-3">
              <div>
                <span className="text-xs text-slate-500">From</span>
                <p className="text-sm text-white break-all">{selected.email_from}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500">To</span>
                <p className="text-sm text-slate-300 break-all">{selected.email_to}</p>
              </div>
              {selected.email_cc && (
                <div>
                  <span className="text-xs text-slate-500">Cc</span>
                  <p className="text-sm text-slate-300 break-all">{selected.email_cc}</p>
                </div>
              )}
              <div>
                <span className="text-xs text-slate-500">Subject</span>
                <p className="text-sm text-white">{selected.email_subject || "(no subject)"}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500">Date</span>
                <p className="text-sm text-slate-300">{selected.email_date}</p>
              </div>

              {/* Classification */}
              <div className="flex items-center gap-2">
                <span
                  className="px-2 py-1 rounded text-xs font-medium"
                  style={{
                    backgroundColor: `${classColor(selected.classification)}22`,
                    color: classColor(selected.classification),
                  }}
                >
                  {selected.classification}
                </span>
                <span className="text-xs text-slate-500">
                  Spam score: {(selected.spam_score * 100).toFixed(0)}%
                </span>
              </div>

              {/* Spam reasons */}
              {selected.spam_reasons && selected.spam_reasons.length > 0 && (
                <div>
                  <span className="text-xs text-slate-500">Spam Indicators</span>
                  <ul className="text-xs text-slate-400 mt-1 space-y-0.5">
                    {selected.spam_reasons.map((r: string, i: number) => (
                      <li key={i} className="flex items-start gap-1">
                        <span className="text-red-400 mt-0.5">*</span>
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Body preview */}
              {selected.body_preview && (
                <div>
                  <span className="text-xs text-slate-500">Body Preview</span>
                  <div className="mt-1 p-3 bg-forensic-bg rounded text-xs text-slate-300 leading-relaxed whitespace-pre-wrap max-h-64 overflow-y-auto">
                    {selected.body_preview}
                  </div>
                </div>
              )}

              {/* Metadata */}
              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-forensic-border">
                <div>
                  <span className="text-xs text-slate-500">Type</span>
                  <p className="text-xs text-slate-300">{selected.comm_type}</p>
                </div>
                <div>
                  <span className="text-xs text-slate-500">Body Length</span>
                  <p className="text-xs text-slate-300">
                    {selected.body_length?.toLocaleString()} chars
                  </p>
                </div>
                {selected.has_attachments && (
                  <div>
                    <span className="text-xs text-slate-500">Attachments</span>
                    <p className="text-xs text-slate-300">{selected.attachment_count}</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4">
          <p className="text-sm text-slate-400">
            {total.toLocaleString()} messages — Page {page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page === 1}
              className="px-3 py-1 rounded bg-forensic-surface text-sm disabled:opacity-50"
            >
              Prev
            </button>
            <button
              onClick={() => setPage(page + 1)}
              disabled={page >= totalPages}
              className="px-3 py-1 rounded bg-forensic-surface text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Top senders section */}
      {stats?.top_senders?.length > 0 && !selected && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-slate-400 mb-3">Top Senders (Non-Spam)</h2>
          <div className="grid grid-cols-2 gap-2">
            {stats.top_senders.slice(0, 10).map((s: any, i: number) => (
              <button
                key={i}
                onClick={() => {
                  setSenderFilter(s.sender?.split("<")[0]?.trim() || s.sender || "");
                  setPage(1);
                }}
                className="bg-forensic-surface rounded border border-forensic-border p-2 text-left hover:border-forensic-accent/50 transition-colors"
              >
                <p className="text-xs text-white truncate">
                  {s.sender?.split("<")[0]?.trim() || s.sender}
                </p>
                <p className="text-xs text-slate-500">{s.count} messages</p>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
