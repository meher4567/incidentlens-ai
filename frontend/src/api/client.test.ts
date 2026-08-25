import { afterEach, describe, expect, it, vi } from "vitest";
import { incidentsApi, logsApi } from "./client";

const originalFetch = globalThis.fetch;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  globalThis.fetch = originalFetch;
});

describe("api client", () => {
  it("posts log batches to the backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(jsonResponse({ ingested: 1, errors: [] }, 201));

    const result = await logsApi.ingestBatch([{ service: "api-gateway" }]);

    expect(result).toEqual({ ingested: 1, errors: [] });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/logs/batch",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ events: [{ service: "api-gateway" }] }),
      }),
    );
  });

  it("raises backend error details", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Incident not found" }, 404));

    await expect(incidentsApi.get("missing")).rejects.toThrow("Incident not found");
  });

  it("fetches operator incident briefings", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(
      jsonResponse({
        incident_id: "incident-1",
        title: "Critical incident on payment-service",
        status: "active",
        severity: "critical",
        summary: "payment-service is the top RCA candidate",
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
        markdown: "# Incident Briefing",
      }),
    );

    const result = await incidentsApi.briefing("incident-1");

    expect(result.suspected_root_cause.service_name).toBe("payment-service");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/incidents/incident-1/briefing",
      expect.objectContaining({
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
      }),
    );
  });
});
