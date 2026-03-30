"use client";

import { useEffect, useState } from "react";
import { timeline } from "@/lib/api";

export default function TimelinePage() {
  const [events, setEvents] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    timeline.getEvents({ page_size: "50" }).then((r) => setEvents(r || [])).catch(console.error);
    timeline.getStats().then(setStats).catch(console.error);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Timeline</h1>

      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
            <p className="text-sm text-slate-400">Total Events</p>
            <p className="text-xl font-bold">{stats.total_events}</p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
            <p className="text-sm text-slate-400">Date Range</p>
            <p className="text-sm">{stats.date_range_start?.slice(0, 10)} — {stats.date_range_end?.slice(0, 10)}</p>
          </div>
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
            <p className="text-sm text-slate-400">Event Types</p>
            <p className="text-sm">{Object.keys(stats.by_type || {}).length} types</p>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {events.map((event: any, i: number) => (
          <div key={event.event_id || i} className="bg-forensic-surface rounded-lg border border-forensic-border p-4 flex items-start gap-4">
            <div className="w-24 shrink-0 text-xs text-slate-400">
              {event.timestamp_utc?.slice(0, 19)}
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="px-2 py-0.5 rounded text-xs bg-forensic-bg text-forensic-accent">
                  {event.event_type}
                </span>
                {event.event_subtype && (
                  <span className="text-xs text-slate-500">{event.event_subtype}</span>
                )}
              </div>
              <p className="text-sm">{event.summary}</p>
              {event.actor_name && (
                <p className="text-xs text-slate-500 mt-1">Actor: {event.actor_name}</p>
              )}
            </div>
          </div>
        ))}
        {events.length === 0 && (
          <p className="text-slate-500 text-sm">No timeline events yet. Ingest evidence to populate.</p>
        )}
      </div>
    </div>
  );
}
