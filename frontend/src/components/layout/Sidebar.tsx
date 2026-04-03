"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "🏠" },
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

  return (
    <aside className="w-56 bg-forensic-surface border-r border-forensic-border flex flex-col h-full">
      <div className="p-4 border-b border-forensic-border">
        <h1 className="text-lg font-bold text-forensic-accent">
          Rubberduck
        </h1>
        <p className="text-xs text-slate-500 mt-1">Digital Forensic Platform</p>
      </div>

      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);

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
              <span>{item.label}</span>
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
