"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { entities } from "@/lib/api";
import Link from "next/link";

export default function EntityDetailPage() {
  const params = useParams();
  const entityId = params.id as string;
  const [entity, setEntity] = useState<any>(null);
  const [relationships, setRelationships] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<"overview" | "mentions" | "relationships">("overview");

  useEffect(() => {
    entities.get(entityId).then(setEntity).catch(console.error);
    entities.getRelationships(entityId).then(setRelationships).catch(() => setRelationships([]));
  }, [entityId]);

  if (!entity) return <div className="text-slate-400">Loading...</div>;

  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <Link href="/entities" className="text-slate-400 hover:text-white text-sm">&larr; Entities</Link>
      </div>
      <h1 className="text-2xl font-bold mb-1">{entity.canonical_name}</h1>
      <div className="flex gap-3 text-sm text-slate-400 mb-6">
        <span className="px-2 py-0.5 rounded bg-forensic-bg">{entity.entity_type}</span>
        <span>{entity.mention_count} mentions</span>
        <span>{entity.alias_count} aliases</span>
        <span>{entity.relationship_count} relationships</span>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-forensic-border">
        {(["overview", "mentions", "relationships"] as const).map((tab) => (
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

      <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6">
        {activeTab === "overview" && (
          <div className="space-y-6">
            {/* Aliases */}
            {entity.aliases?.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-slate-400 mb-2">Aliases</h3>
                <div className="flex flex-wrap gap-2">
                  {entity.aliases.map((a: any) => (
                    <span key={a.id} className="px-2 py-1 rounded bg-forensic-bg text-sm">
                      {a.alias}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Properties */}
            {entity.properties && (
              <div>
                <h3 className="text-sm font-semibold text-slate-400 mb-2">Properties</h3>
                <pre className="text-sm text-slate-300 bg-forensic-bg rounded p-3 overflow-auto">
                  {typeof entity.properties === "string"
                    ? entity.properties
                    : JSON.stringify(entity.properties, null, 2)}
                </pre>
              </div>
            )}

            {/* Metadata */}
            <div>
              <h3 className="text-sm font-semibold text-slate-400 mb-2">Metadata</h3>
              <div className="space-y-1 text-sm">
                <div className="flex"><span className="w-32 text-slate-400">ID:</span><code className="font-mono text-xs">{entity.id}</code></div>
                <div className="flex"><span className="w-32 text-slate-400">Created:</span><span>{entity.created_at?.slice(0, 19)}</span></div>
                <div className="flex"><span className="w-32 text-slate-400">Updated:</span><span>{entity.updated_at?.slice(0, 19)}</span></div>
              </div>
            </div>
          </div>
        )}

        {activeTab === "mentions" && (
          <div className="space-y-2">
            {entity.recent_mentions?.length > 0 ? (
              entity.recent_mentions.map((m: any) => (
                <div key={m.id} className="border border-forensic-border rounded p-3">
                  <div className="flex items-center justify-between mb-1">
                    <Link href={`/evidence/${m.file_id}`} className="text-forensic-accent hover:underline text-sm">
                      {m.file_name || m.file_id}
                    </Link>
                    <span className="text-xs text-slate-500">{m.extractor}</span>
                  </div>
                  <p className="text-sm font-medium">{m.mention_text}</p>
                  {m.context_snippet && (
                    <p className="text-xs text-slate-500 mt-1 line-clamp-2">{m.context_snippet}</p>
                  )}
                </div>
              ))
            ) : (
              <p className="text-slate-500 text-sm">No mentions recorded.</p>
            )}
          </div>
        )}

        {activeTab === "relationships" && (
          <div className="space-y-2">
            {relationships.length > 0 ? (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-slate-400 text-left">
                    <th className="pb-2">From</th>
                    <th className="pb-2">Relationship</th>
                    <th className="pb-2">To</th>
                    <th className="pb-2">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {relationships.map((r: any) => (
                    <tr key={r.id} className="border-t border-forensic-border">
                      <td className="py-2">
                        <Link href={`/entities/${r.source_entity_id}`} className="text-forensic-accent hover:underline">
                          {r.source_entity_name || r.source_entity_id?.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="py-2">
                        <span className="px-2 py-0.5 rounded bg-forensic-bg text-xs">{r.rel_type}</span>
                      </td>
                      <td className="py-2">
                        <Link href={`/entities/${r.target_entity_id}`} className="text-forensic-accent hover:underline">
                          {r.target_entity_name || r.target_entity_id?.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="py-2 text-slate-400">{r.confidence ? `${(r.confidence * 100).toFixed(0)}%` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-slate-500 text-sm">No relationships found.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
