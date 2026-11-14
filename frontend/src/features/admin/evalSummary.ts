/** Typed views over the free-form `summary` JSON stored with each evaluation run. */
import type { EvalRunDetail } from '@/api/types';

export interface CurvePoint {
  threshold: number;
  pass_rate: number;
  false_validation_rate: number;
}

export interface LowConfidenceItem {
  id: string;
  why: string;
  confidence: number;
  kind: string;
  topic: string;
  question: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

export function thresholdCurve(run: EvalRunDetail | undefined): CurvePoint[] {
  const curve = isRecord(run?.summary) ? run.summary.threshold_curve : undefined;
  if (!Array.isArray(curve)) return [];
  return curve.filter(
    (p): p is CurvePoint =>
      isRecord(p) &&
      typeof p.threshold === 'number' &&
      typeof p.pass_rate === 'number' &&
      typeof p.false_validation_rate === 'number',
  );
}

export function lowConfidence(run: EvalRunDetail | undefined): LowConfidenceItem[] {
  const items = isRecord(run?.summary) ? run.summary.low_confidence : undefined;
  if (!Array.isArray(items)) return [];
  return items.filter((i): i is LowConfidenceItem => isRecord(i) && typeof i.question === 'string');
}

export function scoreOf(
  scorecard: Record<string, unknown> | null | undefined,
  key: string,
): number | null {
  const value = scorecard?.[key];
  return typeof value === 'number' ? value : null;
}

/** The curve point nearest to `threshold` (the sweep is in 0.05 steps). */
export function nearestPoint(curve: CurvePoint[], threshold: number): CurvePoint | null {
  let best: CurvePoint | null = null;
  for (const point of curve) {
    if (!best || Math.abs(point.threshold - threshold) < Math.abs(best.threshold - threshold)) {
      best = point;
    }
  }
  return best;
}

export function summaryWeights(run: EvalRunDetail | undefined): number[] | null {
  const config = isRecord(run?.summary) ? run.summary.config : undefined;
  const weights = isRecord(config) ? config.weights : undefined;
  return Array.isArray(weights) && weights.every((w) => typeof w === 'number') ? weights : null;
}
