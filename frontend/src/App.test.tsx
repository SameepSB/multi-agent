import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { formatMoney } from "./api";

const result = {
  status: "complete",
  correlation_id: "cid-1",
  origin: "New York",
  duration_days: 5,
  comparisons: [
    {
      destination: "Denver",
      weather: { status: "GO", high_celsius: 22.2, summary: "Clear", active_alerts: [], source: "s" },
      travel: {
        flight: { amount_minor: 25000, currency: "USD" },
        hotel_per_night: { amount_minor: 13000, currency: "USD" },
        lodging_nights: 5,
        total: { amount_minor: 90000, currency: "USD" },
        travel_time_hours: 4.5,
        event: null,
        event_severity: "none",
      },
      unavailable_sources: [],
    },
  ],
  recommendation: { winner: "Denver", reason: "Lowest cost.", warning: null },
  narrative: null,
  limitations: ["Illustrative amounts."],
};

afterEach(() => {
  vi.restoreAllMocks();
  sessionStorage.clear();
});

async function submit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/bearer token/i), "tok");
  await user.click(screen.getByRole("button", { name: /compare/i }));
}

test("formats minor units as currency", () => {
  expect(formatMoney({ amount_minor: 90000, currency: "USD" })).toBe("$900.00");
});

test("sends bearer token and renders the recommendation", async () => {
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValue(new Response(JSON.stringify(result), { status: 200 }));
  render(<App />);
  await submit();

  expect(await screen.findByText("Recommended: Denver")).toBeInTheDocument();
  expect(screen.getByText("$900.00")).toBeInTheDocument();
  const [, init] = fetchMock.mock.calls[0];
  expect((init!.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  expect(JSON.parse(init!.body as string).destinations).toEqual(["Denver", "Austin", "Miami"]);
});

test("shows unauthorized error with correlation id", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ code: "UNAUTHORIZED", correlation_id: "cid-9" }), { status: 401 }),
  );
  render(<App />);
  await submit();

  expect(await screen.findByRole("alert")).toHaveTextContent(/unauthorized.*cid-9/i);
});

test("rejects fewer than two destinations without calling the API", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch");
  render(<App />);
  const user = userEvent.setup();
  await user.clear(screen.getByLabelText(/destinations/i));
  await user.type(screen.getByLabelText(/destinations/i), "Denver");
  await user.type(screen.getByLabelText(/bearer token/i), "tok");
  await user.click(screen.getByRole("button", { name: /compare/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/2 and 4/);
  expect(fetchMock).not.toHaveBeenCalled();
});
