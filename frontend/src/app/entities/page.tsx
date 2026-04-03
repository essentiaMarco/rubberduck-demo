"use client";

import { useEffect, useState } from "react";
import { entities } from "@/lib/api";
import Link from "next/link";
import DateRangeFilter from "@/components/filters/DateRangeFilter";

const ENTITY_TYPES = ["", "person", "org", "email", "phone", "ip", "url", "device", "location", "app", "account"];
const SORT_OPTIONS = [
  { value: "mentions", label: "Most Mentions" },
  { value: "aliases", label: "Most Aliases" },
  { value: "name", label: "Name A-Z" },
  { value: "updated", label: "Recently Updated" },
];

export default function EntitiesPage() {
  const [data, setData] = useState<any>({ items: [], total: 0 });
  const [typeFilter, setTypeFilter] = useState("");
  const [sortBy, setSortBy] = useState("mentions");
  const [page, setPage] = useState(1);
  const [dateStart, setDateStart] = useState<string | null>(null);
  const [dateEnd, setDateEnd] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;
    const params: Record<string, string> = {
      page: String(page),
      page_size: "25",
      sort_by: sortBy,
    };
    if (typeFilter) params.entity_type = typeFilter;
    if (dateStart) params.date_start = dateStart;
    if (dateEnd) params.date_end = dateEnd;
    entities.list(params).then((result) => {
      if (!ignore) setData(result);
    }).catch((err) => {
      if (!ignore) console.error(err);
    });
    return () => { ignore = true; };
  }, [typeFilter, sortBy, page, dateStart, dateEnd]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Entities</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400">Sort:</span>
          <select
            value={sortBy}
            onChange={(e) => { setSortBy(e.target.value); setPage(1); }}
            className="bg-forensic-surface border border-forensic-border rounded px-2 py-1 text-sm text-slate-300"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="mb-4">
        <DateRangeFilter
          dateStart={dateStart}
          dateEnd={dateEnd}
          onChange={(s, e) => { setDateStart(s); setDateEnd(e); setPage(1); }}
        />
      </div>

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
              <th className="p-3 cursor-pointer hover:text-white" onClick={() => { setSortBy("mentions"); setPage(1); }}>
                Mentions {sortBy === "mentions" ? "\u25BC" : ""}
              </th>
              <th className="p-3 cursor-pointer hover:text-white" onClick={() => { setSortBy("aliases"); setPage(1); }}>
                Aliases {sortBy === "aliases" ? "\u25BC" : ""}
              </th>
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
                <td className="p-3 text-slate-400">{e.mention_count?.toLocaleString()}</td>
                <td className="p-3 text-slate-400">{e.alias_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-4">
        <p className="text-sm text-slate-400">{data.total?.toLocaleString()} entities</p>
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
