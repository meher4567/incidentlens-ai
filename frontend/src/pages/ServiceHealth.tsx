import React, { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { servicesApi, type MetricWindow, type ServiceSummary } from "../api/client";

type ChartPoint = {
  time: string;
  request_count: number;
  error_rate: number;
  p95_latency_ms: number;
  baseline_request_count: number | null;
  baseline_error_rate: number | null;
  baseline_p95_latency_ms: number | null;
};

type MetricChartProps = {
  title: string;
  description: string;
  data: ChartPoint[];
  dataKey: "request_count" | "error_rate" | "p95_latency_ms";
  baselineKey:
    | "baseline_request_count"
    | "baseline_error_rate"
    | "baseline_p95_latency_ms";
  color: string;
};

function MetricChart({
  title,
  description,
  data,
  dataKey,
  baselineKey,
  color,
}: MetricChartProps) {
  const baseline = data[data.length - 1]?.[baselineKey];

  return (
    <section className="card chart-card">
      <h3 className="card-title">{title}</h3>
      <p className="chart-description">{description}</p>
      <div className="chart-canvas" role="img" aria-label={`${title} time series. ${description}`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#343a3a" />
            <XAxis
              dataKey="time"
              stroke="#9aa5a1"
              fontSize={11}
              minTickGap={28}
              tickLine={false}
            />
            <YAxis stroke="#9aa5a1" fontSize={11} width={46} tickLine={false} />
            <Tooltip
              contentStyle={{
                background: "#1b1e1e",
                border: "1px solid #475251",
                borderRadius: 8,
              }}
            />
            {baseline !== null && baseline !== undefined && (
              <ReferenceLine
                y={baseline}
                stroke="#64748b"
                strokeDasharray="5 5"
                label={{ value: "baseline", fill: "#9aa5a1", fontSize: 10 }}
              />
            )}
            <Line
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              dot={false}
              activeDot={{ r: 4 }}
              strokeWidth={2.5}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export default function ServiceHealth() {
  const { data: services, error: servicesError } = useQuery({
    queryKey: ["services"],
    queryFn: servicesApi.list,
  });

  const [selectedServiceId, setSelectedServiceId] = useState<string>("");
  const [windowSize, setWindowSize] = useState(60);
  const serviceList = useMemo(() => (Array.isArray(services) ? services : []), [services]);

  useEffect(() => {
    if (selectedServiceId || serviceList.length === 0) return;
    const defaultService =
      serviceList.find((item) => item.name === "payment-service") ?? serviceList[0];
    setSelectedServiceId(defaultService.id);
  }, [selectedServiceId, serviceList]);

  const { data: health, isLoading, error: healthError } = useQuery({
    queryKey: ["serviceHealth", selectedServiceId, windowSize],
    queryFn: () =>
      servicesApi.health(selectedServiceId, {
        window_size_seconds: String(windowSize),
        limit: "200",
      }),
    enabled: !!selectedServiceId,
  });

  const windows = health?.windows ?? [];
  const chartData: ChartPoint[] = windows.map((window: MetricWindow) => ({
    time: new Date(window.window_start).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    request_count: window.request_count,
    error_rate: Number(window.error_rate ?? 0) * 100,
    p95_latency_ms: window.p95_latency_ms,
    baseline_request_count: window.baseline_request_count ?? null,
    baseline_error_rate:
      window.baseline_error_rate == null ? null : Number(window.baseline_error_rate) * 100,
    baseline_p95_latency_ms: window.baseline_p95_latency_ms ?? null,
  }));
  const latest = chartData[chartData.length - 1];
  const isDegraded = !!latest && (latest.error_rate >= 5 || latest.p95_latency_ms >= 500);

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Telemetry explorer</span>
          <h2 className="page-title">Service Health</h2>
          <p className="page-description">
            Inspect volume, errors, and tail latency against learned baselines.
          </p>
        </div>
        {latest && (
          <span className={`status-chip ${isDegraded ? "status-chip--danger" : ""}`}>
            {isDegraded ? "Degraded" : "Within baseline"}
          </span>
        )}
      </div>

      <section className="card control-bar" aria-label="Service health filters">
        <label className="field-label">
          <span>Service</span>
          <select
            value={selectedServiceId}
            onChange={(event) => setSelectedServiceId(event.target.value)}
          >
            <option value="">Select a service</option>
            {serviceList.map((service: ServiceSummary) => (
              <option key={service.id} value={service.id}>
                {service.name}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label">
          <span>Aggregation window</span>
          <select
            value={windowSize}
            onChange={(event) => setWindowSize(Number(event.target.value))}
          >
            <option value={60}>1 minute</option>
            <option value={300}>5 minutes</option>
          </select>
        </label>
        {latest && (
          <dl className="latest-metrics">
            <div>
              <dt>Error rate</dt>
              <dd>{latest.error_rate.toFixed(1)}%</dd>
            </div>
            <div>
              <dt>P95 latency</dt>
              <dd>{latest.p95_latency_ms.toFixed(0)} ms</dd>
            </div>
            <div>
              <dt>Requests</dt>
              <dd>{latest.request_count.toLocaleString()}</dd>
            </div>
          </dl>
        )}
      </section>

      {isLoading && (
        <div className="loading" role="status">
          Loading health data...
        </div>
      )}
      {(servicesError || healthError) && (
        <div className="error-state" role="alert">
          Service telemetry could not be loaded.
        </div>
      )}
      {!selectedServiceId && !servicesError && (
        <div className="empty-state empty-state--panel">
          Select a service to view health metrics.
        </div>
      )}

      {selectedServiceId && chartData.length > 0 && (
        <div className="chart-grid">
          <MetricChart
            title="Request volume"
            description="Requests completed in each aggregation window; dashed line is the learned baseline."
            data={chartData}
            dataKey="request_count"
            baselineKey="baseline_request_count"
            color="#2dd4bf"
          />
          <MetricChart
            title="Error rate (%)"
            description="Share of ERROR and CRITICAL events; the incident rise is visible above baseline."
            data={chartData}
            dataKey="error_rate"
            baselineKey="baseline_error_rate"
            color="#fb7185"
          />
          <MetricChart
            title="P95 latency (ms)"
            description="Tail latency for the selected service, compared with its historical baseline."
            data={chartData}
            dataKey="p95_latency_ms"
            baselineKey="baseline_p95_latency_ms"
            color="#f59e0b"
          />
        </div>
      )}

      {selectedServiceId && !isLoading && !healthError && chartData.length === 0 && (
        <div className="empty-state empty-state--panel">
          No closed metric windows are available for this selection.
        </div>
      )}
    </div>
  );
}
