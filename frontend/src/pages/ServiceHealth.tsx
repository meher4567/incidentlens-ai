import React, { useState } from "react";
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
import { servicesApi } from "../api/client";

export default function ServiceHealth() {
  const { data: services } = useQuery({
    queryKey: ["services"],
    queryFn: servicesApi.list,
  });

  const [selectedServiceId, setSelectedServiceId] = useState<string>("");
  const [windowSize, setWindowSize] = useState(60);

  const { data: health, isLoading } = useQuery({
    queryKey: ["serviceHealth", selectedServiceId, windowSize],
    queryFn: () =>
      servicesApi.health(selectedServiceId, {
        window_size_seconds: String(windowSize),
        limit: "200",
      }),
    enabled: !!selectedServiceId,
  });

  const serviceList = Array.isArray(services) ? services : [];
  const windows = health?.windows ?? [];

  const chartData = windows.map((w: any) => ({
    time: new Date(w.window_start).toLocaleTimeString(),
    request_count: w.request_count,
    error_rate: w.error_rate ? Number(w.error_rate) * 100 : 0,
    p95_latency_ms: w.p95_latency_ms,
  }));

  return (
    <div>
      <h2 className="card-title" style={{ marginBottom: 24 }}>
        Service Health
      </h2>

      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <label>
            Service:{" "}
            <select
              value={selectedServiceId}
              onChange={(e) => setSelectedServiceId(e.target.value)}
              style={{
                padding: "6px 12px",
                background: "var(--color-bg)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
              }}
            >
              <option value="">Select a service</option>
              {serviceList.map((svc: any) => (
                <option key={svc.id} value={svc.id}>
                  {svc.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Window:{" "}
            <select
              value={windowSize}
              onChange={(e) => setWindowSize(Number(e.target.value))}
              style={{
                padding: "6px 12px",
                background: "var(--color-bg)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius)",
              }}
            >
              <option value={60}>1 minute</option>
              <option value={300}>5 minutes</option>
            </select>
          </label>
        </div>
      </div>

      {isLoading && <div className="loading">Loading health data...</div>}
      {!selectedServiceId && (
        <div className="empty-state">Select a service to view health metrics.</div>
      )}

      {selectedServiceId && chartData.length > 0 && (
        <>
          <div className="card" style={{ marginBottom: 16 }}>
            <h3 className="card-title">Request Count</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="time" stroke="var(--color-text-muted)" fontSize={11} />
                <YAxis stroke="var(--color-text-muted)" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius)",
                  }}
                />
                <Line type="monotone" dataKey="request_count" stroke="var(--color-primary)" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <h3 className="card-title">Error Rate (%)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="time" stroke="var(--color-text-muted)" fontSize={11} />
                <YAxis stroke="var(--color-text-muted)" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius)",
                  }}
                />
                <Line type="monotone" dataKey="error_rate" stroke="var(--color-danger)" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <h3 className="card-title">P95 Latency (ms)</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="time" stroke="var(--color-text-muted)" fontSize={11} />
                <YAxis stroke="var(--color-text-muted)" fontSize={11} />
                <Tooltip
                  contentStyle={{
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius)",
                  }}
                />
                <Line type="monotone" dataKey="p95_latency_ms" stroke="var(--color-warning)" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}