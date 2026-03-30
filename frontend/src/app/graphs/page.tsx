"use client";

import { useEffect, useState, useRef } from "react";
import { graph } from "@/lib/api";

export default function GraphsPage() {
  const [graphData, setGraphData] = useState<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    graph.getFull({ limit: "200" }).then(setGraphData).catch(console.error);
  }, []);

  useEffect(() => {
    if (!graphData || !containerRef.current) return;
    // Dynamic import for cytoscape (client-side only)
    import("cytoscape").then((cyModule) => {
      const cy = cyModule.default({
        container: containerRef.current,
        elements: [
          ...graphData.nodes.map((n: any) => ({
            data: { id: n.id, label: n.label, type: n.entity_type },
          })),
          ...graphData.edges.map((e: any) => ({
            data: { id: e.id, source: e.source, target: e.target, label: e.rel_type },
          })),
        ],
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              "background-color": "#38bdf8",
              color: "#f1f5f9",
              "font-size": "10px",
              "text-valign": "bottom",
              "text-margin-y": 5,
              width: 20,
              height: 20,
            },
          },
          {
            selector: "edge",
            style: {
              "line-color": "#334155",
              "target-arrow-color": "#334155",
              "target-arrow-shape": "triangle",
              "curve-style": "bezier",
              width: 1,
            },
          },
        ],
        layout: { name: "cose", animate: false },
      });
      return () => cy.destroy();
    });
  }, [graphData]);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Relationship Graph</h1>

      {graphData && (
        <div className="flex gap-4 mb-4 text-sm text-slate-400">
          <span>{graphData.node_count} nodes</span>
          <span>{graphData.edge_count} edges</span>
        </div>
      )}

      <div
        ref={containerRef}
        className="bg-forensic-surface rounded-lg border border-forensic-border"
        style={{ height: "600px" }}
      />

      {!graphData && (
        <p className="text-slate-500 text-sm mt-4">Loading graph data...</p>
      )}
    </div>
  );
}
