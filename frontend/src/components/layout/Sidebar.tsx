"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const NAV_GROUPS = [
  {
    label: "Intelligence",
    items: [
      { href: "/", label: "Dashboard", icon: "grid" },
      { href: "/alerts", label: "Alerts", icon: "alert", badgeKey: "alerts" },
      { href: "/secrets", label: "Secrets", icon: "key", badgeKey: "secrets" },
      { href: "/search", label: "Search", icon: "search" },
    ],
  },
  {
    label: "Analysis",
    items: [
      { href: "/communications", label: "Communications", icon: "message" },
      { href: "/phone-analysis", label: "Phone Analysis", icon: "phone" },
      { href: "/financial", label: "Financial", icon: "dollar" },
      { href: "/map", label: "Geospatial", icon: "map" },
      { href: "/timeline", label: "Timeline", icon: "clock" },
    ],
  },
  {
    label: "Investigation",
    items: [
      { href: "/evidence", label: "Evidence", icon: "folder" },
      { href: "/entities", label: "Entities", icon: "users" },
      { href: "/graphs", label: "Graph", icon: "share" },
      { href: "/hypotheses", label: "Hypotheses", icon: "beaker" },
    ],
  },
  {
    label: "Reporting",
    items: [
      { href: "/legal", label: "Legal Drafting", icon: "scale" },
      { href: "/reports", label: "Reports", icon: "doc" },
      { href: "/notebook", label: "Notebook", icon: "edit" },
      { href: "/research", label: "Web Research", icon: "globe" },
    ],
  },
];

function NavIcon({ name }: { name: string }) {
  const icons: Record<string, string> = {
    grid: "M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z",
    alert: "M12 9v2m0 4h.01M5.07 19H19a2 2 0 001.75-2.96L13.75 4a2 2 0 00-3.5 0L3.32 16.04A2 2 0 005.07 19z",
    key: "M15 7a2 2 0 012 2m4 0a6 6 0 01-7.74 5.74L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.59a1 1 0 01.29-.7l6.97-6.97A6 6 0 0121 9z",
    search: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
    message: "M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.42-4.03 8-9 8a9.86 9.86 0 01-4.25-.96L3 20l1.13-3.38A7.95 7.95 0 013 12c0-4.42 4.03-8 9-8s9 3.58 9 8z",
    phone: "M3 5a2 2 0 012-2h3.28a1 1 0 01.95.68l1.49 4.46a1 1 0 01-.5 1.21l-2.38 1.19a11.04 11.04 0 005.12 5.12l1.19-2.38a1 1 0 011.21-.5l4.46 1.49a1 1 0 01.68.95V19a2 2 0 01-2 2h-1C9.72 21 3 14.28 3 6V5z",
    dollar: "M12 8c-1.66 0-3 .9-3 2s1.34 2 3 2 3 .9 3 2-1.34 2-3 2m0-12v2m0 16v2",
    map: "M9 20l-5.45-2.73A2 2 0 012 15.42V5.58a2 2 0 012.82-1.82L9 6l6-3 5.45 2.73A2 2 0 0122 7.58v9.84a2 2 0 01-2.82 1.82L15 17l-6 3z",
    clock: "M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z",
    folder: "M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z",
    users: "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75",
    share: "M18 16a3 3 0 01-2.12-.88l-7.76-7.76A3 3 0 016 8a3 3 0 110-6 3 3 0 012.12.88l7.76 7.76A3 3 0 0118 10a3 3 0 110 6zM6 16a3 3 0 100 6 3 3 0 000-6z",
    beaker: "M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z",
    scale: "M3 6l3 1m0 0l-3 9a5.002 5.002 0 006 0l-3-9m0 0l6-3m6 3l3 1m0 0l-3 9a5.002 5.002 0 006 0l-3-9m0 0l-6-3m3-3v18",
    doc: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.59a1 1 0 01.7.29l5.42 5.42a1 1 0 01.29.7V19a2 2 0 01-2 2z",
    edit: "M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.41-9.41a2 2 0 112.83 2.83L11.41 12H9v-2.41l8.59-8.59z",
    globe: "M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.66 0 3-4.03 3-9s-1.34-9-3-9m0 18c-1.66 0-3-4.03-3-9s1.34-9 3-9",
  };
  const d = icons[name] || icons.grid;
  return (
    <svg className="w-4 h-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
      <path strokeLinecap="round" strokeLinejoin="round" d={d} />
    </svg>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [badges, setBadges] = useState<Record<string, number>>({});

  useEffect(() => {
    Promise.all([
      fetch("/api/alerts/stats").then(r => r.ok ? r.json() : null).catch(() => null),
      fetch("/api/secrets/stats").then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([alertData, secretData]) => {
      const b: Record<string, number> = {};
      if (alertData?.unreviewed) b.alerts = alertData.unreviewed;
      if (secretData?.unreviewed) b.secrets = secretData.unreviewed;
      setBadges(b);
    });
  }, [pathname]);

  return (
    <aside className="w-60 bg-forensic-surface border-r border-forensic-border flex flex-col h-full">
      {/* Brand header */}
      <div className="px-5 py-5 border-b border-forensic-border">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-glow-sm">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.62-.38a2 2 0 01.34 2.76l-7.38 9.84a2 2 0 01-3.16 0l-7.38-9.84a2 2 0 01.34-2.76l7.38-5.54a2 2 0 012.44 0l7.38 5.54z" />
            </svg>
          </div>
          <div>
            <h1 className="text-sm font-bold tracking-tight text-white">
              Gotham<span className="text-indigo-400">4</span>Justice
            </h1>
            <p className="text-[10px] text-slate-500 tracking-wider uppercase">Forensic Intelligence</p>
          </div>
        </div>
      </div>

      {/* Navigation groups */}
      <nav className="flex-1 py-3 overflow-y-auto">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-1">
            <div className="px-5 py-1.5">
              <span className="text-[10px] font-semibold tracking-wider uppercase text-slate-500">
                {group.label}
              </span>
            </div>
            {group.items.map((item) => {
              const isActive =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);

              const badgeCount = (item as any).badgeKey ? badges[(item as any).badgeKey] : undefined;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 mx-2 px-3 py-2 text-[13px] rounded-lg transition-all duration-150 ${
                    isActive
                      ? "bg-indigo-500/10 text-indigo-400 shadow-glow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.03]"
                  }`}
                >
                  <NavIcon name={item.icon} />
                  <span className="flex-1 font-medium">{item.label}</span>
                  {badgeCount !== undefined && badgeCount > 0 && (
                    <span className="bg-red-500/90 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[20px] text-center leading-none">
                      {badgeCount > 999 ? `${Math.floor(badgeCount / 1000)}k` : badgeCount}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-3 border-t border-forensic-border">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <p className="text-[11px] text-slate-500">v0.2.0 &middot; Secure Local</p>
        </div>
      </div>
    </aside>
  );
}
