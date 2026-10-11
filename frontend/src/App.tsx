import { FormEvent, useState } from "react";
import { ApiError, compare, formatMoney } from "./api";
import type { ComparisonResult } from "./types";

const TOKEN_KEY = "travel-comparator-token";

function parseDestinations(raw: string): string[] {
  return raw
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

export default function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem(TOKEN_KEY) ?? "");
  const [origin, setOrigin] = useState("New York");
  const [destinations, setDestinations] = useState("Denver, Austin, Miami");
  const [days, setDays] = useState(5);
  const [departure, setDeparture] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<ComparisonResult | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const list = parseDestinations(destinations);
    if (list.length < 2 || list.length > 4) {
      setError(new ApiError("Enter between 2 and 4 destinations, comma separated.", 0));
      return;
    }
    sessionStorage.setItem(TOKEN_KEY, token);
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await compare(
          {
            origin: origin.trim(),
            destinations: list,
            duration_days: days,
            ...(departure ? { departure_date: departure } : {}),
          },
          token,
        ),
      );
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("Unexpected error.", 0));
    } finally {
      setLoading(false);
    }
  }

  const cheapest = result?.recommendation.winner ?? null;

  return (
    <main>
      <h1>Travel Comparator</h1>
      <form onSubmit={onSubmit} aria-label="comparison form">
        <label>
          Bearer token
          <input
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            required
            autoComplete="off"
          />
        </label>
        <label>
          Origin
          <input value={origin} onChange={(e) => setOrigin(e.target.value)} required minLength={2} maxLength={80} />
        </label>
        <label>
          Destinations (2–4, comma separated)
          <input value={destinations} onChange={(e) => setDestinations(e.target.value)} required />
        </label>
        <label>
          Days
          <input
            type="number"
            min={1}
            max={30}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            required
          />
        </label>
        <label>
          Departure date (optional)
          <input type="date" value={departure} onChange={(e) => setDeparture(e.target.value)} />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Comparing…" : "Compare"}
        </button>
      </form>

      {error && (
        <p role="alert" className="error">
          {error.message}
          {error.correlationId && <small> Correlation ID: {error.correlationId}</small>}
        </p>
      )}

      {result && (
        <section aria-label="results">
          <div className="recommendation">
            <h2>{cheapest ? `Recommended: ${cheapest}` : "No recommendation"}</h2>
            <p>{result.recommendation.reason}</p>
            {result.recommendation.warning && <p className="warn">{result.recommendation.warning}</p>}
            {result.narrative && <p>{result.narrative}</p>}
          </div>

          <div className="cards">
            {result.comparisons.map((city) => (
              <article key={city.destination} className={city.destination === cheapest ? "card winner" : "card"}>
                <h3>{city.destination}</h3>
                {city.weather ? (
                  <p>
                    <span className={`badge ${city.weather.status.toLowerCase()}`}>{city.weather.status}</span>{" "}
                    {city.weather.high_celsius}°C — {city.weather.summary}
                  </p>
                ) : (
                  <p>Weather unavailable</p>
                )}
                {city.weather?.active_alerts.map((alert) => (
                  <p key={alert} className="warn">
                    {alert}
                  </p>
                ))}
                {city.travel ? (
                  <dl>
                    <dt>Flight</dt>
                    <dd>{formatMoney(city.travel.flight)}</dd>
                    <dt>Hotel / night</dt>
                    <dd>{formatMoney(city.travel.hotel_per_night)}</dd>
                    <dt>Total</dt>
                    <dd>
                      <strong>{formatMoney(city.travel.total)}</strong>
                    </dd>
                    <dt>Travel time</dt>
                    <dd>{city.travel.travel_time_hours} h</dd>
                  </dl>
                ) : (
                  <p>Pricing unavailable</p>
                )}
              </article>
            ))}
          </div>

          {result.limitations.length > 0 && (
            <ul className="limitations">
              {result.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
          <small>Correlation ID: {result.correlation_id}</small>
        </section>
      )}
    </main>
  );
}
