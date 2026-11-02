import { useState } from "react";
import { api } from "../api";
import { clampDate, gw, hours, mw, pct, signed } from "../format";
import { useAsync } from "../hooks";
import type { Meta, Metrics } from "../types";
import { DailyChart, HistogramChart, HorizonChart, HourChart, LevelChart, SeriesChart } from "./charts";
import { Panel, Section, StatStrip, Status } from "./ui";

interface Props {
  meta: Meta;
  decisionTime: string;
  onOpenDay: (date: string) => void;
}

function metricStrip(m: Metrics) {
  return [
    { label: "Average error (MAE)", value: mw(m.mae_mw), hint: `${pct(m.wmape_pct)} of generation` },
    { label: "RMSE", value: mw(m.rmse_mw), hint: "weights large misses more" },
    { label: "Bias", value: signed(m.bias_mw), hint: "+ means forecast too high" },
    { label: "90% of misses are below", value: mw(m.abs_error_p90_mw), hint: "absolute error, P90" },
    { label: "Over-forecast buffer", value: mw(m.over_forecast_p90_mw), hint: "wind fell short of forecast by more than this only 10% of the time" },
  ];
}

export default function AccuracyView({ meta, decisionTime, onOpenDay }: Props) {
  const [horizon, setHorizon] = useState(24);
  const [start, setStart] = useState(meta.delivery_start);
  const [end, setEnd] = useState(meta.delivery_end);

  const dayAhead = useAsync(() => api.dayAhead(decisionTime, 1), [decisionTime], 250);
  const sweep = useAsync(() => api.byHorizon(start, end), [start, end], 250);
  const explore = useAsync(() => api.horizon(horizon, start, end), [horizon, start, end], 250);

  const da = dayAhead.data;
  const ex = explore.data;

  return (
    <>
      <Section
        title="How good is the forecast we actually buy on?"
        note={`Every delivery day in January 2026, using the newest forecast published before ${decisionTime} UK time on the previous day.`}
      >
        <Status loading={dayAhead.loading} error={dayAhead.error}>
          {da && (
            <>
              <StatStrip items={metricStrip(da.overall)} />
              <p className="narrative">
                These forecasts were issued {hours(da.lead_hours.min)} to {hours(da.lead_hours.max)} before the delivery half-hour (median {hours(da.lead_hours.median)}). Typical miss: {mw(da.overall.mae_mw)}. To be covered
                nine times out of ten against wind falling short, hold back about {mw(da.overall.over_forecast_p90_mw)} of the forecast wind.
              </p>
              <Panel title="Accuracy per delivery day (click a bar to open that day)" wide>
                <DailyChart rows={da.daily} onPick={onOpenDay} />
              </Panel>
              <div className="grid-2">
                <Panel title="Distribution of misses (red: forecast too high, amber: too low)">
                  <HistogramChart bins={da.histogram} />
                </Panel>
                <Panel title="Error by hour of the delivery day">
                  <HourChart rows={da.by_hour} />
                </Panel>
              </div>
            </>
          )}
        </Status>
      </Section>

      <Section
        title="How does accuracy change with how far ahead we look?"
        note="For each horizon h we use the newest forecast published at least h hours before the delivery half-hour. The shaded band marks the lead times of the day-ahead decision above."
      >
        <div className="controls">
          <label>
            From
            <input type="date" value={start} min={meta.delivery_start} max={end} onChange={(e) => e.target.value && setStart(clampDate(e.target.value, meta.delivery_start, end))} />
          </label>
          <label>
            To
            <input type="date" value={end} min={start} max={meta.delivery_end} onChange={(e) => e.target.value && setEnd(clampDate(e.target.value, start, meta.delivery_end))} />
          </label>
        </div>
        <Status loading={sweep.loading} error={sweep.error}>
          {sweep.data && (
            <Panel title="Error growth with forecast horizon" wide>
              <HorizonChart rows={sweep.data.rows} selected={horizon} leadBand={da?.lead_hours} />
            </Panel>
          )}
        </Status>
      </Section>

      <Section title="Explore one horizon in detail" note="Drag the slider to choose how many hours ahead the forecast was made.">
        <div className="controls">
          <label className="slider">
            Horizon: {horizon} h before delivery
            <input type="range" min={0} max={meta.max_horizon_hours} step={1} value={horizon} onChange={(e) => setHorizon(Number(e.target.value))} />
          </label>
        </div>
        <Status loading={explore.loading} error={explore.error}>
          {ex && (
            <>
              <StatStrip items={metricStrip(ex.metrics)} />
              <p className="muted small">
                Based on {ex.metrics.n.toLocaleString("en-GB")} of {ex.metrics.n_total.toLocaleString("en-GB")} half-hours with both a forecast and an actual. Average actual wind in this period: {gw(ex.metrics.mean_actual_mw)}.
              </p>
              <Panel title="Actual vs forecast (GW)" wide>
                <SeriesChart series={ex.series} />
              </Panel>
              <div className="grid-3">
                <Panel title="Distribution of misses">
                  <HistogramChart bins={ex.histogram} />
                </Panel>
                <Panel title="Error by hour of day">
                  <HourChart rows={ex.by_hour} />
                </Panel>
                <Panel title="Error by how windy it was">
                  <LevelChart rows={ex.by_level} />
                </Panel>
              </div>
            </>
          )}
        </Status>
      </Section>
    </>
  );
}
