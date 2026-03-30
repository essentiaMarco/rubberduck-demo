"use client";

export default function SettingsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      <div className="space-y-6">
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
          <h2 className="text-lg font-semibold mb-4">Case Configuration</h2>
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

        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
          <h2 className="text-lg font-semibold mb-4">System Information</h2>
          <div className="space-y-2 text-sm">
            <p><span className="text-slate-400">Version:</span> 0.1.0</p>
            <p><span className="text-slate-400">Mode:</span> Local-first (no external APIs)</p>
            <p><span className="text-slate-400">OCR:</span> Tesseract (if installed)</p>
            <p><span className="text-slate-400">NLP:</span> spaCy en_core_web_sm</p>
          </div>
        </div>
      </div>
    </div>
  );
}
