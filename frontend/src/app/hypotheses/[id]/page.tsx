"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { hypotheses, hypothesesExt } from "@/lib/api";
import Link from "next/link";

export default function HypothesisDetailPage() {
  const params = useParams();
  const hypId = params.id as string;
  const [hyp, setHyp] = useState<any>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evalResult, setEvalResult] = useState<any>(null);

  const load = () => {
    hypotheses.get(hypId).then(setHyp).catch(console.error);
  };

  useEffect(() => {
    load();
  }, [hypId]);

  const runEvaluation = async () => {
    setEvaluating(true);
    try {
      const result = await hypotheses.evaluate(hypId);
      setEvalResult(result);
      load(); // refresh
    } catch (err: any) {
      console.error(err);
    } finally {
      setEvaluating(false);
    }
  };

  if (!hyp) return <div className="text-slate-400">Loading...</div>;

  const statusColor =
    hyp.status === "supported"
      ? "bg-green-900/30 text-green-400"
      : hyp.status === "refuted"
      ? "bg-red-900/30 text-red-400"
      : "bg-blue-900/30 text-blue-400";

  return (
    <div>
      <Link href="/hypotheses" className="text-sm text-slate-400 hover:text-white mb-4 inline-block">
        &larr; Back to Hypotheses
      </Link>

      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{hyp.title}</h1>
          {hyp.description && <p className="text-slate-400 mt-1">{hyp.description}</p>}
        </div>
        <div className="flex items-center gap-3">
          <span className={`px-3 py-1 rounded text-sm font-medium ${statusColor}`}>
            {hyp.status}
          </span>
          {hyp.confidence != null && (
            <span className="text-lg font-bold text-forensic-accent">
              {Math.round(hyp.confidence * 100)}%
            </span>
          )}
        </div>
      </div>

      {/* Evaluate button */}
      <div className="mb-6">
        <button
          onClick={runEvaluation}
          disabled={evaluating}
          className="bg-forensic-accent text-forensic-bg px-4 py-2 rounded text-sm font-medium hover:bg-forensic-accent/90 disabled:opacity-50"
        >
          {evaluating ? "Evaluating..." : "Run Confidence Evaluation"}
        </button>
      </div>

      {/* Evaluation result */}
      {evalResult && (
        <div className="bg-forensic-surface rounded-lg border border-forensic-border p-4 mb-6">
          <h3 className="text-sm font-semibold mb-3 text-forensic-accent">Evaluation Result</h3>
          <div className="grid grid-cols-4 gap-4 mb-3">
            <div className="text-center">
              <p className="text-2xl font-bold text-green-400">{evalResult.supporting_count}</p>
              <p className="text-xs text-slate-500">Supporting</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-red-400">{evalResult.disconfirming_count}</p>
              <p className="text-xs text-slate-500">Disconfirming</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-slate-400">{evalResult.neutral_count}</p>
              <p className="text-xs text-slate-500">Neutral</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-yellow-400">{evalResult.gap_count}</p>
              <p className="text-xs text-slate-500">Gaps</p>
            </div>
          </div>
          {evalResult.summary && (
            <p className="text-sm text-slate-300 border-t border-forensic-border pt-3">{evalResult.summary}</p>
          )}
        </div>
      )}

      {/* Findings */}
      <div className="mb-8">
        <h2 className="text-lg font-semibold mb-4">
          Findings <span className="text-sm text-slate-500 font-normal">({hyp.findings?.length || 0})</span>
        </h2>
        {hyp.findings && hyp.findings.length > 0 ? (
          <div className="space-y-3">
            {hyp.findings.map((f: any) => (
              <div key={f.id} className="bg-forensic-surface rounded-lg border border-forensic-border p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span
                        className={`text-xs px-2 py-0.5 rounded ${
                          f.finding_type === "supporting"
                            ? "bg-green-900/30 text-green-400"
                            : f.finding_type === "disconfirming"
                            ? "bg-red-900/30 text-red-400"
                            : "bg-slate-700 text-slate-300"
                        }`}
                      >
                        {f.finding_type}
                      </span>
                      <span className="text-xs text-slate-500">weight: {f.weight}</span>
                      {f.auto_generated && (
                        <span className="text-xs text-slate-600">auto</span>
                      )}
                    </div>
                    <p className="text-sm text-slate-300">{f.description}</p>
                    {f.evidence_file_id && (
                      <Link
                        href={`/evidence/${f.evidence_file_id}`}
                        className="text-xs text-forensic-accent hover:underline mt-1 inline-block"
                      >
                        View evidence file
                      </Link>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-500 text-sm">No findings yet.</p>
        )}
      </div>

      {/* Gaps */}
      <div>
        <h2 className="text-lg font-semibold mb-4">
          Evidence Gaps <span className="text-sm text-slate-500 font-normal">({hyp.gaps?.length || 0})</span>
        </h2>
        {hyp.gaps && hyp.gaps.length > 0 ? (
          <div className="space-y-3">
            {hyp.gaps.map((g: any, i: number) => (
              <div key={g.id || i} className="bg-yellow-900/10 rounded-lg border border-yellow-800/30 p-4">
                <p className="text-sm text-yellow-300">{g.description}</p>
                {g.suggested_action && (
                  <p className="text-xs text-slate-500 mt-1">Suggestion: {g.suggested_action}</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-slate-500 text-sm">No evidence gaps identified.</p>
        )}
      </div>
    </div>
  );
}
