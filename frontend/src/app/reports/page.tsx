"use client";

import { useEffect, useState } from "react";
import { evidence, entities, timeline, graph } from "@/lib/api";

interface CaseSummary {
  totalFiles: number;
  totalSize: string;
  parsedFiles: number;
  failedFiles: number;
  totalEntities: number;
  topEntityTypes: { type: string; count: number }[];
  totalEvents: number;
  dateRange: { start: string | null; end: string | null };
  graphNodes: number;
  graphEdges: number;
}

export default function ReportsPage() {
  const [summary, setSummary] = useState<CaseSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [generated, setGenerated] = useState(false);

  const generateReport = async () => {
    setLoading(true);
    try {
      // Gather data from all modules
      const [evidStats, entList, tlStats, graphData] = await Promise.all([
        evidence.getStats().catch(() => null),
        entities.list({ page_size: "1" }).catch(() => null),
        timeline.getStats().catch(() => null),
        graph.getFull({ limit: "1" }).catch(() => null),
      ]);

      const s: CaseSummary = {
        totalFiles: evidStats?.total_files || 0,
        totalSize: evidStats?.total_size_bytes
          ? `${(evidStats.total_size_bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
          : "Unknown",
        parsedFiles: evidStats?.by_status?.completed || 0,
        failedFiles: evidStats?.by_status?.failed || 0,
        totalEntities: entList?.total || 0,
        topEntityTypes: Object.entries(evidStats?.by_extension || {})
          .map(([type, count]) => ({ type, count: count as number }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 8),
        totalEvents: tlStats?.total_events || 0,
        dateRange: {
          start: tlStats?.date_range_start || null,
          end: tlStats?.date_range_end || null,
        },
        graphNodes: graphData?.node_count || 0,
        graphEdges: graphData?.edge_count || 0,
      };

      setSummary(s);
      setGenerated(true);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Reports</h1>
        <button
          onClick={generateReport}
          disabled={loading}
          className="bg-forensic-accent text-forensic-bg px-4 py-2 rounded text-sm font-medium hover:bg-forensic-accent/90 disabled:opacity-50"
        >
          {loading ? "Generating..." : "Generate Case Summary"}
        </button>
      </div>

      {!generated && !loading && (
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-12 text-center">
          <p className="text-xl text-slate-400 mb-2">Case Summary Report</p>
          <p className="text-sm text-slate-500">
            Generate a comprehensive summary of all evidence, entities, timeline events,
            and relationship graph data in this investigation.
          </p>
        </div>
      )}

      {summary && (
        <div className="space-y-6">
          {/* Evidence Overview */}
          <section className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
            <h2 className="text-lg font-semibold mb-4 text-forensic-accent">Evidence Overview</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-2xl font-bold text-white">{summary.totalFiles.toLocaleString()}</p>
                <p className="text-xs text-slate-500">Total Files</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-white">{summary.totalSize}</p>
                <p className="text-xs text-slate-500">Total Size</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-green-400">{summary.parsedFiles.toLocaleString()}</p>
                <p className="text-xs text-slate-500">Successfully Parsed</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-red-400">{summary.failedFiles.toLocaleString()}</p>
                <p className="text-xs text-slate-500">Failed</p>
              </div>
            </div>
            {summary.topEntityTypes.length > 0 && (
              <div className="mt-4 pt-4 border-t border-forensic-border">
                <p className="text-xs text-slate-500 mb-2">File Types</p>
                <div className="flex flex-wrap gap-2">
                  {summary.topEntityTypes.map((t) => (
                    <span key={t.type} className="text-xs bg-forensic-bg px-2 py-1 rounded text-slate-300">
                      {t.type}: {t.count}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* Entities */}
          <section className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
            <h2 className="text-lg font-semibold mb-4 text-forensic-accent">Entity Analysis</h2>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div>
                <p className="text-2xl font-bold text-white">{summary.totalEntities.toLocaleString()}</p>
                <p className="text-xs text-slate-500">Total Entities Extracted</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-white">{summary.graphNodes.toLocaleString()}</p>
                <p className="text-xs text-slate-500">Graph Nodes</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-white">{summary.graphEdges.toLocaleString()}</p>
                <p className="text-xs text-slate-500">Relationships</p>
              </div>
            </div>
          </section>

          {/* Timeline */}
          <section className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
            <h2 className="text-lg font-semibold mb-4 text-forensic-accent">Timeline</h2>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <p className="text-2xl font-bold text-white">{summary.totalEvents.toLocaleString()}</p>
                <p className="text-xs text-slate-500">Total Events</p>
              </div>
              <div>
                <p className="text-sm font-medium text-white">
                  {summary.dateRange.start
                    ? new Date(summary.dateRange.start).toLocaleDateString()
                    : "N/A"}
                </p>
                <p className="text-xs text-slate-500">Earliest Event</p>
              </div>
              <div>
                <p className="text-sm font-medium text-white">
                  {summary.dateRange.end
                    ? new Date(summary.dateRange.end).toLocaleDateString()
                    : "N/A"}
                </p>
                <p className="text-xs text-slate-500">Latest Event</p>
              </div>
            </div>
          </section>

          {/* Print hint */}
          <p className="text-xs text-slate-600 text-center">
            Use your browser&apos;s Print function (Ctrl+P / Cmd+P) to save this report as a PDF.
          </p>
        </div>
      )}
    </div>
  );
}
