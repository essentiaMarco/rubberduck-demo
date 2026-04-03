"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { graph } from "@/lib/api";
import DateRangeFilter from "@/components/filters/DateRangeFilter";

const ENTITY_TYPES = [
  { value: "person", label: "Person", color: "#f97316" },
  { value: "org", label: "Organization", color: "#8b5cf6" },
  { value: "email", label: "Email", color: "#06b6d4" },
  { value: "phone", label: "Phone", color: "#22c55e" },
  { value: "ip", label: "IP Address", color: "#eab308" },
  { value: "location", label: "Location", color: "#ec4899" },
  { value: "device", label: "Device", color: "#64748b" },
  { value: "account", label: "Account", color: "#14b8a6" },
  { value: "url", label: "URL", color: "#a855f7" },
];

const LAYERS = [
  { value: "communications", label: "Communications" },
  { value: "digital_activity", label: "Digital Activity" },
  { value: "financial", label: "Financial" },
  { value: "legal", label: "Legal" },
  { value: "movements", label: "Movements" },
];

const TYPE_COLOR_MAP: Record<string, string> = {};
ENTITY_TYPES.forEach((t) => (TYPE_COLOR_MAP[t.value] = t.color));

export default function GraphsPage() {
  const [graphData, setGraphData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<any>(null);

  // Filter state
  const [selectedTypes, setSelectedTypes] = useState<string[]>([]);
  const [selectedLayers, setSelectedLayers] = useState<string[]>([]);
  const [minConfidence, setMinConfidence] = useState(0.5);
  const [limit, setLimit] = useState(200);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [dateStart, setDateStart] = useState<string | null>(null);
  const [dateEnd, setDateEnd] = useState<string | null>(null);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, string> = {
        limit: String(limit),
        min_confidence: String(minConfidence),
      };
      if (selectedTypes.length > 0) {
        params.entity_types = selectedTypes.join(",");
      }
      if (selectedLayers.length > 0) {
        params.layers = selectedLayers.join(",");
      }
      if (dateStart) params.date_start = dateStart;
      if (dateEnd) params.date_end = dateEnd;
      const data = await graph.getFull(params);
      setGraphData(data);
    } catch (err: any) {
      setError(err.message || "Failed to load graph");
    } finally {
      setLoading(false);
    }
  }, [limit, minConfidence, selectedTypes, selectedLayers, dateStart, dateEnd]);

  // Initial load
  useEffect(() => {
    fetchGraph();
  }, []);

  // Render Cytoscape
  useEffect(() => {
    if (!graphData || !containerRef.current) return;

    // Destroy previous instance
    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    const connectedNodeIds = new Set<string>();
    for (const e of graphData.edges) {
      connectedNodeIds.add(e.source);
      connectedNodeIds.add(e.target);
    }
    const connectedNodes =
      graphData.edges.length > 0
        ? graphData.nodes.filter((n: any) => connectedNodeIds.has(n.id))
        : graphData.nodes.slice(0, 50);

    // Compute degree range for sizing
    const degrees = connectedNodes.map((n: any) => n.degree || 1);
    const maxDegree = Math.max(...degrees, 1);
    const minDegree = Math.min(...degrees, 1);

    import("cytoscape").then((cyModule) => {
      const cy = cyModule.default({
        container: containerRef.current,
        elements: [
          ...connectedNodes.map((n: any) => ({
            data: {
              id: n.id,
              label: n.label,
              type: n.entity_type,
              degree: n.degree || 1,
              // Normalize size: 15–60px based on degree
              nodeSize:
                minDegree === maxDegree
                  ? 25
                  : 15 + ((n.degree - minDegree) / (maxDegree - minDegree)) * 45,
            },
          })),
          ...graphData.edges.map((e: any) => ({
            data: {
              id: e.id,
              source: e.source,
              target: e.target,
              label: e.rel_type,
              layer: e.layer,
              weight: e.weight || 1,
            },
          })),
        ],
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              "background-color": "#38bdf8",
              color: "#f1f5f9",
              "font-size": "9px",
              "text-valign": "bottom",
              "text-margin-y": 5,
              width: "data(nodeSize)",
              height: "data(nodeSize)",
              "border-width": 1,
              "border-color": "#1e293b",
              "text-max-width": "80px",
              "text-wrap": "ellipsis",
            },
          },
          // Color nodes by entity type
          ...ENTITY_TYPES.map((t) => ({
            selector: `node[type="${t.value}"]`,
            style: {
              "background-color": t.color,
            },
          })),
          {
            selector: "node:selected",
            style: {
              "border-width": 3,
              "border-color": "#ffffff",
              "background-color": "#facc15",
            },
          },
          {
            selector: "edge",
            style: {
              "line-color": "#334155",
              "target-arrow-color": "#334155",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              width: 0.5,
              opacity: 0.4,
            } as any,
          },
          {
            selector: "edge:selected",
            style: {
              "line-color": "#facc15",
              "target-arrow-color": "#facc15",
              width: 2,
              opacity: 1,
            },
          },
        ],
        layout: {
          name: graphData.edges.length > 0 ? "cose" : "grid",
          animate: false,
          ...(graphData.edges.length > 0
            ? {
                nodeRepulsion: () => 800000,
                idealEdgeLength: () => 120,
                gravity: 0.3,
                numIter: 500,
                padding: 40,
              }
            : {}),
        },
        minZoom: 0.1,
        maxZoom: 5,
        wheelSensitivity: 0.3,
      });

      // Click handler for node details
      cy.on("tap", "node", (evt: any) => {
        const node = evt.target;
        setSelectedNode({
          id: node.id(),
          label: node.data("label"),
          type: node.data("type"),
          degree: node.data("degree"),
        });
      });

      cy.on("tap", (evt: any) => {
        if (evt.target === cy) {
          setSelectedNode(null);
        }
      });

      cyRef.current = cy;
    });
  }, [graphData]);

  const toggleType = (type: string) => {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  const toggleLayer = (layer: string) => {
    setSelectedLayers((prev) =>
      prev.includes(layer) ? prev.filter((l) => l !== layer) : [...prev, layer]
    );
  };

  const hasEdges = graphData && graphData.edge_count > 0;

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">Relationship Graph</h1>
        {graphData && (
          <div className="flex gap-4 text-sm text-slate-400">
            <span>{graphData.node_count.toLocaleString()} entities</span>
            <span>{graphData.edge_count.toLocaleString()} relationships</span>
          </div>
        )}
      </div>

      {/* Filter bar */}
      <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4 mb-4 space-y-3">
        {/* Entity type chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-500 uppercase tracking-wider w-16 shrink-0">Types</span>
          {ENTITY_TYPES.map((t) => (
            <button
              key={t.value}
              onClick={() => toggleType(t.value)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors flex items-center gap-1.5 ${
                selectedTypes.length === 0 || selectedTypes.includes(t.value)
                  ? "opacity-100"
                  : "opacity-30"
              }`}
              style={{
                backgroundColor: `${t.color}22`,
                color: t.color,
                border: `1px solid ${
                  selectedTypes.includes(t.value) ? t.color : "transparent"
                }`,
              }}
            >
              <span
                className="w-2 h-2 rounded-full inline-block"
                style={{ backgroundColor: t.color }}
              />
              {t.label}
            </button>
          ))}
        </div>

        {/* Layer chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-500 uppercase tracking-wider w-16 shrink-0">Layers</span>
          {LAYERS.map((l) => (
            <button
              key={l.value}
              onClick={() => toggleLayer(l.value)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
                selectedLayers.includes(l.value)
                  ? "bg-forensic-accent/20 text-forensic-accent border-forensic-accent"
                  : "bg-forensic-bg text-slate-400 border-forensic-border hover:border-slate-500"
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>

        {/* Date range */}
        <DateRangeFilter
          dateStart={dateStart}
          dateEnd={dateEnd}
          onChange={(s, e) => { setDateStart(s); setDateEnd(e); }}
        />

        {/* Sliders and apply */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500">Confidence</label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={minConfidence}
              onChange={(e) => setMinConfidence(parseFloat(e.target.value))}
              className="w-28 accent-forensic-accent"
            />
            <span className="text-xs text-slate-300 w-8">{minConfidence.toFixed(2)}</span>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs text-slate-500">Max nodes</label>
            <select
              value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value))}
              className="bg-forensic-bg border border-forensic-border rounded px-2 py-1 text-xs text-slate-300"
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
              <option value={1000}>1,000</option>
            </select>
          </div>

          <button
            onClick={fetchGraph}
            disabled={loading}
            className="bg-forensic-accent text-forensic-bg px-4 py-1.5 rounded text-sm font-medium hover:bg-forensic-accent/90 disabled:opacity-50"
          >
            {loading ? "Loading..." : "Apply Filters"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {graphData && !hasEdges && (
        <div className="bg-yellow-900/20 border border-yellow-800 rounded-lg p-4 mb-4">
          <p className="text-sm text-yellow-400">
            No relationships found with current filters. Try lowering the confidence
            threshold or removing type/layer filters.
          </p>
        </div>
      )}

      {/* Graph canvas + node detail panel */}
      <div className="flex gap-4 flex-1 min-h-0">
        <div
          ref={containerRef}
          className="flex-1 bg-forensic-surface rounded-lg border border-forensic-border"
          style={{ height: "560px" }}
        />

        {/* Node detail sidebar */}
        {selectedNode && (
          <div className="w-64 bg-forensic-surface rounded-lg border border-forensic-border p-4 space-y-3 overflow-y-auto"
               style={{ height: "560px" }}>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Node Details</h3>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-slate-500 hover:text-white text-xs"
              >
                Close
              </button>
            </div>

            <div className="space-y-2">
              <div>
                <span className="text-xs text-slate-500">Name</span>
                <p className="text-sm text-white">{selectedNode.label}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500">Type</span>
                <p className="text-sm flex items-center gap-1.5">
                  <span
                    className="w-2 h-2 rounded-full inline-block"
                    style={{ backgroundColor: TYPE_COLOR_MAP[selectedNode.type] || "#38bdf8" }}
                  />
                  <span style={{ color: TYPE_COLOR_MAP[selectedNode.type] || "#38bdf8" }}>
                    {selectedNode.type}
                  </span>
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-500">Connections</span>
                <p className="text-sm text-white">{selectedNode.degree}</p>
              </div>
            </div>

            <a
              href={`/entities/${selectedNode.id}`}
              className="block text-center text-xs bg-forensic-accent/20 text-forensic-accent rounded px-3 py-2 hover:bg-forensic-accent/30 transition-colors"
            >
              View Entity Details
            </a>
          </div>
        )}
      </div>

      {loading && !graphData && (
        <p className="text-slate-500 text-sm mt-4">Loading graph data...</p>
      )}
    </div>
  );
}
