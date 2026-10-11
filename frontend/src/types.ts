export interface Money {
  amount_minor: number;
  currency: string;
}

export interface Weather {
  status: "GO" | "CAUTION" | string;
  high_celsius: number;
  summary: string;
  active_alerts: string[];
  source: string;
}

export interface Travel {
  flight: Money;
  hotel_per_night: Money;
  lodging_nights: number;
  total: Money;
  travel_time_hours: number;
  event: string | null;
  event_severity: string;
}

export interface CityComparison {
  destination: string;
  weather: Weather | null;
  travel: Travel | null;
  unavailable_sources: string[];
}

export interface Recommendation {
  winner: string | null;
  reason: string;
  warning: string | null;
}

export interface ComparisonResult {
  status: string;
  correlation_id: string;
  origin: string;
  duration_days: number;
  comparisons: CityComparison[];
  recommendation: Recommendation;
  narrative: string | null;
  limitations: string[];
}

export interface ComparisonRequest {
  origin: string;
  destinations: string[];
  duration_days: number;
  departure_date?: string;
}
