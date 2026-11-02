import { useState } from "react";
import { api } from "./api";
import AccuracyView from "./components/AccuracyView";
import DecisionView from "./components/DecisionView";
import { Status } from "./components/ui";
import { useAsync } from "./hooks";

type Tab = "decision" | "accuracy";

export default function App() {
  const meta = useAsync(() => api.meta(), []);
  const [tab, setTab] = useState<Tab>("decision");
  const [date, setDate] = useState("2026-01-15");
  const [decisionTime, setDecisionTime] = useState<string | null>(null);

  const m = meta.data;
  const time = decisionTime ?? m?.default_decision_time ?? "09:00";

  return (
    <div className="page">
      <header className="masthead">
        <h1>Wind forecasts for the day-ahead market</h1>
        <p>
          Great Britain, national wind generation, purchases for January 2026. Forecasts and actuals from Elexon BMRS (WINDFOR and FUELHH).
        </p>
      </header>

      {m?.source === "synthetic" && (
        <div className="banner danger" role="alert">
          Synthetic demo data is loaded. These numbers are not from Elexon. Run <code>python -m backend.scripts.fetch_data</code> to load real data.
        </div>
      )}

      <nav className="tabs" aria-label="Views">
        <button className={tab === "decision" ? "active" : ""} onClick={() => setTab("decision")}>
          Day-ahead decision
        </button>
        <button className={tab === "accuracy" ? "active" : ""} onClick={() => setTab("accuracy")}>
          Forecast accuracy
        </button>
      </nav>

      <main>
        <Status loading={meta.loading} error={meta.error}>
          {m &&
            (tab === "decision" ? (
              <DecisionView meta={m} date={date} onDateChange={setDate} decisionTime={time} onDecisionTimeChange={setDecisionTime} />
            ) : (
              <AccuracyView
                meta={m}
                decisionTime={time}
                onOpenDay={(d) => {
                  setDate(d);
                  setTab("decision");
                  window.scrollTo({ top: 0 });
                }}
              />
            ))}
        </Status>
      </main>

      <footer>
        <p>
          Source: Elexon BMRS Insights API. Times are UK local time (GMT in January). Error is forecast minus actual, so a positive error means the forecast was too optimistic about wind. Contains BMRS data © Elexon Limited copyright and database right 2026.
          {m && ` Snapshot: ${m.actuals_rows.toLocaleString("en-GB")} actual half-hours, ${m.forecast_rows.toLocaleString("en-GB")} forecast rows from ${m.forecast_publish_times.toLocaleString("en-GB")} forecast issues.`}
        </p>
      </footer>
    </div>
  );
}
