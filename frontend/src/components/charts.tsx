import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { clock, dayTime, shortDate } from "../format";
import { COLORS } from "../theme";
import type { DailyStat, HistogramBin, HourStat, HorizonRow, LevelStat, Period } from "../types";

const axis = { fontSize: 12, fill: COLORS.muted };
const gwTick = (v: number) => `${Math.round(v / 100) / 10}`;
const fmt = (v: unknown, digits = 0) =>
  typeof v === "number" ? v.toLocaleString("en-GB", { maximumFractionDigits: digits }) : "n/a";

/** Coerce anything numeric-looking to a number, everything else to null (so charts never get strings/NaN). */
const num = (v: unknown): number | null => {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** True when a series has many gaps: lines would be broken, so we also draw small dots. */
const isSparse = (values: (number | null)[]): boolean => {
  const present = values.filter((v) => v != null).length;
  return present > 0 && present < values.length * 0.9;
};

/** Tick positions every `stepHours`, aligned to whole hours. */
function timeTicks(min: number, max: number, stepHours: number): number[] {
  const step = stepHours * 3600_000;
  const out: number[] = [];
  for (let t = Math.ceil(min / step) * step; t <= max; t += step) out.push(t);
  return out;
}

// ---------------------------------------------------------------------------
// 1. Day-ahead decision chart: forecast (+ uncertainty band) with optional hindsight line
// ---------------------------------------------------------------------------
export function DecisionChart({ periods, showActual, showBand }: { periods: Period[]; showActual: boolean; showBand: boolean }) {
  const data = periods.map((p) => {
    const lo = num(p.band_low_mw);
    const hi = num(p.band_high_mw);
    return {
      ts: new Date(p.t).getTime(),
      forecast: num(p.forecast_mw),
      actual: showActual ? num(p.actual_mw) : null,
      bandLow: showBand ? lo : null,
      bandRange: showBand && lo != null && hi != null ? hi - lo : null,
      publish: p.publish_time,
      lead: p.lead_hours,
      error: p.error_mw,
      lo,
      hi,
    };
  });
  const ts = data.map((d) => d.ts);
  const ticks = timeTicks(Math.min(...ts), Math.max(...ts), 3);
  const sparseForecast = isSparse(data.map((d) => d.forecast));
  const sparseActual = isSparse(data.map((d) => d.actual));

  return (
    <ResponsiveContainer width="100%" height={380}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="ts" type="number" scale="time" domain={["dataMin", "dataMax"]} ticks={ticks} tickFormatter={(v: number) => clock(new Date(v).toISOString())} tick={axis} />
        <YAxis domain={[0, "auto"]} tickFormatter={gwTick} tick={axis} width={44} label={{ value: "GW", angle: -90, position: "insideLeft", fill: COLORS.muted, fontSize: 12 }} />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload as (typeof data)[number];
            return (
              <div className="tooltip">
                <b>{clock(new Date(d.ts).toISOString())}</b>
                <div>Forecast: {fmt(d.forecast)} MW</div>
                {d.lo != null && d.hi != null && (
                  <div>
                    Likely range: {fmt(d.lo)} to {fmt(d.hi)} MW
                  </div>
                )}
                {d.actual != null && <div>Actual: {fmt(d.actual)} MW</div>}
                {d.actual != null && d.error != null && <div>Error: {d.error > 0 ? "+" : ""}{fmt(d.error)} MW</div>}
                <div className="muted">
                  Forecast issued {dayTime(d.publish)} ({fmt(d.lead, 1)} h ahead)
                </div>
              </div>
            );
          }}
        />
        <Legend verticalAlign="top" height={32} />
        {showBand && <Area dataKey="bandLow" stackId="band" stroke="none" fill="transparent" legendType="none" connectNulls isAnimationActive={false} />}
        {showBand && <Area dataKey="bandRange" stackId="band" stroke="none" fill={COLORS.band} fillOpacity={0.16} name="Likely range (P10-P90)" connectNulls isAnimationActive={false} />}
        <Line dataKey="forecast" name="Forecast available at decision time" stroke={COLORS.forecast} strokeWidth={2.5} dot={sparseForecast ? { r: 3 } : false} connectNulls isAnimationActive={false} />
        {showActual && <Line dataKey="actual" name="Actual (hindsight)" stroke={COLORS.actual} strokeWidth={2} strokeDasharray="5 4" dot={sparseActual ? { r: 2.5 } : false} connectNulls isAnimationActive={false} />}
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// 2. Long actual-vs-forecast series (accuracy tab)
// ---------------------------------------------------------------------------
export function SeriesChart({ series }: { series: Period[] }) {
  const data = series.map((p) => ({ ts: new Date(p.t).getTime(), forecast: num(p.forecast_mw), actual: num(p.actual_mw) }));
  const ts = data.map((d) => d.ts);
  const spanDays = (Math.max(...ts) - Math.min(...ts)) / 86400_000;
  const ticks = timeTicks(Math.min(...ts), Math.max(...ts), spanDays > 14 ? 24 * 4 : spanDays > 4 ? 24 : 6);
  const sparseForecast = isSparse(data.map((d) => d.forecast));
  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="ts" type="number" scale="time" domain={["dataMin", "dataMax"]} ticks={ticks} tickFormatter={(v: number) => shortDate(new Date(v).toISOString())} tick={axis} />
        <YAxis tickFormatter={gwTick} tick={axis} width={44} label={{ value: "GW", angle: -90, position: "insideLeft", fill: COLORS.muted, fontSize: 12 }} />
        <Tooltip
          labelFormatter={(v) => dayTime(new Date(Number(v)).toISOString())}
          formatter={(v, name) => [`${fmt(v)} MW`, name]}
        />
        <Legend verticalAlign="top" height={32} />
        <Line dataKey="actual" name="Actual" stroke={COLORS.actual} strokeWidth={1.6} dot={false} connectNulls isAnimationActive={false} />
        <Line dataKey="forecast" name="Forecast" stroke={COLORS.forecast} strokeWidth={1.6} dot={sparseForecast ? { r: 1.5 } : false} connectNulls isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// 3. Error vs forecast horizon
// ---------------------------------------------------------------------------
export function HorizonChart({
  rows,
  selected,
  leadBand,
}: {
  rows: HorizonRow[];
  selected: number;
  leadBand?: { min: number | null; max: number | null };
}) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 24, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        {leadBand?.min != null && leadBand?.max != null && (
          <ReferenceArea x1={Math.round(leadBand.min)} x2={Math.round(leadBand.max)} fill={COLORS.forecast} fillOpacity={0.08} />
        )}
        <XAxis dataKey="horizon_hours" tick={axis} interval={2} label={{ value: "Forecast made at least this many hours before delivery", position: "insideBottom", offset: -12, fill: COLORS.muted, fontSize: 12 }} />
        <YAxis tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}`} tick={axis} width={44} label={{ value: "GW", angle: -90, position: "insideLeft", fill: COLORS.muted, fontSize: 12 }} />
        <Tooltip formatter={(v, name) => [`${fmt(v)} MW`, name]} labelFormatter={(h) => `Horizon ${h} h`} />
        <Legend verticalAlign="top" height={32} />
        <ReferenceLine x={selected} stroke={COLORS.ink} strokeDasharray="3 3" />
        <Line dataKey="mae_mw" name="Average error (MAE)" stroke={COLORS.forecast} strokeWidth={2.4} dot={false} isAnimationActive={false} />
        <Line dataKey="rmse_mw" name="RMSE (penalises big misses)" stroke={COLORS.actual} strokeWidth={1.8} dot={false} isAnimationActive={false} />
        <Line dataKey="abs_error_p90_mw" name="P90 absolute error" stroke={COLORS.over} strokeWidth={1.8} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// 4. Error distribution
// ---------------------------------------------------------------------------
export function HistogramChart({ bins }: { bins: HistogramBin[] }) {
  const data = bins.map((b) => ({ ...b, positive: b.mid_mw > 0 }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 24, left: 0 }} barCategoryGap={1}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="mid_mw" tickFormatter={gwTick} tick={axis} label={{ value: "Forecast minus actual (GW)", position: "insideBottom", offset: -12, fill: COLORS.muted, fontSize: 12 }} />
        <YAxis tick={axis} width={44} />
        <Tooltip
          labelFormatter={(v) => `Error around ${fmt(v)} MW`}
          formatter={(v) => [`${fmt(v)} half-hours`, "Count"]}
        />
        <Bar dataKey="count" isAnimationActive={false}>
          {/* red = forecast above actual (over-forecast), amber = forecast below actual */}
          {data.map((d, i) => (
            <Cell key={i} fill={d.positive ? COLORS.over : COLORS.under} fillOpacity={0.8} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// 5. Error by hour of day
// ---------------------------------------------------------------------------
export function HourChart({ rows }: { rows: HourStat[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 24, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="hour" tick={axis} label={{ value: "Hour of delivery day (UK time)", position: "insideBottom", offset: -12, fill: COLORS.muted, fontSize: 12 }} />
        <YAxis tickFormatter={gwTick} tick={axis} width={44} />
        <Tooltip formatter={(v, name) => [`${fmt(v)} MW`, name]} labelFormatter={(h) => `${String(h).padStart(2, "0")}:00`} />
        <Legend verticalAlign="top" height={32} />
        <ReferenceLine y={0} stroke={COLORS.ink} />
        <Bar dataKey="mae_mw" name="Avg error (MAE)" fill={COLORS.forecast} fillOpacity={0.75} isAnimationActive={false} />
        <Line dataKey="bias_mw" name="Bias (+ = too high)" stroke={COLORS.over} strokeWidth={2} dot={false} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// 6. Error by wind level
// ---------------------------------------------------------------------------
export function LevelChart({ rows }: { rows: LevelStat[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 24, left: 0 }}>
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="label" tick={axis} label={{ value: "Actual wind generation", position: "insideBottom", offset: -12, fill: COLORS.muted, fontSize: 12 }} />
        <YAxis tickFormatter={gwTick} tick={axis} width={44} />
        <Tooltip formatter={(v, name) => [`${fmt(v)} MW`, name]} />
        <Legend verticalAlign="top" height={32} />
        <ReferenceLine y={0} stroke={COLORS.ink} />
        <Bar dataKey="mae_mw" name="Avg error (MAE)" fill={COLORS.forecast} fillOpacity={0.75} isAnimationActive={false} />
        <Line dataKey="bias_mw" name="Bias (+ = too high)" stroke={COLORS.over} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// 7. Daily accuracy of the day-ahead decision forecast
// ---------------------------------------------------------------------------
export function DailyChart({ rows, onPick }: { rows: DailyStat[]; onPick?: (date: string) => void }) {
  const data = rows.map((r) => ({ ...r, label: shortDate(`${r.date}T12:00:00Z`) }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart
        data={data}
        margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
        onClick={(e) => {
          const p = (e as { activePayload?: { payload: DailyStat }[] } | null)?.activePayload?.[0]?.payload;
          if (p && onPick) onPick(p.date);
        }}
      >
        <CartesianGrid stroke={COLORS.grid} vertical={false} />
        <XAxis dataKey="label" tick={axis} interval={2} />
        <YAxis tickFormatter={gwTick} tick={axis} width={44} label={{ value: "GW", angle: -90, position: "insideLeft", fill: COLORS.muted, fontSize: 12 }} />
        <Tooltip formatter={(v, name) => [`${fmt(v)} MW`, name]} />
        <Legend verticalAlign="top" height={32} />
        <ReferenceLine y={0} stroke={COLORS.ink} />
        <Bar dataKey="mae_mw" name="Average error (MAE)" fill={COLORS.forecast} fillOpacity={0.75} isAnimationActive={false} cursor="pointer" />
        <Line dataKey="bias_mw" name="Bias (+ = too high)" stroke={COLORS.over} strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export { COLORS };
