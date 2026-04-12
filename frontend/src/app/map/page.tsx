"use client";

import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";

const geo = {
  locations: (params: Record<string, string> = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<any[]>(`/api/geo/locations?${qs}`);
  },
  stats: () => apiFetch<any>("/api/geo/stats"),
  extract: () => apiFetch<any>("/api/geo/extract", { method: "POST" }),
  radius: (lat: number, lon: number, km: number) =>
    apiFetch<any[]>(`/api/geo/locations/radius?lat=${lat}&lon=${lon}&radius_km=${km}`),
  heatmap: () => apiFetch<any[]>("/api/geo/heatmap"),
};

function sourceIcon(source: string): string {
  switch (source) {
    case "photo_exif": return "📷";
    case "google_location_history": return "📍";
    case "cell_tower": return "📡";
    case "ip_geolocation": return "🌐";
    default: return "📌";
  }
}

export default function MapPage() {
  const [stats, setStats] = useState<any>(null);
  const [locations, setLocations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [sourceFilter, setSourceFilter] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [selectedLoc, setSelectedLoc] = useState<any>(null);

  const fetchStats = useCallback(async () => {
    try {
      const data = await geo.stats();
      setStats(data);
    } catch {}
  }, []);

  const fetchLocations = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = { limit: "5000" };
      if (sourceFilter) params.source_type = sourceFilter;
      if (dateStart) params.date_start = dateStart;
      if (dateEnd) params.date_end = dateEnd;
      const data = await geo.locations(params);
      setLocations(data || []);
    } catch {}
    setLoading(false);
  }, [sourceFilter, dateStart, dateEnd]);

  useEffect(() => { fetchStats(); fetchLocations(); }, [fetchStats, fetchLocations]);

  const handleExtract = async () => {
    setExtracting(true);
    try {
      await geo.extract();
      fetchStats();
      fetchLocations();
    } finally {
      setExtracting(false);
    }
  };

  // Group locations by source type for summary
  const bySource: Record<string, number> = {};
  locations.forEach(loc => {
    bySource[loc.source_type || "unknown"] = (bySource[loc.source_type || "unknown"] || 0) + 1;
  });

  return (
    <div style={{ padding: "24px", maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h1 style={{ fontSize: 24, fontWeight: 700 }}>Geospatial Intelligence</h1>
        <button
          onClick={handleExtract}
          disabled={extracting}
          style={{
            background: extracting ? "#334155" : "#6366f1",
            color: "#fff", border: "none", borderRadius: 6,
            padding: "8px 16px", cursor: extracting ? "default" : "pointer", fontWeight: 600,
          }}
        >
          {extracting ? "Extracting..." : "Extract Locations"}
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
          <div style={{ background: "#1e293b", borderRadius: 8, padding: "12px 20px", minWidth: 130, textAlign: "center", border: "1px solid #334155" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: "#e2e8f0" }}>{stats.total_locations || 0}</div>
            <div style={{ fontSize: 11, color: "#94a3b8", textTransform: "uppercase" }}>Total Points</div>
          </div>
          {Object.entries(stats.by_source || {}).map(([src, count]) => (
            <div key={src} style={{ background: "#1e293b", borderRadius: 8, padding: "12px 20px", minWidth: 120, textAlign: "center", border: "1px solid #334155" }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: "#67e8f9" }}>{count as number}</div>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>{sourceIcon(src)} {src}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: 12, marginBottom: 16, alignItems: "center" }}>
        <select
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px" }}
        >
          <option value="">All Sources</option>
          <option value="photo_exif">Photo EXIF</option>
          <option value="google_location_history">Google Location History</option>
          <option value="cell_tower">Cell Tower</option>
          <option value="ip_geolocation">IP Geolocation</option>
        </select>
        <input
          type="date" value={dateStart} onChange={(e) => setDateStart(e.target.value)}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px" }}
        />
        <span style={{ color: "#64748b" }}>to</span>
        <input
          type="date" value={dateEnd} onChange={(e) => setDateEnd(e.target.value)}
          style={{ background: "#1e293b", color: "#e2e8f0", border: "1px solid #334155", borderRadius: 6, padding: "6px 12px" }}
        />
      </div>

      {loading && <div style={{ color: "#94a3b8" }}>Loading locations...</div>}

      {!loading && locations.length === 0 && (
        <div style={{ textAlign: "center", color: "#64748b", padding: 60 }}>
          <p style={{ fontSize: 18, marginBottom: 12 }}>No location data extracted yet.</p>
          <p>Click "Extract Locations" to scan evidence for GPS coordinates from photos, Google Location History, and other sources.</p>
        </div>
      )}

      {!loading && locations.length > 0 && (
        <>
          {/* Location table with coordinates */}
          <div style={{ marginBottom: 16, color: "#94a3b8", fontSize: 13 }}>
            Showing {locations.length} location{locations.length !== 1 ? "s" : ""}.
            To view on an interactive map, install <code>react-leaflet</code> (npm i react-leaflet leaflet).
          </div>

          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid #334155", color: "#94a3b8", fontSize: 12, textTransform: "uppercase" }}>
                <th style={{ textAlign: "left", padding: "8px 12px" }}>Source</th>
                <th style={{ textAlign: "left", padding: "8px 12px" }}>Timestamp</th>
                <th style={{ textAlign: "right", padding: "8px 12px" }}>Latitude</th>
                <th style={{ textAlign: "right", padding: "8px 12px" }}>Longitude</th>
                <th style={{ textAlign: "left", padding: "8px 12px" }}>Label</th>
                <th style={{ textAlign: "center", padding: "8px 12px" }}>Map</th>
              </tr>
            </thead>
            <tbody>
              {locations.slice(0, 200).map((loc: any) => (
                <tr
                  key={loc.id}
                  style={{
                    borderBottom: "1px solid #1e293b",
                    cursor: "pointer",
                    background: selectedLoc?.id === loc.id ? "#1e293b" : "transparent",
                  }}
                  onClick={() => setSelectedLoc(selectedLoc?.id === loc.id ? null : loc)}
                >
                  <td style={{ padding: "8px 12px", color: "#e2e8f0" }}>
                    {sourceIcon(loc.source_type)} {loc.source_type}
                  </td>
                  <td style={{ padding: "8px 12px", color: "#94a3b8", fontSize: 13 }}>
                    {loc.timestamp ? new Date(loc.timestamp).toLocaleString() : "--"}
                  </td>
                  <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace", color: "#67e8f9", fontSize: 13 }}>
                    {loc.latitude?.toFixed(6)}
                  </td>
                  <td style={{ padding: "8px 12px", textAlign: "right", fontFamily: "monospace", color: "#67e8f9", fontSize: 13 }}>
                    {loc.longitude?.toFixed(6)}
                  </td>
                  <td style={{ padding: "8px 12px", color: "#94a3b8", fontSize: 13, maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {loc.label || "--"}
                  </td>
                  <td style={{ padding: "8px 12px", textAlign: "center" }}>
                    <a
                      href={`https://www.google.com/maps?q=${loc.latitude},${loc.longitude}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      style={{ color: "#6366f1", textDecoration: "underline", fontSize: 12 }}
                    >
                      View
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {locations.length > 200 && (
            <div style={{ color: "#64748b", fontSize: 12, textAlign: "center", marginTop: 8 }}>
              Showing first 200 of {locations.length} locations. Use filters to narrow results.
            </div>
          )}
        </>
      )}
    </div>
  );
}
