import {
  demoIncidentDetail,
  demoIncidentBriefing,
  demoIncidents,
  demoOverviewMetrics,
  demoPrCurves,
  demoServiceHealth,
  demoServices,
} from "./demoData";

const BASE_URL = import.meta.env.VITE_API_URL ?? "";
const USE_DEMO_DATA = import.meta.env.VITE_DEMO_MODE === "true";

export interface LogCounts {
  total_logs: number;
}

export interface OverviewMetrics {
  total_logs: number;
  recent_events_per_min: number;
  queue_depth: number;
  recent_errors: number;
  total_services: number;
  active_incidents: number;
}

export interface ServiceSummary {
  id: string;
  name: string;
  created_at: string;
}

export interface ServiceDependency {
  upstream_id: string;
  downstream_id: string;
  upstream_name: string | null;
  downstream_name: string | null;
}

export interface MetricWindow {
  service_id: string;
  service_name?: string;
  window_start: string;
  window_size_seconds: number;
  request_count: number;
  error_count: number;
  error_rate: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  unique_messages: number;
  baseline_request_count?: number | null;
  baseline_error_rate?: number | null;
  baseline_p95_latency_ms?: number | null;
}

export interface ServiceHealthResponse {
  service_id: string;
  service_name: string;
  windows: MetricWindow[];
  window_size_seconds: number;
}

export interface IncidentSummary {
  id: string;
  start_time: string;
  end_time: string | null;
  severity: string;
  affected_services: string[];
  affected_service_names: string[];
  alert_count: number;
  closed_at: string | null;
  created_at: string;
}

export interface IncidentAlert {
  id: string;
  service_id: string;
  service_name: string;
  anomaly_type: string;
  start_window: string;
  end_window: string;
  severity: string;
  observed_value: number;
  baseline_value: number;
}

export interface RootCauseScore {
  service_id: string;
  service_name: string;
  score: number;
  rank: number;
  feature_vector?: Record<string, unknown> | null;
  feature_contributions?: Record<string, number> | null;
}

export interface TimelineEvent {
  alert_id: string;
  service_name: string;
  anomaly_type: string;
  start_window: string;
  severity: string;
}

export interface IncidentDetail extends IncidentSummary {
  alerts: IncidentAlert[];
  root_cause_scores: RootCauseScore[];
  timeline: TimelineEvent[];
}

export interface IncidentImpact {
  affected_services: string[];
  alert_count: number;
  duration_minutes: number | null;
  status: string;
}

export interface SuspectedRootCause {
  service_name: string | null;
  score: number | null;
  confidence: string;
  why: string;
}

export interface IncidentBriefing {
  incident_id: string;
  title: string;
  status: string;
  severity: string;
  summary: string;
  suspected_root_cause: SuspectedRootCause;
  impact: IncidentImpact;
  evidence: string[];
  recommended_actions: string[];
  markdown: string;
}

export interface PRPoint {
  precision: number;
  recall: number;
}

export interface PRCurveResponse {
  mad: PRPoint[];
  isolation_forest: PRPoint[];
  summary?: {
    mad?: { precision: number; recall: number; f1: number };
    isolation_forest?: { precision: number; recall: number; f1: number };
  };
}

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
  counts: () =>
    USE_DEMO_DATA
      ? Promise.resolve({ total_logs: demoOverviewMetrics().total_logs })
      : apiFetch<LogCounts>("/api/logs/counts"),
};

// Metrics overview
export const metricsApi = {
  overview: () =>
    USE_DEMO_DATA
      ? Promise.resolve(demoOverviewMetrics())
      : apiFetch<OverviewMetrics>("/api/metrics"),
  prCurves: () =>
    USE_DEMO_DATA ? Promise.resolve(demoPrCurves()) : apiFetch<PRCurveResponse>("/api/metrics/pr-curves"),
};

// Services
export const servicesApi = {
  list: () =>
    USE_DEMO_DATA ? Promise.resolve(demoServices()) : apiFetch<ServiceSummary[]>("/api/services"),
  health: (serviceId: string, params?: Record<string, string>) => {
    const qs = new URLSearchParams(params || {}).toString();
    return USE_DEMO_DATA
      ? Promise.resolve(demoServiceHealth(serviceId))
      : apiFetch<ServiceHealthResponse>(`/api/services/${serviceId}/health?${qs}`);
  },
  dependencies: () => apiFetch<ServiceDependency[]>("/api/services/dependencies"),
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
    return USE_DEMO_DATA ? Promise.resolve(demoIncidents()) : apiFetch<IncidentSummary[]>(`/api/incidents?${qs}`);
  },
  get: (incidentId: string) =>
    USE_DEMO_DATA
      ? Promise.resolve(demoIncidentDetail(incidentId))
      : apiFetch<IncidentDetail>(`/api/incidents/${incidentId}`),
  briefing: (incidentId: string) =>
    USE_DEMO_DATA
      ? Promise.resolve(demoIncidentBriefing(incidentId))
      : apiFetch<IncidentBriefing>(`/api/incidents/${incidentId}/briefing`),
};
