import { useState } from "react";
import { api } from "../api";
import { clampDate, clock, dayTime, gw, gwh, hours, mw, pct, shortDate, signed } from "../format";
import { useAsync } from "../hooks";
import type { DecisionView as DecisionData, Meta } from "../types";
import { DecisionChart } from "./charts";
import { Panel, Section, StatStrip, Status } from "./ui";

interface Props {
  meta: Meta;
  date: string;
  onDateChange: (d: string) => void;
  decisionTime: string;
  onDecisionTimeChange: (t: string) => void;
}

function shiftDay(iso: string, delta: number, min: string, max: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  const out = d.toISOString().slice(0, 10);
  return out < min ? min : out > max ? max : out;
}

/** Plain-English read-out of what the buyer knew at decision time. */
function narrative(d: DecisionData): string {
  const s = d.summary;
  if (s.n_with_forecast === 0 || s.forecast_energy_mwh == null) {
    return "No wind forecast had been published by this decision time, so there is nothing to base the purchase on yet.";
  }
  const avg = s.forecast_energy_mwh / (s.n_with_forecast * 0.5);
  const parts = [
    `At ${dayTime(d.cutoff_utc)} the newest forecast available was issued at ${dayTime(s.newest_forecast_published)}.`,
    `It expected wind to average ${gw(avg)} on ${shortDate(`${d.delivery_date}T12:00:00Z`)}, peaking at ${gw(s.peak_forecast_mw)} around ${s.peak_forecast_time ? clock(s.peak_forecast_time) : "n/a"} and dropping to ${gw(s.min_forecast_mw)} around ${s.min_forecast_time ? clock(s.min_forecast_time) : "n/a"}.`,
  ];
  return parts.join(" ");
}

export default function DecisionView({ meta, date, onDateChange, decisionTime, onDecisionTimeChange }: Props) {
  const [showActual, setShowActual] = useState(true);
  const [showBand, setShowBand] = useState(true);
  const state = useAsync(() => api.decision(date, decisionTime, 1), [date, decisionTime], 250);
  const d = state.data;

  return (
    <>
      <Section
        title="What do we know when we place the day-ahead order?"
        note="Pick the delivery day and the time the buying decision is made on the previous day. The chart shows only forecasts that had already been published by then."
      >
        <div className="controls">
          <label>
            Delivery day
            <span className="inline">
              <button type="button" className="step" aria-label="Previous day" onClick={() => onDateChange(shiftDay(date, -1, meta.delivery_start, meta.delivery_end))}>
                ‹
              </button>
              <input type="date" value={date} min={meta.delivery_start} max={meta.delivery_end} onChange={(e) => e.target.value && onDateChange(clampDate(e.target.value, meta.delivery_start, meta.delivery_end))} />
              <button type="button" className="step" aria-label="Next day" onClick={() => onDateChange(shiftDay(date, 1, meta.delivery_start, meta.delivery_end))}>
                ›
              </button>
            </span>
          </label>
          <label>
            Decision time on the day before (UK)
            <input type="time" value={decisionTime} onChange={(e) => e.target.value && onDecisionTimeChange(e.target.value)} />
          </label>
          <label className="check">
            <input type="checkbox" checked={showBand} onChange={(e) => setShowBand(e.target.checked)} />
            Show likely range
          </label>
          <label className="check">
            <input type="checkbox" checked={showActual} onChange={(e) => setShowActual(e.target.checked)} />
            Show what actually happened
          </label>
        </div>

        <Status loading={state.loading} error={state.error}>
          {d && (
            <>
              <p className="narrative">{narrative(d)}</p>
              <StatStrip
                items={[
                  { label: "Expected wind energy", value: gwh(d.summary.forecast_energy_mwh), hint: "whole delivery day" },
                  { label: "Peak forecast", value: gw(d.summary.peak_forecast_mw), hint: d.summary.peak_forecast_time ? `at ${clock(d.summary.peak_forecast_time)}` : undefined },
                  { label: "Lowest forecast", value: gw(d.summary.min_forecast_mw), hint: d.summary.min_forecast_time ? `at ${clock(d.summary.min_forecast_time)}` : undefined },
                  { label: "Forecast age at decision", value: `${hours(d.summary.min_lead_hours)} to ${hours(d.summary.max_lead_hours)}`, hint: "time between issue and delivery period" },
                ]}
              />

              <Panel title="Wind generation forecast for the delivery day (GW, half-hourly)" wide>
                <DecisionChart periods={d.periods} showActual={showActual} showBand={showBand && d.band.available} />
                {showBand && !d.band.available && <p className="muted small">Likely range not shown: {d.band.basis}.</p>}
                {showBand && d.band.available && (
                  <p className="muted small">
                    Likely range = forecast plus the 10th and 90th percentile of past misses ({signed(d.band.p10_residual_mw)} / {signed(d.band.p90_residual_mw)}), learned from {d.band.basis} that were already known at decision time.
                  </p>
                )}
              </Panel>

              {showActual && (
                <>
                  <h3>How it turned out</h3>
                  <StatStrip
                    items={[
                      { label: "Actual wind energy", value: gwh(d.summary.actual_energy_mwh), hint: `forecast was ${gwh(d.summary.forecast_energy_mwh)}` },
                      { label: "Average error", value: mw(d.metrics.mae_mw), hint: `${pct(d.metrics.wmape_pct)} of generation` },
                      { label: "Bias", value: signed(d.metrics.bias_mw), hint: (d.metrics.bias_mw ?? 0) > 0 ? "forecast was too high on average" : "forecast was too low on average" },
                      { label: "Worst over-forecast", value: mw(d.metrics.max_over_mw), hint: "wind lower than forecast: risk of under-buying" },
                    ]}
                  />
                </>
              )}
            </>
          )}
        </Status>
      </Section>

      {d && d.vintages.length > 0 && (
        <Section title="Which forecast versions fed this view" note="Elexon publishes new wind forecasts through the day. Each delivery half-hour uses the newest one that existed at the decision time.">
          <table className="table">
            <thead>
              <tr>
                <th>Forecast issued</th>
                <th>Covers delivery periods</th>
                <th>Half-hours used</th>
              </tr>
            </thead>
            <tbody>
              {d.vintages.map((v) => (
                <tr key={v.publish_time}>
                  <td>{dayTime(v.publish_time)}</td>
                  <td>
                    {clock(v.first_period)} to {clock(v.last_period)}
                  </td>
                  <td>{v.n_periods}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
    </>
  );
}
