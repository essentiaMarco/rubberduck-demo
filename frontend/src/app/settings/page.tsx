"use client";

import { useEffect, useState } from "react";
import { cases } from "@/lib/api";

export default function SettingsPage() {
  const [caseList, setCaseList] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);

  useEffect(() => {
    cases.list().then(setCaseList).catch(console.error);
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => {});
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <div className="space-y-6">
        {/* System health */}
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
          <h2 className="text-lg font-semibold mb-4">System Status</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`w-2 h-2 rounded-full ${
                    health?.status === "ok" ? "bg-green-400" : "bg-red-400"
                  }`}
                />
                <span className="text-sm text-slate-300">Backend</span>
              </div>
              <p className="text-xs text-slate-500">
                {health?.status === "ok" ? "Connected" : "Unavailable"}
              </p>
            </div>
            <div>
              <span className="text-sm text-slate-300">Database</span>
              <p className="text-xs text-slate-500">SQLite + DuckDB</p>
            </div>
            <div>
              <span className="text-sm text-slate-300">Search Index</span>
              <p className="text-xs text-slate-500">FTS5 (porter + unicode61)</p>
            </div>
            <div>
              <span className="text-sm text-slate-300">NLP Engine</span>
              <p className="text-xs text-slate-500">spaCy en_core_web_sm</p>
            </div>
          </div>
        </div>

        {/* Cases */}
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
          <h2 className="text-lg font-semibold mb-4">Cases</h2>
          {caseList.length === 0 ? (
            <p className="text-slate-500 text-sm">No cases configured.</p>
          ) : (
            <div className="space-y-3">
              {caseList.map((c: any) => (
                <div key={c.id} className="bg-forensic-bg rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-medium text-white">{c.name}</h3>
                      {c.case_number && (
                        <p className="text-xs text-slate-500 mt-0.5">Case #{c.case_number}</p>
                      )}
                      {c.description && (
                        <p className="text-sm text-slate-400 mt-1">{c.description}</p>
                      )}
                    </div>
                    <span className="text-xs text-slate-600">
                      {c.created_at ? new Date(c.created_at).toLocaleDateString() : ""}
                    </span>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-xs text-slate-500">
                    {c.court && <span>Court: {c.court}</span>}
                    {c.petitioner_name && <span>Petitioner: {c.petitioner_name}</span>}
                    {c.decedent_name && <span>Decedent: {c.decedent_name}</span>}
                    {c.judge_name && <span>Judge: {c.judge_name}</span>}
                    {c.department && <span>Dept: {c.department}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Case Configuration */}
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
          <h2 className="text-lg font-semibold mb-4">Platform Configuration</h2>
          <div className="space-y-3 text-sm">
            <div>
              <label className="text-slate-400 block mb-1">Default Court</label>
              <input
                type="text"
                defaultValue="San Francisco Superior Court, Probate Division"
                className="w-full bg-forensic-bg border border-forensic-border rounded px-3 py-2 text-sm"
                readOnly
              />
            </div>
            <div>
              <label className="text-slate-400 block mb-1">Default Timezone</label>
              <input
                type="text"
                defaultValue="America/Los_Angeles"
                className="w-full bg-forensic-bg border border-forensic-border rounded px-3 py-2 text-sm"
                readOnly
              />
            </div>
          </div>
        </div>

        {/* System Information */}
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
          <h2 className="text-lg font-semibold mb-4">System Information</h2>
          <div className="space-y-2 text-sm">
            <p><span className="text-slate-400">Version:</span> 0.1.0</p>
            <p><span className="text-slate-400">Mode:</span> Local-first (no external APIs)</p>
            <p><span className="text-slate-400">OCR:</span> Tesseract (if installed)</p>
            <p><span className="text-slate-400">NLP:</span> spaCy en_core_web_sm</p>
            <p><span className="text-slate-400">Search:</span> SQLite FTS5</p>
            <p><span className="text-slate-400">Timeline:</span> DuckDB + Parquet</p>
          </div>
        </div>
      </div>
    </div>
  );
}
