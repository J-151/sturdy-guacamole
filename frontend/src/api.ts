import type { DayAheadAccuracy, DecisionView, HorizonAccuracy, HorizonRow, Meta } from "./types";

/** GET /api/... and return parsed JSON. Surfaces the backend's error message when there is one. */
async function get<T>(path: string, params: Record<string, string | number> = {}): Promise<T> {
  const query = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const url = `/api${path}${query.toString() ? `?${query}` : ""}`;
  const res = await fetch(url);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* response was not JSON - keep the status text */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => get<Meta>("/meta"),
  decision: (date: string, decisionTime: string, daysBefore: number) =>
    get<DecisionView>("/decision", { date, decision_time: decisionTime, days_before: daysBefore }),
  dayAhead: (decisionTime: string, daysBefore: number) =>
    get<DayAheadAccuracy>("/accuracy/day-ahead", { decision_time: decisionTime, days_before: daysBefore }),
  horizon: (horizonHours: number, start: string, end: string) =>
    get<HorizonAccuracy>("/accuracy/horizon", { horizon_hours: horizonHours, start, end }),
  byHorizon: (start: string, end: string) => get<{ rows: HorizonRow[] }>("/accuracy/by-horizon", { start, end }),
};
