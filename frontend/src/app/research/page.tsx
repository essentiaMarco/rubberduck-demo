"use client";

import { useEffect, useState } from "react";
import { osint } from "@/lib/api";

interface ResearchPlan {
  id: string;
  title: string;
  status: string;
  created_at: string;
  case_id?: string;
}

interface Capture {
  id: string;
  url: string;
  page_title: string;
  capture_timestamp: string;
  http_status: number;
}

export default function WebResearchPage() {
  const [plans, setPlans] = useState<ResearchPlan[]>([]);
  const [captures, setCaptures] = useState<Capture[]>([]);
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    osint
      .listPlans()
      .then((r) => setPlans(Array.isArray(r) ? r : []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedPlan) {
      osint
        .listCaptures(selectedPlan)
        .then((r) => setCaptures(Array.isArray(r) ? r : []))
        .catch(() => setCaptures([]));
    } else {
      setCaptures([]);
    }
  }, [selectedPlan]);

  const approvePlan = async (planId: string) => {
    try {
      await osint.approvePlan(planId);
      // Refresh plans
      const updated = await osint.listPlans();
      setPlans(Array.isArray(updated) ? updated : []);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Web Research (OSINT)</h1>

      <div className="bg-yellow-900/20 border border-yellow-800 rounded-lg p-4 mb-6">
        <p className="text-sm text-yellow-400">
          Web research plans must be reviewed and approved before execution to ensure
          legal and ethical compliance with evidence collection standards.
        </p>
      </div>

      {/* Research Plans */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-4">Research Plans</h2>

        {loading ? (
          <p className="text-slate-500 text-sm">Loading plans...</p>
        ) : plans.length === 0 ? (
          <div className="bg-forensic-surface rounded-lg border border-forensic-border p-8 text-center">
            <p className="text-slate-400 mb-2">No research plans created yet.</p>
            <p className="text-xs text-slate-500">
              Research plans define OSINT collection targets and methods.
              They must be approved before any web captures are executed.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {plans.map((plan) => (
              <div
                key={plan.id}
                className={`bg-forensic-surface rounded-lg border p-4 cursor-pointer transition-colors ${
                  selectedPlan === plan.id
                    ? "border-forensic-accent"
                    : "border-forensic-border hover:border-slate-600"
                }`}
                onClick={() => setSelectedPlan(plan.id === selectedPlan ? null : plan.id)}
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-medium text-white">{plan.title}</h3>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        plan.status === "approved"
                          ? "bg-green-900/30 text-green-400"
                          : plan.status === "pending"
                          ? "bg-yellow-900/30 text-yellow-400"
                          : plan.status === "completed"
                          ? "bg-blue-900/30 text-blue-400"
                          : "bg-slate-700 text-slate-300"
                      }`}
                    >
                      {plan.status}
                    </span>
                    {plan.status === "pending" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          approvePlan(plan.id);
                        }}
                        className="text-xs bg-green-900/30 text-green-400 px-2 py-1 rounded hover:bg-green-900/50"
                      >
                        Approve
                      </button>
                    )}
                  </div>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Created: {new Date(plan.created_at).toLocaleString()}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Captures for selected plan */}
      {selectedPlan && (
        <div>
          <h2 className="text-lg font-semibold mb-4">
            Web Captures
            <span className="text-sm text-slate-500 font-normal ml-2">
              ({captures.length} captures)
            </span>
          </h2>

          {captures.length === 0 ? (
            <div className="bg-forensic-surface rounded-lg border border-forensic-border p-6 text-center">
              <p className="text-slate-400 text-sm">
                No captures yet for this research plan.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {captures.map((cap) => (
                <div
                  key={cap.id}
                  className="bg-forensic-surface rounded-lg border border-forensic-border p-3"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-white truncate">
                        {cap.page_title || cap.url}
                      </p>
                      <p className="text-xs text-slate-500 truncate mt-0.5">{cap.url}</p>
                    </div>
                    <div className="flex items-center gap-2 ml-3 shrink-0">
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          cap.http_status >= 200 && cap.http_status < 300
                            ? "bg-green-900/30 text-green-400"
                            : "bg-red-900/30 text-red-400"
                        }`}
                      >
                        {cap.http_status}
                      </span>
                      <span className="text-xs text-slate-500">
                        {new Date(cap.capture_timestamp).toLocaleString()}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
