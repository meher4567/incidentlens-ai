const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// Logs
export const logsApi = {
  ingestBatch: (events: unknown[]) =>
    apiFetch<{ ingested: number; errors: unknown[] }>("/api/logs/batch", {
      method: "POST",
      body: JSON.stringify({ events }),
    }),
  query: (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch<unknown[]>(`/api/logs?${qs}`);
  },
  counts: () => apiFetch<{ total_logs: number }>("/api/logs/counts"),
};

// Metrics overview
export const metricsApi = {
  overview: () => apiFetch<{
    recent_events_per_min: number;
    queue_depth: number;
    recent_errors: number;
    total_services: number;
  }>("/api/metrics"),
};

// Services
export const servicesApi = {
  list: () => apiFetch<Array<{ id: string; name: string; created_at: string }>>("/api/services"),
  health: (serviceId: string, params?: Record<string, string>) => {
    const qs = new URLSearchParams(params || {}).toString();
    return apiFetch<{
      service_id: string;
      service_name: string;
      windows: unknown[];
      window_size_seconds: number;
    }>(`/api/services/${serviceId}/health?${qs}`);
  },
  dependencies: () => apiFetch<unknown[]>("/api/services/dependencies"),
};

// Anomalies
export const anomaliesApi = {
  list: (params?: Record<string, string>) => {
    const qs = new URLSearchParams(params || {}).toString();
    return apiFetch<unknown[]>(`/api/anomalies?${qs}`);
  },
};

// Alerts
export const alertsApi = {
  list: (params?: Record<string, string>) => {
    const qs = new URLSearchParams(params || {}).toString();
    return apiFetch<unknown[]>(`/api/alerts?${qs}`);
  },
  get: (alertId: string) => apiFetch<unknown>(`/api/alerts/${alertId}`),
};

// Incidents
export const incidentsApi = {
  list: (params?: Record<string, string>) => {
    const qs = new URLSearchParams(params || {}).toString();
    return apiFetch<unknown[]>(`/api/incidents?${qs}`);
  },
  get: (incidentId: string) =>
    apiFetch<{
      id: string;
      start_time: string;
      end_time: string | null;
      severity: string;
      affected_services: string[];
      affected_service_names: string[];
      alert_count: number;
      closed_at: string | null;
      created_at: string;
      alerts: unknown[];
      root_cause_scores: unknown[];
      timeline: unknown[];
    }>(`/api/incidents/${incidentId}`),
};