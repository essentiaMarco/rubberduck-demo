"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { evidence } from "@/lib/api";

interface ContentMatch {
  snippet: string;
  byte_offset: number;
  match_index: number;
}

function ExpandableMatch({
  match,
  fileId,
  formatBytes,
}: {
  match: ContentMatch;
  fileId: string;
  formatBytes: (b: number) => string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [expandedContent, setExpandedContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadMore = async () => {
    if (expandedContent) {
      setExpanded(!expanded);
      return;
    }
    setLoading(true);
    try {
      // Load 5KB around the match offset
      const contextSize = 5000;
      const start = Math.max(0, match.byte_offset - contextSize);
      const r = await evidence.getContent(fileId, {
        offset: String(start),
        max_bytes: String(contextSize * 2),
      });
      setExpandedContent(r.content || "");
      setExpanded(true);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-forensic-bg rounded-lg border border-forensic-border">
      <div className="flex items-center justify-between px-4 pt-3 pb-2">
        <span className="text-xs font-medium text-forensic-accent">
          Match {match.match_index + 1}
        </span>
        <div className="flex items-center gap-3">
          <button
            onClick={loadMore}
            disabled={loading}
            className="text-xs text-slate-400 hover:text-forensic-accent underline"
          >
            {loading ? "Loading..." : expanded ? "Show match" : "Expand context"}
          </button>
          <span className="text-xs text-slate-500">
            offset: {formatBytes(match.byte_offset)}
          </span>
        </div>
      </div>
      <div className="px-4 pb-4 max-h-[400px] overflow-y-auto">
        {expanded && expandedContent ? (
          <pre className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-mono break-words">
            {expandedContent}
          </pre>
        ) : (
          <div
            className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap font-mono break-words [&_mark]:bg-yellow-500/30 [&_mark]:text-yellow-200 [&_mark]:px-0.5 [&_mark]:rounded"
            dangerouslySetInnerHTML={{ __html: match.snippet }}
          />
        )}
      </div>
    </div>
  );
}

export default function FileDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const fileId = params.id as string;
  const searchQuery = searchParams.get("q") || "";

  const [file, setFile] = useState<any>(null);
  const [content, setContent] = useState<string>("");
  const [contentMeta, setContentMeta] = useState<{
    total_size: number;
    truncated: boolean;
    offset: number;
  } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Search-within-file state
  const [searchMatches, setSearchMatches] = useState<ContentMatch[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchTotal, setSearchTotal] = useState(0);

  const [activeTab, setActiveTab] = useState<"metadata" | "content" | "custody">(
    searchQuery ? "content" : "metadata"
  );

  // Load file metadata
  useEffect(() => {
    evidence.getFile(fileId).then(setFile).catch(console.error);
  }, [fileId]);

  // Load content: either search matches or sequential
  useEffect(() => {
    if (searchQuery) {
      // Search within file for relevant sections
      setSearchLoading(true);
      evidence
        .searchContent(fileId, searchQuery)
        .then((r) => {
          setSearchMatches(r.matches || []);
          setSearchTotal(r.total_matches || 0);
          setContentMeta({
            total_size: r.total_size || 0,
            truncated: false,
            offset: 0,
          });
        })
        .catch(() => {})
        .finally(() => setSearchLoading(false));
    } else {
      // Sequential read (default for non-search navigation)
      evidence
        .getContent(fileId)
        .then((r) => {
          setContent(r.content || "");
          setContentMeta({
            total_size: r.total_size || 0,
            truncated: r.truncated || false,
            offset: (r.offset || 0) + (r.content?.length || 0),
          });
        })
        .catch(() => {});
    }
  }, [fileId, searchQuery]);

  const loadMore = async () => {
    if (!contentMeta?.truncated || loadingMore) return;
    setLoadingMore(true);
    try {
      const r = await evidence.getContent(fileId, {
        offset: String(contentMeta.offset),
        max_bytes: "500000",
      });
      setContent((prev) => prev + (r.content || ""));
      setContentMeta({
        total_size: r.total_size || 0,
        truncated: r.truncated || false,
        offset: (r.offset || contentMeta.offset) + (r.content?.length || 0),
      });
    } catch {
      // ignore
    } finally {
      setLoadingMore(false);
    }
  };

  const switchToFullContent = () => {
    // Clear search results and load sequential content
    setSearchMatches([]);
    setSearchTotal(0);
    evidence
      .getContent(fileId)
      .then((r) => {
        setContent(r.content || "");
        setContentMeta({
          total_size: r.total_size || 0,
          truncated: r.truncated || false,
          offset: (r.offset || 0) + (r.content?.length || 0),
        });
      })
      .catch(() => {});
  };

  if (!file) return <div className="text-slate-400">Loading...</div>;

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const isSearchMode = searchQuery && (searchMatches.length > 0 || searchLoading);

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
          <div>
            {/* Search mode: show matching sections */}
            {isSearchMode ? (
              <div>
                <div className="flex items-center justify-between mb-4 pb-3 border-b border-forensic-border">
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-white font-medium">
                      {searchLoading ? (
                        "Searching..."
                      ) : (
                        <>
                          {searchTotal} match{searchTotal !== 1 ? "es" : ""} for{" "}
                          <span className="text-forensic-accent">&ldquo;{searchQuery}&rdquo;</span>
                        </>
                      )}
                    </span>
                    {contentMeta && (
                      <span className="text-xs text-slate-500">
                        in {formatBytes(contentMeta.total_size)} file
                      </span>
                    )}
                  </div>
                  <button
                    onClick={switchToFullContent}
                    className="text-xs text-slate-400 hover:text-white underline"
                  >
                    View full content
                  </button>
                </div>

                {searchLoading ? (
                  <div className="text-center py-8 text-slate-400">
                    Searching within file...
                  </div>
                ) : searchMatches.length === 0 ? (
                  <div className="text-center py-8 text-slate-400">
                    No matches found for &ldquo;{searchQuery}&rdquo; in this file.
                  </div>
                ) : (
                  <div className="space-y-4 max-h-[600px] overflow-y-auto pr-2">
                    {searchMatches.map((match, i) => (
                      <ExpandableMatch key={i} match={match} fileId={fileId} formatBytes={formatBytes} />
                    ))}
                  </div>
                )}
              </div>
            ) : (
              /* Sequential read mode */
              <div>
                {contentMeta && contentMeta.total_size > 0 && (
                  <div className="flex items-center justify-between mb-3 pb-3 border-b border-forensic-border">
                    <span className="text-xs text-slate-500">
                      Total content size: {formatBytes(contentMeta.total_size)}
                      {contentMeta.truncated && (
                        <span className="text-yellow-500 ml-2">
                          (showing first {formatBytes(contentMeta.offset)})
                        </span>
                      )}
                    </span>
                  </div>
                )}

                <pre className="whitespace-pre-wrap text-sm text-slate-300 max-h-[600px] overflow-auto">
                  {content || "No parsed content available."}
                </pre>

                {contentMeta?.truncated && (
                  <div className="mt-4 pt-3 border-t border-forensic-border flex items-center gap-3">
                    <button
                      onClick={loadMore}
                      disabled={loadingMore}
                      className="bg-forensic-accent text-forensic-bg px-4 py-2 rounded text-sm font-medium hover:bg-forensic-accent/90 disabled:opacity-50"
                    >
                      {loadingMore ? "Loading..." : "Load More Content"}
                    </button>
                    <span className="text-xs text-slate-500">
                      {formatBytes(contentMeta.total_size - contentMeta.offset)} remaining
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
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
