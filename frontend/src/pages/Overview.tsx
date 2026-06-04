import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { logsApi, incidentsApi, metricsApi, type IncidentSummary } from "../api/client";

function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function serviceSummary(services: string[]): string {
  if (services.length === 0) {
    return "-";
  }
  return `${services.slice(0, 3).join(", ")}${services.length > 3 ? ` +${services.length - 3}` : ""}`;
}

export default function Overview() {
  const { data: logCounts, isLoading: logsLoading, error: logsError } = useQuery({
    queryKey: ["logCounts"],
    queryFn: logsApi.counts,
    refetchInterval: 15_000,
  });

  const { data: incidents, isLoading: incLoading } = useQuery({
    queryKey: ["incidents"],
    queryFn: () => incidentsApi.list({ limit: "10" }),
    refetchInterval: 15_000,
  });

  const { data: overview } = useQuery({
    queryKey: ["overview"],
    queryFn: () => metricsApi.overview(),
    refetchInterval: 15_000,
  });

  const incidentList = Array.isArray(incidents) ? incidents : [];
  const activeIncidentCount =
    overview?.active_incidents ?? incidentList.filter((incident) => !incident.closed_at).length;
  const impactedServiceCount = new Set(
    incidentList.flatMap((incident) => incident.affected_service_names ?? []),
  ).size;
  const mostRecentIncident = incidentList[0];
  const pipelineState =
    logsError ? "API unavailable" : overview?.queue_depth === 0 ? "Caught up" : "Processing backlog";

  return (
    <div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">Incident operations</span>
          <h2 className="page-title">Overview</h2>
        </div>
        <span className={`status-chip ${logsError ? "status-chip--danger" : "status-chip--success"}`}>
          {pipelineState}
        </span>
      </div>

      {logsLoading && <div className="loading">Loading metrics...</div>}
      {logsError && <div className="error-state">Failed to load overview data. Is the API running?</div>}

      <div className="signal-grid">
        <section className="signal-card signal-card--primary">
          <span className="signal-label">Active incidents</span>
          <strong>{activeIncidentCount}</strong>
          <small>{impactedServiceCount} impacted services</small>
        </section>
        <section className="signal-card">
          <span className="signal-label">Last incident</span>
          <strong>{mostRecentIncident ? mostRecentIncident.severity : "-"}</strong>
          <small>{mostRecentIncident ? formatDateTime(mostRecentIncident.start_time) : "No detected incident"}</small>
        </section>
        <section className="signal-card">
          <span className="signal-label">Ingestion rate</span>
          <strong>{overview?.recent_events_per_min ?? "-"}</strong>
          <small>events per minute</small>
        </section>
      </div>

      <div className="grid grid-4" style={{ marginBottom: 32 }}>
        <div className="card stat-tile">
          <span className="stat-value">
            {logCounts?.total_logs?.toLocaleString() ?? "-"}
          </span>
          <span className="stat-label">Total Logs Ingested</span>
        </div>
        <div className="card stat-tile">
          <span className="stat-value">
            {overview?.recent_events_per_min ?? "-"}
          </span>
          <span className="stat-label">Ingestion Rate (events/min)</span>
        </div>
        <div className="card stat-tile">
          <span className="stat-value">
            {overview?.queue_depth ?? "-"}
          </span>
          <span className="stat-label">Queue Depth</span>
        </div>
        <div className="card stat-tile">
          <span className="stat-value">
            {overview?.recent_errors ?? "-"}
          </span>
          <span className="stat-label">Recent Errors</span>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 24 }}>
        <div className="card stat-tile">
          <span className="stat-value">
            {activeIncidentCount}
          </span>
          <span className="stat-label">Active Incidents</span>
        </div>
        <div className="card stat-tile">
          <span className="stat-value">
            {overview?.total_services ?? "-"}
          </span>
          <span className="stat-label">Monitored Services</span>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 className="card-title">Recent Incidents</h3>
        {incLoading && <div className="loading">Loading incidents...</div>}
        {incidentList.length === 0 && !incLoading ? (
          <div className="empty-state">
            No incidents detected yet. Run the pipeline to see results.
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Severity</th>
                  <th>Start Time</th>
                  <th>Affected Services</th>
                  <th>Alert Count</th>
                </tr>
              </thead>
              <tbody>
                {incidentList.map((inc: IncidentSummary) => (
                  <tr key={inc.id}>
                    <td>
                      <Link to={`/incidents/${inc.id}`} style={{ color: "var(--color-primary)" }}>
                        {inc.id?.slice(0, 8)}...
                      </Link>
                    </td>
                    <td>
                      <span className={`badge badge-${inc.severity}`}>
                        {inc.severity}
                      </span>
                    </td>
                    <td>{formatDateTime(inc.start_time)}</td>
                    <td>{serviceSummary(inc.affected_service_names || [])}</td>
                    <td>{inc.alert_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
