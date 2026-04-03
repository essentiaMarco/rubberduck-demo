"use client";

import { useEffect, useState } from "react";
import { legal } from "@/lib/api";

export default function LegalPage() {
  const [templates, setTemplates] = useState<any[]>([]);
  const [documents, setDocuments] = useState<any[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<any>(null);
  const [creating, setCreating] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null);

  const loadData = () => {
    legal.listTemplates().then((r) => setTemplates(Array.isArray(r) ? r : r?.items || [])).catch(console.error);
    legal.listDocuments().then((r) => setDocuments(Array.isArray(r) ? r : r?.items || [])).catch(console.error);
  };

  useEffect(() => {
    loadData();
  }, []);

  const createFromTemplate = async (templateName: string) => {
    setCreating(true);
    try {
      await legal.createDocument({
        template_name: templateName,
        title: `Draft — ${templateName}`,
        doc_type: "draft",
      });
      loadData();
      setSelectedTemplate(null);
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  const viewDocument = async (docId: string) => {
    try {
      const doc = await legal.getDocument(docId);
      setSelectedDoc(doc);
    } catch (err) {
      console.error(err);
    }
  };

  const renderDocument = async (docId: string) => {
    try {
      const doc = await legal.renderDocument(docId);
      setSelectedDoc(doc);
      loadData();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Legal Drafting</h1>

      <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-6">
        <p className="text-red-400 text-sm font-medium">
          All documents generated here are DRAFTS requiring review. They are not court filings.
        </p>
      </div>

      {/* Document viewer modal */}
      {selectedDoc && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-forensic-surface rounded-lg border border-forensic-border w-full max-w-3xl max-h-[80vh] flex flex-col mx-4">
            <div className="flex items-center justify-between px-6 py-4 border-b border-forensic-border">
              <div>
                <h3 className="font-semibold text-white">{selectedDoc.title}</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  {selectedDoc.doc_type} — {selectedDoc.status}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => renderDocument(selectedDoc.id)}
                  className="text-xs bg-forensic-accent/20 text-forensic-accent px-3 py-1.5 rounded hover:bg-forensic-accent/30"
                >
                  Re-render
                </button>
                <button
                  onClick={() => setSelectedDoc(null)}
                  className="text-slate-400 hover:text-white text-sm px-2"
                >
                  Close
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-6">
              {selectedDoc.rendered_content ? (
                <div
                  className="prose prose-invert prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: selectedDoc.rendered_content }}
                />
              ) : selectedDoc.content ? (
                <pre className="text-sm text-slate-300 whitespace-pre-wrap">{selectedDoc.content}</pre>
              ) : (
                <p className="text-slate-500">No content yet. Click &ldquo;Re-render&rdquo; to generate content.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Templates */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Available Templates</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {templates.map((t: any) => (
            <div key={t.name} className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-medium text-forensic-accent">{t.name}</h3>
                  <p className="text-sm text-slate-400 mt-1">{t.description}</p>
                  <div className="flex gap-2 mt-2">
                    <span className="text-xs px-2 py-0.5 rounded bg-forensic-bg">{t.doc_type}</span>
                    {t.provider && (
                      <span className="text-xs px-2 py-0.5 rounded bg-forensic-bg">{t.provider}</span>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => createFromTemplate(t.name)}
                  disabled={creating}
                  className="text-xs bg-forensic-accent text-forensic-bg px-3 py-1.5 rounded font-medium hover:bg-forensic-accent/90 disabled:opacity-50 shrink-0 ml-3"
                >
                  Generate
                </button>
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
          {documents.map((d: any) => (
            <div
              key={d.id}
              className="bg-forensic-surface rounded-lg border border-forensic-border p-4 hover:border-forensic-accent/50 transition-colors cursor-pointer"
              onClick={() => viewDocument(d.id)}
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium text-white">{d.title}</h3>
                  <p className="text-xs text-slate-500 mt-1">
                    {d.doc_type} — {d.provider || "general"}
                    {d.created_at && ` — ${new Date(d.created_at).toLocaleString()}`}
                  </p>
                </div>
                <span
                  className={`text-xs px-2 py-0.5 rounded ${
                    d.status === "final"
                      ? "bg-green-900/30 text-green-400"
                      : "bg-yellow-900/30 text-yellow-400"
                  }`}
                >
                  {d.status}
                </span>
              </div>
            </div>
          ))}
          {documents.length === 0 && (
            <p className="text-slate-500 text-sm">No documents generated yet. Use a template above to create one.</p>
          )}
        </div>
      </div>
    </div>
  );
}
