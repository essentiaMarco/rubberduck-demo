"use client";

import { useEffect, useState } from "react";
import { entities } from "@/lib/api";
import Link from "next/link";

const ENTITY_TYPES = ["", "person", "org", "email", "phone", "ip", "url", "device", "location", "app", "account"];

export default function EntitiesPage() {
  const [data, setData] = useState<any>({ items: [], total: 0 });
  const [typeFilter, setTypeFilter] = useState("");
  const [page, setPage] = useState(1);

  useEffect(() => {
    const params: Record<string, string> = { page: String(page), page_size: "25" };
    if (typeFilter) params.entity_type = typeFilter;
    entities.list(params).then(setData).catch(console.error);
  }, [typeFilter, page]);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Entities</h1>

      <div className="flex gap-1 mb-4 flex-wrap">
        {ENTITY_TYPES.map((t) => (
          <button
            key={t}
            onClick={() => { setTypeFilter(t); setPage(1); }}
            className={`px-3 py-1 rounded text-xs ${
              typeFilter === t
                ? "bg-forensic-accent text-forensic-bg"
                : "bg-forensic-surface text-slate-400"
            }`}
          >
            {t || "All"}
          </button>
        ))}
      </div>

      <div className="bg-forensic-surface rounded-lg border border-forensic-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 text-left bg-forensic-bg">
              <th className="p-3">Name</th>
              <th className="p-3">Type</th>
              <th className="p-3">Mentions</th>
              <th className="p-3">Aliases</th>
            </tr>
          </thead>
          <tbody>
            {data.items?.map((e: any) => (
              <tr key={e.id} className="border-t border-forensic-border hover:bg-forensic-bg/50">
                <td className="p-3">
                  <Link href={`/entities/${e.id}`} className="text-forensic-accent hover:underline">
                    {e.canonical_name}
                  </Link>
                </td>
                <td className="p-3">
                  <span className="px-2 py-0.5 rounded text-xs bg-forensic-bg">{e.entity_type}</span>
                </td>
                <td className="p-3 text-slate-400">{e.mention_count}</td>
                <td className="p-3 text-slate-400">{e.alias_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-4">
        <p className="text-sm text-slate-400">{data.total} entities</p>
        <div className="flex gap-2">
          <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}
            className="px-3 py-1 rounded bg-forensic-surface text-sm disabled:opacity-50">Prev</button>
          <span className="px-3 py-1 text-sm text-slate-400">Page {page}</span>
          <button onClick={() => setPage(page + 1)} disabled={data.items?.length < 25}
            className="px-3 py-1 rounded bg-forensic-surface text-sm disabled:opacity-50">Next</button>
        </div>
      </div>
    </div>
  );
}
