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
import { buildComparisonData } from "./anomalyComparisonData";

export default function AnomalyComparison() {
  const {
    data: prData,
    isLoading,
    error,
  } = useQuery<PRCurveResponse>({
    queryKey: ["prCurves"],
    queryFn: metricsApi.prCurves,
  });

  const chartData = buildComparisonData(prData);

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Model evaluation</span>
          <h2 className="page-title">Anomaly Methods</h2>
          <p className="page-description">Transparent held-out comparison of robust MAD and Isolation Forest detectors.</p>
        </div>
        <span className="status-chip">Held-out evaluation</span>
      </div>

      {isLoading && <div className="loading">Loading benchmark data...</div>}

      {error && !isLoading && (
        <div className="card section-card">
          <p className="muted-copy">
            No benchmark data available. Run make benchmark to generate PR curves.
          </p>
        </div>
      )}

      {prData?.summary && (
        <div className="grid grid-3 stat-grid">
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
            <span className="stat-value stat-value--compact">
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
        <section className="card chart-card">
          <h3 className="card-title">Precision-Recall Curves</h3>
          <p className="chart-description">
            MAD robust z-score compared with Isolation Forest on held-out incidents
          </p>
          <div className="chart-canvas chart-canvas--large" role="img" aria-label="Precision-recall curves. MAD maintains higher precision than Isolation Forest across the measured recall range.">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 28 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="recall"
                type="number"
                stroke="#9aa5a1"
                fontSize={11}
                label={{
                  value: "Recall",
                  position: "insideBottom",
                  offset: -16,
                  style: { fill: "#9aa5a1", fontSize: 12 },
                }}
                domain={[0, 1]}
                ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
                tickFormatter={(value) => value.toFixed(1)}
              />
              <YAxis
                stroke="#9aa5a1"
                fontSize={11}
                label={{
                  value: "Precision",
                  angle: -90,
                  position: "insideLeft",
                  style: { fill: "#9aa5a1", fontSize: 12 },
                }}
                domain={[0, 1]}
                ticks={[0, 0.2, 0.4, 0.6, 0.8, 1]}
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
                stroke="#2dd4bf"
                name="MAD z-score"
                dot={{ r: 3 }}
                strokeWidth={2}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="if_precision"
                stroke="#f59e0b"
                name="Isolation Forest"
                dot={{ r: 3 }}
                strokeWidth={2}
                strokeDasharray="5 5"
                isAnimationActive={false}
              />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {!isLoading && !error && chartData.length === 0 && (
        <div className="empty-state">
          Run make benchmark to generate PR curve data, then refresh.
        </div>
      )}
    </div>
  );
}
