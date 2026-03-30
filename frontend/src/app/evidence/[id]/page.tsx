"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { evidence } from "@/lib/api";

export default function FileDetailPage() {
  const params = useParams();
  const fileId = params.id as string;
  const [file, setFile] = useState<any>(null);
  const [content, setContent] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"metadata" | "content" | "custody">("metadata");

  useEffect(() => {
    evidence.getFile(fileId).then(setFile).catch(console.error);
    evidence.getContent(fileId).then((r) => setContent(r.content || "")).catch(() => {});
  }, [fileId]);

  if (!file) return <div className="text-slate-400">Loading...</div>;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-2">{file.file_name}</h1>
      <p className="text-sm text-slate-400 mb-6">
        {file.mime_type} — {file.file_size_bytes ? `${(file.file_size_bytes / 1024).toFixed(1)} KB` : "Unknown size"}
        — SHA-256: <code className="font-mono text-xs">{file.sha256}</code>
      </p>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-forensic-border">
        {(["metadata", "content", "custody"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm capitalize ${
              activeTab === tab
                ? "text-forensic-accent border-b-2 border-forensic-accent"
                : "text-slate-400 hover:text-white"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
        {activeTab === "metadata" && (
          <div className="space-y-2 text-sm">
            {Object.entries(file)
              .filter(([k]) => !["custody_chain"].includes(k))
              .map(([key, val]) => (
                <div key={key} className="flex">
                  <span className="w-48 text-slate-400 shrink-0">{key}:</span>
                  <span className="font-mono text-xs break-all">{String(val ?? "—")}</span>
                </div>
              ))}
          </div>
        )}

        {activeTab === "content" && (
          <pre className="whitespace-pre-wrap text-sm text-slate-300 max-h-[600px] overflow-auto">
            {content || "No parsed content available."}
          </pre>
        )}

        {activeTab === "custody" && (
          <div className="space-y-3">
            {file.custody_chain?.map((entry: any, i: number) => (
              <div key={entry.id} className="flex items-start gap-3">
                <div className="w-2 h-2 rounded-full bg-forensic-accent mt-2 shrink-0" />
                <div>
                  <p className="text-sm font-medium">{entry.action}</p>
                  <p className="text-xs text-slate-400">
                    {entry.timestamp} — {entry.actor}
                  </p>
                  {entry.details && (
                    <pre className="text-xs text-slate-500 mt-1">{entry.details}</pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
