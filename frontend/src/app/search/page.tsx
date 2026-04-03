"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { search } from "@/lib/api";
import Link from "next/link";
import DateRangeFilter from "@/components/filters/DateRangeFilter";

const FILE_TYPES = [
  { value: "", label: "All Types" },
  { value: ".eml", label: "Email (.eml)" },
  { value: ".mbox", label: "Mailbox (.mbox)" },
  { value: ".pdf", label: "PDF (.pdf)" },
  { value: ".docx", label: "Word (.docx)" },
  { value: ".txt", label: "Text (.txt)" },
  { value: ".html", label: "HTML (.html)" },
];

interface SearchResult {
  file_id: string;
  file_name: string;
  file_ext: string | null;
  source_label: string | null;
  score: number;
  snippet: string;
  mime_type: string | null;
}

interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
  page: number;
  page_size: number;
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileType, setFileType] = useState("");
  const [page, setPage] = useState(1);
  const [suggestions, setSuggestions] = useState<Array<{ term: string; count: number }>>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const suggestTimeout = useRef<NodeJS.Timeout | null>(null);
  const [dateStart, setDateStart] = useState<string | null>(null);
  const [dateEnd, setDateEnd] = useState<string | null>(null);

  const doSearch = useCallback(
    async (searchQuery: string, searchPage: number = 1) => {
      if (!searchQuery.trim()) {
        setResults(null);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const body: any = {
          query: searchQuery.trim(),
          page: searchPage,
          page_size: 20,
        };
        if (fileType) {
          body.file_types = [fileType];
        }
        if (dateStart) body.date_start = dateStart;
        if (dateEnd) body.date_end = dateEnd;
        const data = await search.query(body);
        setResults(data);
      } catch (err: any) {
        setError(err.message || "Search failed");
        setResults(null);
      } finally {
        setLoading(false);
      }
    },
    [fileType, dateStart, dateEnd]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setShowSuggestions(false);
    doSearch(query, 1);
  };

  // Re-search when page or fileType changes (if we have a query)
  useEffect(() => {
    if (query.trim()) {
      doSearch(query, page);
    }
  }, [page, fileType]);

  // Autocomplete suggestions
  const handleInputChange = (value: string) => {
    setQuery(value);

    if (suggestTimeout.current) clearTimeout(suggestTimeout.current);

    if (value.trim().length >= 2) {
      suggestTimeout.current = setTimeout(async () => {
        try {
          const suggs = await search.suggest(value.trim());
          setSuggestions(Array.isArray(suggs) ? suggs : []);
          setShowSuggestions(true);
        } catch {
          setSuggestions([]);
        }
      }, 300);
    } else {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  };

  const selectSuggestion = (term: string) => {
    setQuery(term);
    setShowSuggestions(false);
    setPage(1);
    doSearch(term, 1);
  };

  const totalPages = results ? Math.ceil(results.total / results.page_size) : 0;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Search Evidence</h1>

      {/* Search bar */}
      <form onSubmit={handleSubmit} className="mb-6">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => handleInputChange(e.target.value)}
              onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
              placeholder="Search all evidence files by keyword..."
              className="w-full bg-forensic-surface border border-forensic-border rounded-lg px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:border-forensic-accent"
            />

            {/* Autocomplete dropdown */}
            {showSuggestions && suggestions.length > 0 && (
              <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-forensic-surface border border-forensic-border rounded-lg shadow-lg overflow-hidden">
                {suggestions.map((s) => (
                  <button
                    key={s.term}
                    type="button"
                    onMouseDown={() => selectSuggestion(s.term)}
                    className="w-full text-left px-4 py-2 text-sm hover:bg-forensic-bg/50 flex justify-between items-center"
                  >
                    <span className="text-slate-200">{s.term}</span>
                    <span className="text-xs text-slate-500">{s.count} files</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          <select
            value={fileType}
            onChange={(e) => {
              setFileType(e.target.value);
              setPage(1);
            }}
            className="bg-forensic-surface border border-forensic-border rounded-lg px-3 py-3 text-sm text-slate-300"
          >
            {FILE_TYPES.map((ft) => (
              <option key={ft.value} value={ft.value}>
                {ft.label}
              </option>
            ))}
          </select>

          <button
            type="submit"
            disabled={loading || !query.trim()}
            className="bg-forensic-accent text-forensic-bg px-6 py-3 rounded-lg font-medium hover:bg-forensic-accent/90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </div>
      </form>

      {/* Date filter */}
      <div className="mb-4">
        <DateRangeFilter
          dateStart={dateStart}
          dateEnd={dateEnd}
          onChange={(s, e) => { setDateStart(s); setDateEnd(e); }}
        />
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-6">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Results */}
      {results && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm text-slate-400">
              {results.total.toLocaleString()} result{results.total !== 1 ? "s" : ""} for &ldquo;{results.query}&rdquo;
            </p>
          </div>

          {results.results.length === 0 ? (
            <div className="bg-forensic-surface rounded-lg border border-forensic-border p-8 text-center">
              <p className="text-slate-400">No results found. Try different keywords or remove filters.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {results.results.map((r, i) => (
                <div
                  key={`${r.file_id}-${i}`}
                  className="bg-forensic-surface rounded-lg border border-forensic-border p-4 hover:border-forensic-accent/50 transition-colors"
                >
                  <div className="flex items-start justify-between mb-2">
                    <Link
                      href={`/evidence/${r.file_id}?q=${encodeURIComponent(query.trim())}`}
                      className="text-forensic-accent hover:underline font-medium"
                    >
                      {r.file_name}
                    </Link>
                    <div className="flex items-center gap-2 shrink-0 ml-4">
                      {r.file_ext && (
                        <span className="text-xs px-2 py-0.5 rounded bg-forensic-bg text-slate-400">
                          {r.file_ext}
                        </span>
                      )}
                      <span className="text-xs text-slate-500">
                        score: {r.score.toFixed(2)}
                      </span>
                    </div>
                  </div>

                  {r.source_label && (
                    <p className="text-xs text-slate-500 mb-2">Source: {r.source_label}</p>
                  )}

                  {/* Snippet with highlighting */}
                  <p
                    className="text-sm text-slate-300 leading-relaxed"
                    dangerouslySetInnerHTML={{ __html: r.snippet }}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-6">
              <p className="text-sm text-slate-400">
                Page {results.page} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage(Math.max(1, page - 1))}
                  disabled={page === 1}
                  className="px-3 py-1 rounded bg-forensic-surface text-sm disabled:opacity-50"
                >
                  Prev
                </button>
                <button
                  onClick={() => setPage(page + 1)}
                  disabled={page >= totalPages}
                  className="px-3 py-1 rounded bg-forensic-surface text-sm disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!results && !loading && !error && (
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-12 text-center">
          <p className="text-xl text-slate-400 mb-2">Search across all evidence</p>
          <p className="text-sm text-slate-500">
            Full-text search with BM25 ranking. Supports keywords, phrases, and boolean operators.
          </p>
        </div>
      )}
    </div>
  );
}
