"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "🏠" },
  { href: "/alerts", label: "Alerts", icon: "🚨", badgeKey: "alerts" },
  { href: "/secrets", label: "Secrets", icon: "🔑", badgeKey: "secrets" },
  { href: "/financial", label: "Financial", icon: "💰" },
  { href: "/map", label: "Map", icon: "🗺️" },
  { href: "/search", label: "Search", icon: "🔎" },
  { href: "/communications", label: "Communications", icon: "💬" },
  { href: "/phone-analysis", label: "Phone Analysis", icon: "📞" },
  { href: "/evidence", label: "Evidence", icon: "📁" },
  { href: "/timeline", label: "Timeline", icon: "📅" },
  { href: "/entities", label: "Entities", icon: "👤" },
  { href: "/graphs", label: "Graphs", icon: "🕸️" },
  { href: "/hypotheses", label: "Hypotheses", icon: "🔬" },
  { href: "/research", label: "Web Research", icon: "🔍" },
  { href: "/legal", label: "Legal Drafting", icon: "⚖️" },
  { href: "/reports", label: "Reports", icon: "📊" },
  { href: "/notebook", label: "Notebook", icon: "📝" },
  { href: "/settings", label: "Settings", icon: "⚙️" },
];

export function Sidebar() {
  const pathname = usePathname();
  const [badges, setBadges] = useState<Record<string, number>>({});

  useEffect(() => {
    // Fetch badge counts for alerts and secrets
    Promise.all([
      fetch("/api/alerts/stats").then(r => r.ok ? r.json() : null).catch(() => null),
      fetch("/api/secrets/stats").then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([alertData, secretData]) => {
      const b: Record<string, number> = {};
      if (alertData?.unreviewed) b.alerts = alertData.unreviewed;
      if (secretData?.unreviewed) b.secrets = secretData.unreviewed;
      setBadges(b);
    });
  }, [pathname]); // Refresh badges on navigation

  return (
    <aside className="w-56 bg-forensic-surface border-r border-forensic-border flex flex-col h-full">
      <div className="p-4 border-b border-forensic-border">
        <h1 className="text-lg font-bold text-forensic-accent">
          Gotham4Justice
        </h1>
        <p className="text-xs text-slate-500 mt-1">Digital Forensic Platform</p>
      </div>

      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

          const badgeCount = (item as any).badgeKey ? badges[(item as any).badgeKey] : undefined;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                isActive
                  ? "bg-forensic-accent/10 text-forensic-accent border-r-2 border-forensic-accent"
                  : "text-slate-400 hover:text-slate-200 hover:bg-forensic-bg/50"
              }`}
            >
              <span className="text-base">{item.icon}</span>
              <span className="flex-1">{item.label}</span>
              {badgeCount !== undefined && badgeCount > 0 && (
                <span className="bg-red-500/80 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
                  {badgeCount > 999 ? `${Math.floor(badgeCount / 1000)}k` : badgeCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-forensic-border">
        <p className="text-xs text-slate-600">v0.1.0 — Local Only</p>
      </div>
    </aside>
  );
}
