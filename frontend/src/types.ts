// TypeScript shapes of the JSON returned by the Python API (see backend/analysis.py).

export interface Meta {
  source: string; // "elexon" for real data, "synthetic" for offline demo data
  fetched_at: string | null;
  delivery_start: string;
  delivery_end: string;
  default_decision_time: string;
  default_days_before: number;
  max_horizon_hours: number;
  actuals_rows: number;
  forecast_rows: number;
  forecast_publish_times: number;
}

export interface Metrics {
  n: number;
  n_total: number;
  mean_actual_mw: number | null;
  mae_mw: number | null;
  rmse_mw: number | null;
  bias_mw: number | null;
  wmape_pct: number | null;
  abs_error_p50_mw: number | null;
  abs_error_p90_mw: number | null;
  abs_error_p95_mw: number | null;
  over_forecast_p90_mw: number | null;
  under_forecast_p90_mw: number | null;
  max_over_mw: number | null;
  max_under_mw: number | null;
}

export interface Period {
  t: string;
  forecast_mw: number | null;
  actual_mw: number | null;
  error_mw: number | null;
  publish_time: string | null;
  lead_hours: number | null;
  band_low_mw?: number | null;
  band_high_mw?: number | null;
}

export interface Vintage {
  publish_time: string;
  n_periods: number;
  first_period: string;
  last_period: string;
}

export interface DecisionView {
  delivery_date: string;
  decision_time_local: string;
  days_before: number;
  cutoff_utc: string | null;
  periods: Period[];
  summary: {
    n_periods: number;
    n_with_forecast: number;
    n_with_actual: number;
    forecast_energy_mwh: number | null;
    actual_energy_mwh: number | null;
    peak_forecast_mw: number | null;
    peak_forecast_time: string | null;
    min_forecast_mw: number | null;
    min_forecast_time: string | null;
    newest_forecast_published: string | null;
    oldest_forecast_published: string | null;
    min_lead_hours: number | null;
    max_lead_hours: number | null;
  };
  vintages: Vintage[];
  band: {
    available: boolean;
    basis: string;
    p10_residual_mw: number | null;
    p90_residual_mw: number | null;
  };
  metrics: Metrics;
}

export interface HistogramBin {
  from_mw: number;
  to_mw: number;
  mid_mw: number;
  count: number;
}

export interface HourStat {
  hour: number;
  mae_mw: number | null;
  bias_mw: number | null;
  n: number;
}

export interface LevelStat {
  label: string;
  n: number;
  mae_mw: number | null;
  bias_mw: number | null;
  wmape_pct: number | null;
}

export interface DailyStat {
  date: string;
  n: number;
  mae_mw: number | null;
  rmse_mw: number | null;
  bias_mw: number | null;
  wmape_pct: number | null;
  mean_actual_mw: number | null;
  mean_lead_hours: number | null;
}

export interface DayAheadAccuracy {
  decision_time_local: string;
  days_before: number;
  overall: Metrics;
  lead_hours: { min: number | null; median: number | null; max: number | null };
  daily: DailyStat[];
  histogram: HistogramBin[];
  by_hour: HourStat[];
  by_level: LevelStat[];
}

export interface HorizonAccuracy {
  horizon_hours: number;
  start: string;
  end: string;
  metrics: Metrics;
  series: Period[];
  histogram: HistogramBin[];
  by_hour: HourStat[];
  by_level: LevelStat[];
}

export interface HorizonRow {
  horizon_hours: number;
  n: number;
  mae_mw: number | null;
  rmse_mw: number | null;
  bias_mw: number | null;
  wmape_pct: number | null;
  abs_error_p90_mw: number | null;
  median_actual_lead_hours: number | null;
}
