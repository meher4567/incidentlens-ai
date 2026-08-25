import type { PRCurveResponse } from "../api/client";

export type ComparisonPoint = {
  recall: number;
  mad_precision: number;
  if_precision: number;
};

function interpolatePrecision(
  points: Array<{ recall: number; precision: number }>,
  recall: number,
): number {
  const ordered = [...points].sort((left, right) => left.recall - right.recall);
  if (recall <= ordered[0].recall) return ordered[0].precision;
  if (recall >= ordered[ordered.length - 1].recall) return ordered[ordered.length - 1].precision;

  const upperIndex = ordered.findIndex((point) => point.recall >= recall);
  const lower = ordered[upperIndex - 1];
  const upper = ordered[upperIndex];
  const ratio = (recall - lower.recall) / (upper.recall - lower.recall);
  return lower.precision + ratio * (upper.precision - lower.precision);
}

export function buildComparisonData(prData?: PRCurveResponse): ComparisonPoint[] {
  if (!prData || prData.mad.length === 0 || prData.isolation_forest.length === 0) return [];
  const recalls = new Set([
    ...prData.mad.map((point) => point.recall),
    ...prData.isolation_forest.map((point) => point.recall),
  ]);
  return Array.from(recalls)
    .sort((left, right) => left - right)
    .map((recall) => ({
      recall,
      mad_precision: interpolatePrecision(prData.mad, recall),
      if_precision: interpolatePrecision(prData.isolation_forest, recall),
    }));
}
