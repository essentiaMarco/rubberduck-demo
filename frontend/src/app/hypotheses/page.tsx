"use client";

import { useEffect, useState } from "react";
import { hypotheses } from "@/lib/api";
import Link from "next/link";

export default function HypothesesPage() {
  const [data, setData] = useState<any>({ items: [] });

  useEffect(() => {
    hypotheses.list().then(setData).catch(console.error);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Hypothesis Testing</h1>

      <div className="space-y-4">
        {data.items?.map((h: any) => (
          <div key={h.id} className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
            <div className="flex items-center justify-between mb-2">
              <Link href={`/hypotheses/${h.id}`} className="text-lg font-semibold text-forensic-accent hover:underline">
                {h.title}
              </Link>
              <div className="flex items-center gap-3">
                <span className={`px-2 py-0.5 rounded text-xs ${
                  h.status === "supported" ? "bg-green-900/30 text-green-400" :
                  h.status === "refuted" ? "bg-red-900/30 text-red-400" :
                  "bg-blue-900/30 text-blue-400"
                }`}>
                  {h.status}
                </span>
                {h.confidence != null && (
                  <span className="text-sm text-slate-400">
                    {Math.round(h.confidence * 100)}% confidence
                  </span>
                )}
              </div>
            </div>
            {h.description && <p className="text-sm text-slate-400">{h.description}</p>}
            <div className="flex gap-4 mt-3 text-xs text-slate-500">
              <span>{h.finding_count} findings</span>
              <span>{h.gap_count} gaps</span>
            </div>
          </div>
        ))}

        {(!data.items || data.items.length === 0) && (
          <p className="text-slate-500 text-sm">No hypotheses yet. Create one to start testing.</p>
        )}
      </div>
    </div>
  );
}
