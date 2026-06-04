import type {
  IncidentDetail,
  IncidentSummary,
  OverviewMetrics,
  PRCurveResponse,
  ServiceHealthResponse,
  ServiceSummary,
} from "./client";

const SERVICE_IDS = {
  apiGateway: "9ff7b8c7-67f1-4f22-83d8-4045d8a2b001",
  checkout: "9ff7b8c7-67f1-4f22-83d8-4045d8a2b002",
  payment: "9ff7b8c7-67f1-4f22-83d8-4045d8a2b003",
  inventory: "9ff7b8c7-67f1-4f22-83d8-4045d8a2b004",
  auth: "9ff7b8c7-67f1-4f22-83d8-4045d8a2b005",
  notification: "9ff7b8c7-67f1-4f22-83d8-4045d8a2b006",
};

const INCIDENT_ID = "3d91f6e2-7b59-4f43-8ef8-f4b7cdd45a01";

function isoMinutesAgo(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString();
}

function service(id: string, name: string): ServiceSummary {
  return { id, name, created_at: isoMinutesAgo(240) };
}

export function demoServices(): ServiceSummary[] {
  return [
    service(SERVICE_IDS.apiGateway, "api-gateway"),
    service(SERVICE_IDS.auth, "auth-service"),
    service(SERVICE_IDS.checkout, "checkout-service"),
    service(SERVICE_IDS.inventory, "inventory-service"),
    service(SERVICE_IDS.notification, "notification-service"),
    service(SERVICE_IDS.payment, "payment-service"),
  ];
}

export function demoOverviewMetrics(): OverviewMetrics {
  return {
    total_logs: 100_000,
    recent_events_per_min: 746.4,
    queue_depth: 0,
    recent_errors: 27,
    total_services: 6,
    active_incidents: 1,
  };
}

export function demoIncidents(): IncidentSummary[] {
  return [
    {
      id: INCIDENT_ID,
      start_time: isoMinutesAgo(18),
      end_time: null,
      severity: "critical",
      affected_services: [
        SERVICE_IDS.checkout,
        SERVICE_IDS.payment,
        SERVICE_IDS.inventory,
      ],
      affected_service_names: [
        "checkout-service",
        "payment-service",
        "inventory-service",
      ],
      alert_count: 7,
      closed_at: null,
      created_at: isoMinutesAgo(16),
    },
    {
      id: "2f8f4e89-1e91-4388-87bb-63dbf8378c02",
      start_time: isoMinutesAgo(74),
      end_time: isoMinutesAgo(63),
      severity: "high",
      affected_services: [SERVICE_IDS.auth, SERVICE_IDS.apiGateway],
      affected_service_names: ["auth-service", "api-gateway"],
      alert_count: 3,
      closed_at: isoMinutesAgo(62),
      created_at: isoMinutesAgo(72),
    },
  ];
}

export function demoIncidentDetail(incidentId: string): IncidentDetail {
  const incident = demoIncidents().find((item) => item.id === incidentId) ?? demoIncidents()[0];

  return {
    ...incident,
    alerts: [
      {
        id: "82f0f0be-7f5a-409a-9b10-3797d149bf01",
        service_id: SERVICE_IDS.payment,
        service_name: "payment-service",
        anomaly_type: "latency_spike",
        start_window: isoMinutesAgo(18),
        end_window: isoMinutesAgo(17),
        severity: "critical",
        observed_value: 1482,
        baseline_value: 214,
      },
      {
        id: "82f0f0be-7f5a-409a-9b10-3797d149bf02",
        service_id: SERVICE_IDS.checkout,
        service_name: "checkout-service",
        anomaly_type: "error_rate_spike",
        start_window: isoMinutesAgo(16),
        end_window: isoMinutesAgo(15),
        severity: "high",
        observed_value: 0.181,
        baseline_value: 0.014,
      },
    ],
    root_cause_scores: [
      {
        service_id: SERVICE_IDS.payment,
        service_name: "payment-service",
        score: 0.871,
        rank: 1,
        feature_vector: {
          is_earliest: 1,
          blast_radius: 2,
          metric_jump_magnitude: 6.8,
        },
        feature_contributions: {
          earliest_signal: 0.31,
          blast_radius: 0.22,
          metric_jump: 0.34,
        },
      },
      {
        service_id: SERVICE_IDS.checkout,
        service_name: "checkout-service",
        score: 0.642,
        rank: 2,
        feature_vector: {
          is_earliest: 0,
          blast_radius: 3,
          metric_jump_magnitude: 4.9,
        },
        feature_contributions: {
          earliest_signal: 0.08,
          blast_radius: 0.28,
          metric_jump: 0.21,
        },
      },
    ],
    timeline: [
      {
        alert_id: "82f0f0be-7f5a-409a-9b10-3797d149bf01",
        service_name: "payment-service",
        anomaly_type: "latency_spike",
        start_window: isoMinutesAgo(18),
        severity: "critical",
      },
      {
        alert_id: "82f0f0be-7f5a-409a-9b10-3797d149bf02",
        service_name: "checkout-service",
        anomaly_type: "error_rate_spike",
        start_window: isoMinutesAgo(16),
        severity: "high",
      },
    ],
  };
}

export function demoServiceHealth(serviceId: string): ServiceHealthResponse {
  const selected = demoServices().find((item) => item.id === serviceId) ?? demoServices()[0];
  const windows = Array.from({ length: 32 }, (_, index) => {
    const minutesAgo = 31 - index;
    const incidentPressure = index > 20 ? index - 20 : 0;
    return {
      service_id: selected.id,
      service_name: selected.name,
      window_start: isoMinutesAgo(minutesAgo),
      window_size_seconds: 60,
      request_count: 760 + Math.round(Math.sin(index / 3) * 45),
      error_count: Math.max(1, Math.round(incidentPressure * 2.2)),
      error_rate: Number((0.012 + incidentPressure * 0.011).toFixed(3)),
      p50_latency_ms: 96 + incidentPressure * 12,
      p95_latency_ms: 226 + incidentPressure * 93,
      unique_messages: 18 + Math.round(incidentPressure / 2),
      baseline_request_count: 740,
      baseline_error_rate: 0.014,
      baseline_p95_latency_ms: 218,
    };
  });

  return {
    service_id: selected.id,
    service_name: selected.name,
    windows,
    window_size_seconds: 60,
  };
}

export function demoPrCurves(): PRCurveResponse {
  return {
    mad: [
      { recall: 0.22, precision: 0.98 },
      { recall: 0.46, precision: 0.93 },
      { recall: 0.68, precision: 0.88 },
      { recall: 0.84, precision: 0.81 },
      { recall: 0.93, precision: 0.72 },
    ],
    isolation_forest: [
      { recall: 0.28, precision: 0.89 },
      { recall: 0.52, precision: 0.84 },
      { recall: 0.73, precision: 0.77 },
      { recall: 0.89, precision: 0.68 },
      { recall: 0.97, precision: 0.55 },
    ],
    summary: {
      mad: { precision: 0.842, recall: 0.884, f1: 0.862 },
      isolation_forest: { precision: 0.713, recall: 0.912, f1: 0.801 },
    },
  };
}
