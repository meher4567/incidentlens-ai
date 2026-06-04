import React from "react";
import { useQuery } from "@tanstack/react-query";
import { logsApi, incidentsApi, metricsApi, alertsApi } from "../api/client";

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

  return (
    <div>
      <h2 className="card-title" style={{ marginBottom: 24 }}>
        Overview
      </h2>

      {logsLoading && <div className="loading">Loading metrics...</div>}
      {logsError && <div className="error-state">Failed to load overview data. Is the API running?</div>}

      <div className="grid grid-4" style={{ marginBottom: 32 }}>
        <div className="card stat-tile">
          <span className="stat-value">
            {logCounts?.total_logs?.toLocaleString() ?? "\u2014"}
          </span>
          <span className="stat-label">Total Logs Ingested</span>
        </div>
        <div className="card stat-tile">
          <span className="stat-value">
            {overview?.recent_events_per_min ?? "\u2014"}
          </span>
          <span className="stat-label">Ingestion Rate (events/min)</span>
        </div>
        <div className="card stat-tile">
          <span className="stat-value">
            {overview?.queue_depth ?? "\u2014"}
          </span>
          <span className="stat-label">Queue Depth</span>
        </div>
        <div className="card stat-tile">
          <span className="stat-value">
            {overview?.recent_errors ?? "\u2014"}
          </span>
          <span className="stat-label">Recent Errors</span>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginBottom: 24 }}>
        <div className="card stat-tile">
          <span className="stat-value">
            {incidentList.length}
          </span>
          <span className="stat-label">Active Incidents</span>
        </div>
        <div className="card stat-tile">
          <span className="stat-value">
            {overview?.total_services ?? "\u2014"}
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
                {incidentList.map((inc: any) => (
                  <tr key={inc.id}>
                    <td>
                      <a href={`/incidents/${inc.id}`} style={{ color: "var(--color-primary)" }}>
                        {inc.id?.slice(0, 8)}...
                      </a>
                    </td>
                    <td>
                      <span className={`badge badge-${inc.severity}`}>
                        {inc.severity}
                      </span>
                    </td>
                    <td>{inc.start_time ? new Date(inc.start_time).toLocaleString() : "\u2014"}</td>
                    <td>
                      {(inc.affected_service_names || []).slice(0, 3).join(", ")}
                      {(inc.affected_service_names || []).length > 3
                        ? ` +${inc.affected_service_names.length - 3}`
                        : ""}
                    </td>
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