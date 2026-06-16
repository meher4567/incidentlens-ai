// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import IncidentDetail from "./IncidentDetail";

const briefingMarkdown = "# Incident Briefing\n\npayment-service root cause";

const { incidentsApiMock } = vi.hoisted(() => ({
  incidentsApiMock: {
    list: vi.fn(),
    get: vi.fn().mockResolvedValue({
      id: "incident-1",
      start_time: "2026-01-01T00:00:00Z",
      end_time: null,
      severity: "critical",
      affected_services: ["payment-service"],
      affected_service_names: ["payment-service"],
      alert_count: 1,
      closed_at: null,
      created_at: "2026-01-01T00:00:00Z",
      alerts: [],
      root_cause_scores: [
        {
          service_id: "payment-service-id",
          service_name: "payment-service",
          score: 0.87,
          rank: 1,
          feature_contributions: { metric_jump: 0.34 },
        },
      ],
      timeline: [
        {
          alert_id: "alert-1",
          service_name: "payment-service",
          anomaly_type: "latency_spike",
          start_window: "2026-01-01T00:00:00Z",
          severity: "critical",
        },
      ],
    }),
    briefing: vi.fn().mockResolvedValue({
      incident_id: "incident-1",
      title: "critical incident on payment-service",
      status: "active",
      severity: "critical",
      summary: "payment-service is the top RCA candidate with high confidence.",
      suspected_root_cause: {
        service_name: "payment-service",
        score: 0.87,
        confidence: "high",
        why: "Top contributing signals: metric jump.",
      },
      impact: {
        affected_services: ["payment-service"],
        alert_count: 1,
        duration_minutes: null,
        status: "active",
      },
      evidence: ["Earliest alert: payment-service latency_spike"],
      recommended_actions: ["Check payment-service deploys"],
      markdown: "# Incident Briefing\n\npayment-service root cause",
    }),
  },
}));

vi.mock("../api/client", () => ({
  incidentsApi: incidentsApiMock,
}));

function renderIncidentDetail() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/incidents/incident-1"]}>
        <Routes>
          <Route path="/incidents/:incidentId" element={<IncidentDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("IncidentDetail", () => {
  afterEach(() => {
    cleanup();
  });

  beforeEach(() => {
    vi.clearAllMocks();
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it("renders an operator briefing and copies the markdown handoff", async () => {
    renderIncidentDetail();

    expect(await screen.findByText("Incident Briefing")).toBeTruthy();
    expect(screen.getByText("payment-service is the top RCA candidate with high confidence.")).toBeTruthy();
    expect(screen.getByText("Check payment-service deploys")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(briefingMarkdown);
    });
    expect(await screen.findByText("Copied")).toBeTruthy();
  });

  it("shows markdown fallback when clipboard access is denied", async () => {
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockRejectedValue(new Error("denied")),
      },
    });
    renderIncidentDetail();

    expect(await screen.findByText("Incident Briefing")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));

    const fallback = await screen.findByLabelText("Incident briefing markdown");
    expect((fallback as HTMLTextAreaElement).value).toBe(briefingMarkdown);
    expect(screen.getByText("Clipboard access failed. Select the briefing text manually.")).toBeTruthy();
  });
});
