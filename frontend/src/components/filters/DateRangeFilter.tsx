"use client";

import { useState } from "react";

interface DateRangeFilterProps {
  dateStart: string | null;
  dateEnd: string | null;
  onChange: (start: string | null, end: string | null) => void;
}

const PRESETS = [
  { label: "All Time", days: null },
  { label: "Last 7d", days: 7 },
  { label: "Last 30d", days: 30 },
  { label: "Last 90d", days: 90 },
  { label: "Last Year", days: 365 },
  { label: "Custom", days: -1 },
] as const;

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().split("T")[0];
}

export default function DateRangeFilter({ dateStart, dateEnd, onChange }: DateRangeFilterProps) {
  const [showCustom, setShowCustom] = useState(false);

  const activePreset = (() => {
    if (!dateStart && !dateEnd) return "All Time";
    if (showCustom) return "Custom";
    for (const p of PRESETS) {
      if (p.days && p.days > 0 && dateStart === daysAgo(p.days) && !dateEnd) {
        return p.label;
      }
    }
    return "Custom";
  })();

  const handlePreset = (preset: (typeof PRESETS)[number]) => {
    if (preset.days === null) {
      // All Time
      setShowCustom(false);
      onChange(null, null);
    } else if (preset.days === -1) {
      // Custom
      setShowCustom(true);
    } else {
      setShowCustom(false);
      onChange(daysAgo(preset.days), null);
    }
  };

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-xs text-slate-500 uppercase tracking-wider shrink-0">Period</span>

      {PRESETS.map((p) => (
        <button
          key={p.label}
          onClick={() => handlePreset(p)}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
            activePreset === p.label
              ? "bg-forensic-accent/20 text-forensic-accent border border-forensic-accent"
              : "bg-forensic-bg text-slate-400 border border-forensic-border hover:border-slate-500"
          }`}
        >
          {p.label}
        </button>
      ))}

      {showCustom && (
        <div className="flex items-center gap-2 ml-2">
          <input
            type="date"
            value={dateStart || ""}
            onChange={(e) => onChange(e.target.value || null, dateEnd)}
            className="bg-forensic-bg border border-forensic-border rounded px-2 py-1 text-xs text-slate-300"
          />
          <span className="text-xs text-slate-500">to</span>
          <input
            type="date"
            value={dateEnd || ""}
            onChange={(e) => onChange(dateStart, e.target.value || null)}
            className="bg-forensic-bg border border-forensic-border rounded px-2 py-1 text-xs text-slate-300"
          />
        </div>
      )}
    </div>
  );
}
