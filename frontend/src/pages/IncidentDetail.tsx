import React from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  incidentsApi,
  type IncidentDetail as IncidentDetailData,
  type IncidentSummary,
  type RootCauseScore,
  type TimelineEvent,
} from "../api/client";

function formatDateTime(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "-";
}

function formatFeatureContributions(contributions?: Record<string, number> | null): string {
  if (!contributions || Object.keys(contributions).length === 0) {
    return "-";
  }

  return Object.entries(contributions)
    .sort(([, left], [, right]) => Math.abs(right) - Math.abs(left))
    .map(([name, value]) => `${name.replace(/_/g, " ")}: ${value.toFixed(2)}`)
    .join(", ");
}

export default function IncidentDetail() {
  const { incidentId } = useParams<{ incidentId: string }>();

  const { data: incidents } = useQuery({
    queryKey: ["incidents"],
    queryFn: () => incidentsApi.list({ limit: "50" }),
    enabled: !incidentId,
  });

  const { data: incident, isLoading } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => incidentsApi.get(incidentId!),
    enabled: !!incidentId,
  });

  if (!incidentId) {
    const list = Array.isArray(incidents) ? incidents : [];
    return (
      <div>
        <h2 className="card-title" style={{ marginBottom: 24 }}>Incidents</h2>
        {list.length === 0 ? (
          <div className="empty-state">No incidents detected yet.</div>
        ) : (
          <div className="table-wrapper card">
            <table>
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Severity</th>
                  <th>Start</th>
                  <th>End</th>
                  <th>Services</th>
                  <th>Alerts</th>
                </tr>
              </thead>
              <tbody>
                {list.map((inc: IncidentSummary) => (
                  <tr key={inc.id}>
                    <td>
                      <Link to={`/incidents/${inc.id}`} style={{ color: "var(--color-primary)" }}>
                        {inc.id.slice(0, 8)}...
                      </Link>
                    </td>
                    <td><span className={`badge badge-${inc.severity}`}>{inc.severity}</span></td>
                    <td>{formatDateTime(inc.start_time)}</td>
                    <td>{inc.end_time ? formatDateTime(inc.end_time) : "Ongoing"}</td>
                    <td>{inc.affected_service_names.join(", ")}</td>
                    <td>{inc.alert_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  if (isLoading) return <div className="loading">Loading incident...</div>;
  if (!incident) return <div className="empty-state">Incident not found.</div>;

  const inc: IncidentDetailData = incident;
  return (
    <div>
      <Link to="/incidents" style={{ color: "var(--color-text-muted)", fontSize: "0.875rem" }}>
        Back to incidents
      </Link>
      <h2 className="card-title" style={{ margin: "16px 0" }}>
        Incident <code style={{ fontSize: "0.75rem" }}>{inc.id}</code>
      </h2>
      <div className="grid grid-3" style={{ marginBottom: 24 }}>
        <div className="card">
          <span className="stat-label">Severity</span>
          <span className={`badge badge-${inc.severity}`} style={{ display: "block", marginTop: 4 }}>
            {inc.severity}
          </span>
        </div>
        <div className="card">
          <span className="stat-label">Time Range</span>
          <span style={{ fontSize: "0.875rem", display: "block", marginTop: 4 }}>
            {formatDateTime(inc.start_time)} - {inc.end_time ? formatDateTime(inc.end_time) : "Ongoing"}
          </span>
        </div>
        <div className="card">
          <span className="stat-label">Affected Services</span>
          <span style={{ fontSize: "0.875rem", display: "block", marginTop: 4 }}>
            {inc.affected_service_names.join(", ")}
          </span>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 className="card-title">Timeline</h3>
        {inc.timeline.length === 0 ? (
          <div className="empty-state">No timeline data.</div>
        ) : (
          <div style={{ borderLeft: "2px solid var(--color-border)", paddingLeft: 16 }}>
            {inc.timeline.map((event: TimelineEvent) => (
              <div
                key={event.alert_id}
                style={{
                  marginBottom: 12,
                  padding: "8px 12px",
                  background: "var(--color-bg)",
                  borderRadius: "var(--radius)",
                }}
              >
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span className={`badge badge-${event.severity}`}>{event.severity}</span>
                  <strong>{event.service_name}</strong>
                  <span style={{ color: "var(--color-text-muted)", fontSize: "0.75rem" }}>
                    {event.anomaly_type}
                  </span>
                  <span style={{ marginLeft: "auto", color: "var(--color-text-muted)", fontSize: "0.75rem" }}>
                    {new Date(event.start_window).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3 className="card-title">Root Cause Ranking</h3>
        {inc.root_cause_scores.length === 0 ? (
          <div className="empty-state">No root cause scores computed yet.</div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Service</th>
                  <th>Score</th>
                  <th>Feature Contributions</th>
                </tr>
              </thead>
              <tbody>
                {inc.root_cause_scores.map((rc: RootCauseScore) => (
                  <tr key={rc.service_id}>
                    <td>#{rc.rank}</td>
                    <td><strong>{rc.service_name}</strong></td>
                    <td>{rc.score.toFixed(3)}</td>
                    <td style={{ fontSize: "0.75rem", color: "var(--color-text-muted)" }}>
                      {formatFeatureContributions(rc.feature_contributions)}
                    </td>
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
