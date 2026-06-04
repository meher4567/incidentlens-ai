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
      "http://localhost:8000/api/logs/batch",
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
});
