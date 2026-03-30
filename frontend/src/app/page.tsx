"use client";

import { useEffect, useState } from "react";
import { evidence, jobs as jobsApi } from "@/lib/api";

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [recentJobs, setRecentJobs] = useState<any[]>([]);

  useEffect(() => {
    evidence.getStats().then(setStats).catch(console.error);
    jobsApi.list({ page_size: "5" }).then((r) => setRecentJobs(r.items || [])).catch(console.error);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Investigation Dashboard</h1>

      {/* Stats cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <StatCard label="Total Files" value={stats?.total_files ?? "—"} />
        <StatCard
          label="Total Size"
          value={stats ? formatBytes(stats.total_size_bytes) : "—"}
        />
        <StatCard label="Sources" value={stats?.sources_count ?? "—"} />
        <StatCard label="Duplicates" value={stats?.duplicate_count ?? "—"} />
      </div>

      {/* Parse status breakdown */}
      {stats?.by_status && (
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6 mb-8">
          <h2 className="text-lg font-semibold mb-4">Parse Status</h2>
          <div className="flex gap-4 flex-wrap">
            {Object.entries(stats.by_status).map(([status, count]) => (
              <div key={status} className="px-3 py-1 rounded bg-forensic-bg text-sm">
                <span className="text-slate-400">{status}:</span>{" "}
                <span className="font-medium">{count as number}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent jobs */}
      <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
        <h2 className="text-lg font-semibold mb-4">Recent Jobs</h2>
        {recentJobs.length === 0 ? (
          <p className="text-slate-500 text-sm">No jobs yet. Ingest evidence to get started.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 text-left">
                <th className="pb-2">Type</th>
                <th className="pb-2">Status</th>
                <th className="pb-2">Progress</th>
                <th className="pb-2">Created</th>
              </tr>
            </thead>
            <tbody>
              {recentJobs.map((job) => (
                <tr key={job.id} className="border-t border-forensic-border">
                  <td className="py-2">{job.job_type}</td>
                  <td className="py-2">
                    <StatusBadge status={job.status} />
                  </td>
                  <td className="py-2">{Math.round(job.progress * 100)}%</td>
                  <td className="py-2 text-slate-500">{job.created_at?.slice(0, 19)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
      <p className="text-sm text-slate-400">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    pending: "bg-yellow-900/30 text-yellow-400",
    running: "bg-blue-900/30 text-blue-400",
    completed: "bg-green-900/30 text-green-400",
    failed: "bg-red-900/30 text-red-400",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs ${colors[status] || "bg-slate-800 text-slate-400"}`}>
      {status}
    </span>
  );
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}
