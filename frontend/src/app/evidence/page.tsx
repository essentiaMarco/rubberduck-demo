"use client";

import { useEffect, useState } from "react";
import { evidence } from "@/lib/api";
import Link from "next/link";
import DateRangeFilter from "@/components/filters/DateRangeFilter";

export default function EvidencePage() {
  const [files, setFiles] = useState<any>({ items: [], total: 0 });
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("");
  const [dateStart, setDateStart] = useState<string | null>(null);
  const [dateEnd, setDateEnd] = useState<string | null>(null);

  useEffect(() => {
    const params: Record<string, string> = { page: String(page), page_size: "25" };
    if (filter) params.parse_status = filter;
    if (dateStart) params.date_start = dateStart;
    if (dateEnd) params.date_end = dateEnd;
    evidence.listFiles(params).then(setFiles).catch(console.error);
  }, [page, filter, dateStart, dateEnd]);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Evidence Files</h1>
        <div className="flex gap-2">
          {["", "completed", "pending", "failed", "unsupported"].map((s) => (
            <button
              key={s}
              onClick={() => { setFilter(s); setPage(1); }}
              className={`px-3 py-1 rounded text-sm ${
                filter === s
                  ? "bg-forensic-accent text-forensic-bg"
                  : "bg-forensic-surface text-slate-400 hover:text-white"
              }`}
            >
              {s || "All"}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-4">
        <DateRangeFilter
          dateStart={dateStart}
          dateEnd={dateEnd}
          onChange={(s, e) => { setDateStart(s); setDateEnd(e); setPage(1); }}
        />
      </div>

      <div className="bg-forensic-surface rounded-lg border border-forensic-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-left bg-forensic-bg">
              <th className="p-3">Name</th>
              <th className="p-3">Type</th>
              <th className="p-3">Size</th>
              <th className="p-3">Status</th>
              <th className="p-3">SHA-256</th>
            </tr>
          </thead>
          <tbody>
            {files.items?.map((f: any) => (
              <tr key={f.id} className="border-t border-forensic-border hover:bg-forensic-bg/50">
                <td className="p-3">
                  <Link href={`/evidence/${f.id}`} className="text-forensic-accent hover:underline">
                    {f.file_name}
                  </Link>
                </td>
                <td className="p-3 text-slate-400">{f.file_ext}</td>
                <td className="p-3 text-slate-400">
                  {f.file_size_bytes ? `${(f.file_size_bytes / 1024).toFixed(1)} KB` : "—"}
                </td>
                <td className="p-3">
                  <span className={`px-2 py-0.5 rounded text-xs ${
                    f.parse_status === "completed" ? "bg-green-900/30 text-green-400" :
                    f.parse_status === "failed" ? "bg-red-900/30 text-red-400" :
                    "bg-yellow-900/30 text-yellow-400"
                  }`}>
                    {f.parse_status}
                  </span>
                </td>
                <td className="p-3 text-slate-600 font-mono text-xs">
                  {f.sha256?.slice(0, 16)}...
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between mt-4">
        <p className="text-sm text-slate-400">{files.total} files total</p>
        <div className="flex gap-2">
          <button
            onClick={() => setPage(Math.max(1, page - 1))}
            disabled={page === 1}
            className="px-3 py-1 rounded bg-forensic-surface text-sm disabled:opacity-50"
          >
            Prev
          </button>
          <span className="px-3 py-1 text-sm text-slate-400">Page {page}</span>
          <button
            onClick={() => setPage(page + 1)}
            disabled={files.items?.length < 25}
            className="px-3 py-1 rounded bg-forensic-surface text-sm disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
