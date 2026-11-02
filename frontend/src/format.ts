const nf0 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 1 });

export const mw = (v: number | null | undefined): string => (v == null ? "n/a" : `${nf0.format(v)} MW`);
export const gw = (v: number | null | undefined): string => (v == null ? "n/a" : `${nf1.format(v / 1000)} GW`);
export const mwh = (v: number | null | undefined): string => (v == null ? "n/a" : `${nf0.format(v)} MWh`);
export const gwh = (v: number | null | undefined): string => (v == null ? "n/a" : `${nf1.format(v / 1000)} GWh`);
export const pct = (v: number | null | undefined): string => (v == null ? "n/a" : `${nf1.format(v)}%`);
export const hours = (v: number | null | undefined): string => (v == null ? "n/a" : `${nf1.format(v)} h`);
export const signed = (v: number | null | undefined): string =>
  v == null ? "n/a" : `${v > 0 ? "+" : ""}${nf0.format(v)} MW`;

/** "2026-01-14T09:00:00Z" -> "14 Jan, 09:00" (UK time; identical to UTC in January) */
export function dayTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/London",
  }).format(d);
}

export function clock(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/London" }).format(new Date(iso));
}

export function shortDate(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "Europe/London" }).format(new Date(iso));
}

/** Keep a YYYY-MM-DD string inside [min, max]. Browsers do not enforce <input min/max> for typed dates. */
export function clampDate(value: string, min: string, max: string): string {
  return value < min ? min : value > max ? max : value;
}
