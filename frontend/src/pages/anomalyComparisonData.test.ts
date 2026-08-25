import { describe, expect, it } from "vitest";
import { buildComparisonData } from "./anomalyComparisonData";

describe("buildComparisonData", () => {
  it("interpolates both detectors onto a shared recall axis", () => {
    const points = buildComparisonData({
      mad: [
        { recall: 0.2, precision: 1 },
        { recall: 0.8, precision: 0.7 },
      ],
      isolation_forest: [
        { recall: 0.4, precision: 0.9 },
        { recall: 1, precision: 0.5 },
      ],
    });

    expect(points.map((point) => point.recall)).toEqual([0.2, 0.4, 0.8, 1]);
    expect(points.every((point) => Number.isFinite(point.mad_precision))).toBe(true);
    expect(points.every((point) => Number.isFinite(point.if_precision))).toBe(true);
    expect(points[1].mad_precision).toBeCloseTo(0.9);
    expect(points[2].if_precision).toBeCloseTo(0.6333, 3);
  });

  it("fails closed when either curve has no observations", () => {
    expect(buildComparisonData({ mad: [], isolation_forest: [] })).toEqual([]);
  });
});
