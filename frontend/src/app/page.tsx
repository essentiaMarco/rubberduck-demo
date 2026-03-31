"use client";

import { useEffect, useState } from "react";
import { evidence, jobs as jobsApi, analysis } from "@/lib/api";

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [recentJobs, setRecentJobs] = useState<any[]>([]);
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [analysisJobId, setAnalysisJobId] = useState<string | null>(null);
  const [analysisProgress, setAnalysisProgress] = useState<any>(null);

  const refreshData = () => {
    evidence.getStats().then(setStats).catch(console.error);
    jobsApi.list({ page_size: "10" }).then((r) => setRecentJobs(r.items || [])).catch(console.error);
  };

  useEffect(() => {
    refreshData();
  }, []);

  // Poll analysis job progress
  useEffect(() => {
    if (!analysisJobId) return;
    const interval = setInterval(() => {
      jobsApi.get(analysisJobId).then((job) => {
        setAnalysisProgress(job);
        if (job.status === "completed" || job.status === "failed") {
          setAnalysisRunning(false);
          setAnalysisJobId(null);
          refreshData();
        }
      }).catch(console.error);
    }, 3000);
    return () => clearInterval(interval);
  }, [analysisJobId]);

  const handleRunAnalysis = async () => {
    setAnalysisRunning(true);
    try {
      const result = await analysis.runFull();
      setAnalysisJobId(result.job_id);
      refreshData();
    } catch (err) {
      console.error(err);
      setAnalysisRunning(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Investigation Dashboard</h1>
        <button
          onClick={handleRunAnalysis}
          disabled={analysisRunning}
          className={`px-4 py-2 rounded font-medium text-sm ${
            analysisRunning
              ? "bg-forensic-border text-slate-500 cursor-not-allowed"
              : "bg-forensic-accent text-forensic-bg hover:bg-forensic-accent/90"
          }`}
        >
          {analysisRunning ? "Analysis Running..." : "Run Full Analysis"}
        </button>
      </div>

      {/* Analysis progress */}
      {analysisProgress && analysisRunning && (
        <div className="bg-blue-900/20 border border-blue-800 rounded-lg p-4 mb-6">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-blue-400">
              Analysis Pipeline: {analysisProgress.status}
            </span>
            <span className="text-sm text-blue-400">
              {Math.round((analysisProgress.progress || 0) * 100)}%
            </span>
          </div>
          <div className="w-full bg-blue-900/30 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${(analysisProgress.progress || 0) * 100}%` }}
            />
          </div>
          <p className="text-xs text-slate-500 mt-2">
            Step {analysisProgress.processed_items || 0} of {analysisProgress.total_items || 3}:
            {(analysisProgress.progress || 0) < 0.33 ? " Building search index..." :
             (analysisProgress.progress || 0) < 0.67 ? " Extracting entities (NER + regex)..." :
             " Rebuilding timeline..."}
          </p>
        </div>
      )}

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
