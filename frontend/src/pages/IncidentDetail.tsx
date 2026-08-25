import React from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  incidentsApi,
  type IncidentBriefing,
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
  const [copyState, setCopyState] = React.useState<"idle" | "copied" | "failed">("idle");

  const { data: incidents, isLoading: listLoading, error: listError } = useQuery({
    queryKey: ["incidents"],
    queryFn: () => incidentsApi.list({ limit: "50" }),
    enabled: !incidentId,
  });

  const { data: incident, isLoading, error: incidentError } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => incidentsApi.get(incidentId!),
    enabled: !!incidentId,
  });

  const { data: briefing } = useQuery({
    queryKey: ["incident-briefing", incidentId],
    queryFn: () => incidentsApi.briefing(incidentId!),
    enabled: !!incidentId,
  });

  async function copyBriefingMarkdown(report: IncidentBriefing) {
    try {
      await navigator.clipboard.writeText(report.markdown);
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  }

  if (!incidentId) {
    const list = Array.isArray(incidents) ? incidents : [];
    return (
      <div>
        <div className="page-heading">
          <div>
            <span className="eyebrow">Correlated operations</span>
            <h2 className="page-title">Incidents</h2>
            <p className="page-description">Alert cascades grouped into operator-ready investigations.</p>
          </div>
          {!listLoading && <span className="status-chip">{list.length} detected</span>}
        </div>
        {listLoading && <div className="loading" role="status">Loading incidents...</div>}
        {listError && <div className="error-state" role="alert">Incidents could not be loaded.</div>}
        {list.length > 0 ? (
          <div className="table-wrapper card" tabIndex={0} aria-label="All incidents table">
            <table>
              <caption className="sr-only">All correlated incidents</caption>
              <thead>
                <tr>
                  <th scope="col">ID</th>
                  <th scope="col">Severity</th>
                  <th scope="col">Start</th>
                  <th scope="col">End</th>
                  <th scope="col">Services</th>
                  <th scope="col">Alerts</th>
                </tr>
              </thead>
              <tbody>
                {list.map((inc: IncidentSummary) => (
                  <tr key={inc.id}>
                    <td>
                      <Link className="text-link id-link" to={`/incidents/${inc.id}`} title={inc.id}>
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
        ) : !listLoading && !listError ? (
          <div className="empty-state empty-state--panel">No incidents detected yet.</div>
        ) : null}
      </div>
    );
  }

  if (isLoading) return <div className="loading">Loading incident...</div>;
  if (incidentError) return <div className="error-state" role="alert">Incident details could not be loaded.</div>;
  if (!incident) return <div className="empty-state">Incident not found.</div>;

  const inc: IncidentDetailData = incident;
  return (
    <div>
      <Link to="/incidents" className="back-link">
        <span aria-hidden="true">←</span> Back to incidents
      </Link>
      <div className="page-heading incident-heading">
        <div>
          <span className="eyebrow">Active investigation</span>
          <h2 className="page-title">Incident <code title={inc.id}>{inc.id.slice(0, 8)}</code></h2>
          <p className="page-description">Detected {formatDateTime(inc.start_time)}</p>
        </div>
        <span className={`badge badge-${inc.severity}`}>{inc.severity}</span>
      </div>
      <div className="grid grid-2 summary-grid">
        <div className="card">
          <span className="stat-label">Time Range</span>
          <span className="summary-value summary-value--small">
            {formatDateTime(inc.start_time)} - {inc.end_time ? formatDateTime(inc.end_time) : "Ongoing"}
          </span>
        </div>
        <div className="card">
          <span className="stat-label">Affected Services</span>
          <span className="summary-value summary-value--small">
            {inc.affected_service_names.join(", ")}
          </span>
        </div>
      </div>

      {briefing && (
        <section className="card incident-briefing section-card">
          <div className="briefing-header">
            <div>
              <span className="eyebrow">Operator handoff</span>
              <h3 className="card-title">Incident Briefing</h3>
            </div>
            <button
              className="button"
              type="button"
              onClick={() => void copyBriefingMarkdown(briefing)}
              aria-live="polite"
            >
              {copyState === "copied" ? "Copied" : "Copy Markdown"}
            </button>
          </div>

          {copyState === "failed" && (
            <div className="error-state error-state--compact">
              Clipboard access failed. Select the briefing text manually.
              <textarea
                className="markdown-fallback"
                readOnly
                value={briefing.markdown}
                aria-label="Incident briefing markdown"
              />
            </div>
          )}

          <p className="briefing-summary">{briefing.summary}</p>

          <div className="briefing-grid">
            <section className="briefing-panel">
              <span className="stat-label">Suspected root cause</span>
              <strong>{briefing.suspected_root_cause.service_name ?? "Pending RCA"}</strong>
              <small>
                {briefing.suspected_root_cause.confidence} confidence
                {briefing.suspected_root_cause.score !== null
                  ? ` - score ${briefing.suspected_root_cause.score.toFixed(3)}`
                  : ""}
              </small>
              <p>{briefing.suspected_root_cause.why}</p>
            </section>
            <section className="briefing-panel">
              <span className="stat-label">Impact</span>
              <strong>{briefing.impact.affected_services.length} services</strong>
              <small>{briefing.impact.alert_count} clustered alerts - {briefing.impact.status}</small>
              <p>{briefing.impact.affected_services.join(", ")}</p>
            </section>
          </div>

          <div className="briefing-grid">
            <section>
              <h4 className="section-title">Evidence</h4>
              <ul className="briefing-list">
                {briefing.evidence.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
            <section>
              <h4 className="section-title">Recommended Actions</h4>
              <ol className="briefing-list briefing-list--ordered">
                {briefing.recommended_actions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ol>
            </section>
          </div>
        </section>
      )}

      <section className="card section-card">
        <h3 className="card-title">Timeline</h3>
        {inc.timeline.length === 0 ? (
          <div className="empty-state">No timeline data.</div>
        ) : (
          <div className="timeline">
            {inc.timeline.map((event: TimelineEvent) => (
              <div key={event.alert_id} className="timeline-event">
                <div className="timeline-event__content">
                  <span className={`badge badge-${event.severity}`}>{event.severity}</span>
                  <strong>{event.service_name}</strong>
                  <span className="timeline-event__type">
                    {event.anomaly_type}
                  </span>
                  <time className="timeline-event__time" dateTime={event.start_window}>
                    {new Date(event.start_window).toLocaleTimeString()}
                  </time>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card section-card">
        <h3 className="card-title">Root Cause Ranking</h3>
        {inc.root_cause_scores.length === 0 ? (
          <div className="empty-state">No root cause scores computed yet.</div>
        ) : (
          <div className="table-wrapper" tabIndex={0} aria-label="Root cause ranking table">
            <table>
              <caption className="sr-only">Ranked root cause candidates and feature contributions</caption>
              <thead>
                <tr>
                  <th scope="col">Rank</th>
                  <th scope="col">Service</th>
                  <th scope="col">Score</th>
                  <th scope="col">Feature Contributions</th>
                </tr>
              </thead>
              <tbody>
                {inc.root_cause_scores.map((rc: RootCauseScore) => (
                  <tr key={rc.service_id}>
                    <td>#{rc.rank}</td>
                    <td><strong>{rc.service_name}</strong></td>
                    <td>{rc.score.toFixed(3)}</td>
                    <td className="feature-contributions">
                      {formatFeatureContributions(rc.feature_contributions)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
