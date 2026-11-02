// One place for chart colours so the whole app speaks the same visual language.
export const COLORS = {
  ink: "#16242B",
  muted: "#5B6B73",
  grid: "#DCE3E6",
  actual: "#12263A", // what really happened: dark, solid
  forecast: "#0E9AA7", // what we were told: teal
  band: "#0E9AA7",
  over: "#C23B5A", // over-forecast (wind lower than expected -> risk of under-buying)
  under: "#D9961B", // under-forecast (wind higher than expected -> risk of over-buying)
};
