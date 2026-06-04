import React, { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

interface PRPoint {
  precision: number;
  recall: number;
}

interface PRData {
  mad: PRPoint[];
  isolation_forest: PRPoint[];
  summary?: {
    mad?: { precision: number; recall: number; f1: number };
    isolation_forest?: { precision: number; recall: number; f1: number };
  };
}

export default function AnomalyComparison() {
  const [prData, setPrData] = useState<PRData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchPrData() {
      try {
        setLoading(true);
        setError(null);
        // Try to load from benchmark results API
        const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";
        const resp = await fetch(`${baseUrl}/api/metrics/pr-curves`);
        if (resp.ok) {
          const data = await resp.json();
          setPrData(data);
        } else {
          // Fallback: try to fetch from static benchmark result
          const today = new Date().toISOString().slice(0, 10);
          const staticResp = await fetch(`/benchmarks/results/${today}/anomaly_pr.json`);
          if (staticResp.ok) {
            const staticData = await staticResp.json();
            setPrData({
              mad: staticData.pr_curve_data?.mad || [],
              isolation_forest: staticData.pr_curve_data?.isolation_forest || [],
              summary: staticData.results,
            });
          } else {
            setError("No benchmark data available. Run 'make benchmark' to generate PR curves.");
          }
        }
      } catch {
        setError("No benchmark data available. Run 'make benchmark' to generate PR curves.");
      } finally {
        setLoading(false);
      }
    }
    fetchPrData();
  }, []);

  // Transform data for Recharts (merge MAD and IF points by recall)
  const chartData: Array<{
    recall: number;
    mad_precision?: number;
    if_precision?: number;
  }> = [];

  if (prData) {
    const allRecalls = new Set<number>();
    prData.mad.forEach((p) => allRecalls.add(p.recall));
    prData.isolation_forest.forEach((p) => allRecalls.add(p.recall));
    const sortedRecalls = Array.from(allRecalls).sort((a, b) => a - b);

    sortedRecalls.forEach((r) => {
      const madPt = prData.mad.find((p) => Math.abs(p.recall - r) < 0.001);
      const ifPt = prData.isolation_forest.find((p) => Math.abs(p.recall - r) < 0.001);
      chartData.push({
        recall: r,
        mad_precision: madPt?.precision,
        if_precision: ifPt?.precision,
      });
    });
  }

  return (
    <div>
      <h2 className="card-title" style={{ marginBottom: 24 }}>
        Anomaly Methods Comparison
      </h2>

      {loading && <div className="loading">Loading benchmark data...</div>}

      {error && !loading && (
        <div className="card" style={{ marginBottom: 24 }}>
          <p style={{ color: "var(--color-text-muted)" }}>{error}</p>
        </div>
      )}

      {prData?.summary && (
        <div className="grid grid-3" style={{ marginBottom: 24 }}>
          <div className="card stat-tile">
            <span className="stat-label">MAD F1 Score</span>
            <span className="stat-value">
              {prData.summary.mad?.f1 != null ? prData.summary.mad.f1.toFixed(3) : "\u2014"}
            </span>
          </div>
          <div className="card stat-tile">
            <span className="stat-label">Isolation Forest F1 Score</span>
            <span className="stat-value">
              {prData.summary.isolation_forest?.f1 != null
                ? prData.summary.isolation_forest.f1.toFixed(3)
                : "\u2014"}
            </span>
          </div>
          <div className="card stat-tile">
            <span className="stat-label">
              MAD Precision / Recall
            </span>
            <span className="stat-value" style={{ fontSize: "1rem" }}>
              {prData.summary.mad ? (
                <>
                  P: {prData.summary.mad.precision.toFixed(3)} / R:{" "}
                  {prData.summary.mad.recall.toFixed(3)}
                </>
              ) : (
                "\u2014"
              )}
            </span>
          </div>
        </div>
      )}

      {chartData.length > 0 && (
        <div className="card">
          <h3 className="card-title">Precision-Recall Curves</h3>
          <div style={{ marginBottom: 8, fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
            Comparing MAD robust z-score vs Isolation Forest on held-out incidents
          </div>
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="recall"
                stroke="var(--color-text-muted)"
                fontSize={11}
                label={{
                  value: "Recall",
                  position: "insideBottom",
                  offset: -5,
                  style: { fill: "var(--color-text-muted)", fontSize: 12 },
                }}
                domain={[0, 1]}
                tickFormatter={(v) => v.toFixed(1)}
              />
              <YAxis
                stroke="var(--color-text-muted)"
                fontSize={11}
                label={{
                  value: "Precision",
                  angle: -90,
                  position: "insideLeft",
                  style: { fill: "var(--color-text-muted)", fontSize: 12 },
                }}
                domain={[0, 1]}
                tickFormatter={(v) => v.toFixed(1)}
              />
              <Tooltip
                contentStyle={{
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius)",
                }}
                formatter={(value: number) => value.toFixed(3)}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="mad_precision"
                stroke="var(--color-primary)"
                name="MAD z-score"
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                dataKey="if_precision"
                stroke="var(--color-warning)"
                name="Isolation Forest"
                dot={false}
                strokeWidth={2}
                strokeDasharray="5 5"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {!loading && !error && chartData.length === 0 && (
        <div className="empty-state">
          Run <code>make benchmark</code> to generate PR curve data, then refresh.
        </div>
      )}
    </div>
  );
}