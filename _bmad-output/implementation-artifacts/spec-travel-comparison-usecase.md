---
title: 'Travel comparison use case'
type: 'feature'
created: '2026-10-03'
status: 'done'
review: 'thorough'
review_source: 'auto'
lenses_ran:
  - blind-hunter
  - edge-case-hunter
  - verification-gap
  - intent-alignment
baseline_commit: 'abf8bcc3cab401d62c472e98feadae06b4bad016'
route: 'full'
route_source: 'auto'
review_loop_iteration: 0
context:
  - '{project-root}/readme.md'
  - '{project-root}/Travel_Comparator_execution_steps.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-multi-agent-2026-10-03/ARCHITECTURE-SPINE.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Travel comparison is documented but not runnable.

**Approach:** Build the use case end to end: local CLI and authenticated API share a coordinator, weather/travel agents and provider adapters, tests, Compose, and Azure deployment.

## Boundaries & Constraints

**Always:** Follow the README and spine. Use Python 3.14/`uv`, canonical versioned contracts, A2A, MCP, authenticated API, CLI, Docker Compose and ACA/Bicep. Enforce deadlines, retries/idempotency, ownership, explicit partial/failure results, limits, redaction and private workers. Stub external services in deterministic tests. Attribute source data.

**Never:** Handle payment-card data, claim PCI compliance, expose workers/tools, allow user/model-controlled destinations/tools, add a database, or require live APIs for tests. Never present synthetic estimates as bookable/live quotes.

**User decision:** Use labeled synthetic fare/hotel estimates for missing routes. Mark them illustrative, not live/bookable; preserve the three documented NYC examples.

## I/O & Edge-Case Matrix

| Scenario | Input | Expected behavior | Error |
|---|---|---|---|
| Complete | Valid 2–4 destination comparison | Parallel assessment, conditional follow-up, deterministic winner and provenance | HTTP 200 `complete` |
| Partial/failed | Some/all required sources unavailable | Mark omissions; no invented result or unsupported winner | HTTP 200 `partial` / HTTP 502 `failed` |
| Rejected | Invalid, oversized, unauthorized or payment-bearing input | Reject before fan-out; redact request | HTTP 4xx |
| Timeout | Provider exceeds shared deadline | At most one safe retry; no duplicate task | HTTP 504 |

</frozen-after-approval>

## Code Map

- `readme.md` and `_bmad-output/planning-artifacts/architecture/architecture-multi-agent-2026-10-03/ARCHITECTURE-SPINE.md` — binding contracts, behavior, security and deployment rules.
- `Travel_Comparator_execution_steps.md` — runnable local/API guide, truthful provider limitations, Azure promotion steps, supported inputs, and the three preserved illustrative NYC totals.
- `pyproject.toml`, `uv.lock`, `src/travel_comparator/` — pinned Python 3.14 app, shared contracts/coordinator, CLI/API, A2A workers, MCP/NWS and OpenAI adapters.
- `data/travel_data.json` — explicit illustrative travel reference data.
- `tests/` — unit, contract, integration, API, A2A, MCP, and deployment-boundary tests.
- `deploy/compose.yaml`, `Dockerfile`, `deploy/bicep/`, `.github/workflows/` — local topology, image, ACA templates, and staged digest-based CI/CD.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml`, `uv.lock`, `.gitignore`, `.env.example` — pinned runtime, config and secret exclusions.
- [x] `src/travel_comparator/contracts/`, `application/` — canonical schemas/settings; parallel orchestration, follow-up and deterministic winner.
- [x] `src/travel_comparator/agents/`, `providers/`, `data/travel_data.json` — A2A workers, MCP/NWS, OpenAI, provenance-labelled estimates.
- [x] `src/travel_comparator/api/`, `cli/` — health, role-protected REST and thin CLI sharing the use case.
- [x] `tests/` — contracts, behavior, auth, failures, data safety, timeout, idempotency, and stubbed end-to-end coverage.
- [x] `deploy/` — Compose, image, Bicep and protected CI/CD for internal workers and immutable Azure releases.
- [x] `readme.md`, `Travel_Comparator_execution_steps.md` — runnable workflow and truthful limits.

**Acceptance Criteria:**
- Given valid input from CLI or API, when a comparison runs, then both use the same schema-valid parallel coordinator flow, conditional follow-up and deterministic recommendation.
- Given provider failures, invalid input, denied identity, payment data or timeout, when handled, then use the matrix status; do no unauthorized fan-out and invent no evidence.
- Given laptop Compose with stubbed providers, when started and smoke-tested, then API and private agents are healthy without Azure credentials or live-provider tests.
- Given Bicep deployment, when promoted through protected environments, then only the API is externally reachable, workers authorize the coordinator identity, secrets are least-privilege, and image digests are immutable.

## Implementation Notes

- All application outbound integrations are injectable/stubbable; automated tests do not require Azure, NWS, or OpenAI credentials.
- Azure role assignments and user-assigned identities are defined in Bicep. Entra app-role creation/assignment, Key Vault RBAC-mode setup, GitHub Environment protection, and live deployment are operator prerequisites.
- Live NWS mode requires an operator-supplied `NWS_USER_AGENT` identifying the application and a genuine monitored contact; stub mode does not require it.
- Live weather assessments use the requested departure date's daytime forecast and return `UNAVAILABLE` when the NWS response has no forecast period for that date. Synthetic travel estimates identify their data owner and version; trip-overlap event impacts are included in pricing and recommendation warnings.
- API throttling and idempotency-response storage are bounded in-process caches, consistent with the no-database boundary. They are not shared/durable across replicas, restarts, or scale-to-zero; use a shared store only if durable, cross-replica quotas or idempotency become a requirement.
- The API result cache replays completed responses for the same authenticated principal, key, and request bytes. Reusing a key with different request bytes returns 409. A request without a supplied key receives a request-scoped key.

## Spec Change Log

## Review Triage Log

- Direct final check found the API route called the coordinator once through the new idempotency result cache and again after it; the redundant call was removed. The regression test now asserts a replay returns the same result without additional agent calls.
- Thorough review follow-up hardened A2A JSON shape validation and JWT role-claim type checks; bounded rate-limit principal state; enforced configured CLI city limits and card-data rejection; allowed stub-mode startup without an OpenAI key; surfaced data owner/version; fixed overlapping trip-event handling and severe-event warnings; and made Azure Container Apps launch the correct API/worker process.
- Verification-gap follow-up added focused live-mode NWS classification/date tests and API/worker OIDC role tests. CI now starts Compose, waits for API readiness, and runs the CLI smoke comparison. Compose startup was not executable in this local environment because Docker is unavailable.
- Intent-alignment follow-up found no missing local application surface; CLI/API share the coordinator, while fare/hotel estimates remain explicitly synthetic and Azure deployment remains an operator-run environment check.
- Residual: Bicep's image parameter documents digest-only input but does not itself regex-validate digest syntax; the GitHub release workflows enforce a full `sha256:` digest before deployment. Direct deployments that bypass those workflows must provide a validated digest.

## Design Notes

The CLI accepts natural-language queries through OpenAI; REST accepts the canonical request. Both converge before orchestration. Model text cannot override structured evidence or winner rules.

## Verification

**Commands:**
- `uv sync --locked --dev` — passed with Python 3.14.5.
- `uv run --locked pytest -q` — passed: 50 tests, including a stubbed API → A2A worker → MCP end-to-end journey and focused auth, NWS, event, CLI-input, and limiter regressions.
- `uv run --locked ruff check src tests` and `uv run --locked ruff format --check src tests` — passed.
- `uv export --locked --no-emit-project --format requirements-txt --output-file requirements-audit.txt`, followed by `uv run --locked pip-audit --strict --requirement requirements-audit.txt` — passed; the generated audit file was removed.
- All four Bicep files (`foundation.bicep`, `main.bicep`, `api-app.bicep`, `worker-app.bicep`) compiled successfully with the Bicep build tool. Azure CLI is not installed locally.
- All three GitHub Actions workflow files parsed as YAML; `git diff --check` passed.
- `docker compose --env-file .env.example -f deploy/compose.yaml config --quiet` and `docker compose up --build` could not be run because Docker is not installed in this environment. CI is configured to validate Compose startup/readiness and a CLI comparison, but that workflow was not run in this environment.
- No Azure resources were deployed. GitHub environment approvals, federated credentials, Entra app roles, Key Vault setup, image promotion, and readiness smoke checks remain operator/deployment verification.
