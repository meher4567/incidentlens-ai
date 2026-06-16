// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Overview from "./Overview";

vi.mock("../api/client", () => ({
  logsApi: {
    counts: vi.fn().mockResolvedValue({ total_logs: 1234 }),
  },
  incidentsApi: {
    list: vi.fn().mockResolvedValue([
      {
        id: "11111111-2222-3333-4444-555555555555",
        start_time: "2026-01-01T00:00:00Z",
        end_time: null,
        severity: "high",
        affected_services: ["checkout-service", "payment-service"],
        affected_service_names: ["checkout-service", "payment-service"],
        alert_count: 3,
        closed_at: null,
        created_at: "2026-01-01T00:00:00Z",
      },
    ]),
  },
  metricsApi: {
    overview: vi.fn().mockResolvedValue({
      total_logs: 1234,
      recent_events_per_min: 250,
      queue_depth: 0,
      recent_errors: 2,
      total_services: 6,
      active_incidents: 1,
    }),
  },
}));

function renderOverview() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Overview />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Overview", () => {
  it("renders pipeline health, incident, and ingestion summaries", async () => {
    renderOverview();

    expect(await screen.findByText("Caught up")).toBeTruthy();
    expect(await screen.findByText("1,234")).toBeTruthy();
    expect(await screen.findByText("checkout-service, payment-service")).toBeTruthy();
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getByText("6")).toBeTruthy();
  });
});
