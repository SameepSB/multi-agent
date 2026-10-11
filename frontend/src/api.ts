import type { ComparisonRequest, ComparisonResult } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly correlationId?: string,
  ) {
    super(message);
  }
}

export async function compare(
  request: ComparisonRequest,
  token: string,
  signal?: AbortSignal,
): Promise<ComparisonResult> {
  let response: Response;
  try {
    response = await fetch("/api/v1/comparisons", {
      method: "POST",
      signal,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(request),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Cannot reach the API. Is it running on port 8080?", 0);
  }

  if (response.ok) return (await response.json()) as ComparisonResult;

  let body: { code?: string; correlation_id?: string } = {};
  try {
    body = await response.json();
  } catch {
    // non-JSON error body
  }
  const message =
    response.status === 401
      ? "Unauthorized: check the bearer token."
      : `Request failed (${body.code ?? response.status}).`;
  throw new ApiError(message, response.status, body.correlation_id);
}

export function formatMoney(money: { amount_minor: number; currency: string }): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: money.currency,
  }).format(money.amount_minor / 100);
}
