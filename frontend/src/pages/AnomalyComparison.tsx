import React from "react";
import { useQuery } from "@tanstack/react-query";
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
import { metricsApi, type PRCurveResponse } from "../api/client";

export default function AnomalyComparison() {
  const {
    data: prData,
    isLoading,
    error,
  } = useQuery<PRCurveResponse>({
    queryKey: ["prCurves"],
    queryFn: metricsApi.prCurves,
  });

  const chartData: Array<{
    recall: number;
    mad_precision?: number;
    if_precision?: number;
  }> = [];

  if (prData) {
    const allRecalls = new Set<number>();
    prData.mad.forEach((point) => allRecalls.add(point.recall));
    prData.isolation_forest.forEach((point) => allRecalls.add(point.recall));
    const sortedRecalls = Array.from(allRecalls).sort((a, b) => a - b);

    sortedRecalls.forEach((recall) => {
      const madPoint = prData.mad.find((point) => Math.abs(point.recall - recall) < 0.001);
      const isolationPoint = prData.isolation_forest.find(
        (point) => Math.abs(point.recall - recall) < 0.001,
      );
      chartData.push({
        recall,
        mad_precision: madPoint?.precision,
        if_precision: isolationPoint?.precision,
      });
    });
  }

  return (
    <div>
      <h2 className="card-title" style={{ marginBottom: 24 }}>
        Anomaly Methods Comparison
      </h2>

      {isLoading && <div className="loading">Loading benchmark data...</div>}

      {error && !isLoading && (
        <div className="card" style={{ marginBottom: 24 }}>
          <p style={{ color: "var(--color-text-muted)" }}>
            No benchmark data available. Run make benchmark to generate PR curves.
          </p>
        </div>
      )}

      {prData?.summary && (
        <div className="grid grid-3" style={{ marginBottom: 24 }}>
          <div className="card stat-tile">
            <span className="stat-label">MAD F1 Score</span>
            <span className="stat-value">
              {prData.summary.mad?.f1 != null ? prData.summary.mad.f1.toFixed(3) : "-"}
            </span>
          </div>
          <div className="card stat-tile">
            <span className="stat-label">Isolation Forest F1 Score</span>
            <span className="stat-value">
              {prData.summary.isolation_forest?.f1 != null
                ? prData.summary.isolation_forest.f1.toFixed(3)
                : "-"}
            </span>
          </div>
          <div className="card stat-tile">
            <span className="stat-label">MAD Precision / Recall</span>
            <span className="stat-value" style={{ fontSize: "1rem" }}>
              {prData.summary.mad ? (
                <>
                  P: {prData.summary.mad.precision.toFixed(3)} / R:{" "}
                  {prData.summary.mad.recall.toFixed(3)}
                </>
              ) : (
                "-"
              )}
            </span>
          </div>
        </div>
      )}

      {chartData.length > 0 && (
        <div className="card">
          <h3 className="card-title">Precision-Recall Curves</h3>
          <div style={{ marginBottom: 8, fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
            MAD robust z-score compared with Isolation Forest on held-out incidents
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
                tickFormatter={(value) => value.toFixed(1)}
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
                tickFormatter={(value) => value.toFixed(1)}
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

      {!isLoading && !error && chartData.length === 0 && (
        <div className="empty-state">
          Run make benchmark to generate PR curve data, then refresh.
        </div>
      )}
    </div>
  );
}
