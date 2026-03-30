"use client";

import { useEffect, useState } from "react";
import { legal } from "@/lib/api";

export default function LegalPage() {
  const [templates, setTemplates] = useState<any[]>([]);
  const [documents, setDocuments] = useState<any>({ items: [] });

  useEffect(() => {
    legal.listTemplates().then(setTemplates).catch(console.error);
    legal.listDocuments().then(setDocuments).catch(console.error);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Legal Drafting</h1>

      <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-6">
        <p className="text-red-400 text-sm font-medium">
          All documents generated here are DRAFTS requiring review. They are not court filings.
        </p>
      </div>

      {/* Templates */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Available Templates</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {templates.map((t: any) => (
            <div key={t.name} className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
              <h3 className="font-medium text-forensic-accent">{t.name}</h3>
              <p className="text-sm text-slate-400 mt-1">{t.description}</p>
              <div className="flex gap-2 mt-2">
                <span className="text-xs px-2 py-0.5 rounded bg-forensic-bg">{t.doc_type}</span>
                {t.provider && (
                  <span className="text-xs px-2 py-0.5 rounded bg-forensic-bg">{t.provider}</span>
                )}
              </div>
            </div>
          ))}
          {templates.length === 0 && (
            <p className="text-slate-500 text-sm">No templates loaded yet.</p>
          )}
        </div>
      </div>

      {/* Documents */}
      <div>
        <h2 className="text-lg font-semibold mb-4">Generated Documents</h2>
        <div className="space-y-3">
          {documents.items?.map((d: any) => (
            <div key={d.id} className="bg-forensic-surface rounded-lg border border-forensic-border p-4 draft-watermark">
              <div className="flex items-center justify-between">
                <h3 className="font-medium">{d.title}</h3>
                <span className="text-xs px-2 py-0.5 rounded bg-yellow-900/30 text-yellow-400">
                  {d.status}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">{d.doc_type} — {d.provider || "general"}</p>
            </div>
          ))}
          {(!documents.items || documents.items.length === 0) && (
            <p className="text-slate-500 text-sm">No documents generated yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
