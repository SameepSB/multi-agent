# Travel Comparator — Architecture

**Document type:** Target architecture and implementation contract
**Status:** Architecture defined; application implementation and Azure deployment are not present in this repository yet.
**Last updated:** 2026-10-03

This document describes how to build and operate the Travel Comparator as a secure, cost-conscious MVP: develop and test on a laptop first, then deploy to Azure. It also records the boundaries to preserve if payment capabilities are introduced later. It is not a claim that the controls are already implemented or that the system is PCI DSS compliant.

The current product behavior and demo sequence are in [Travel_Comparator_execution_steps.md](./Travel_Comparator_execution_steps.md). The concise, enforceable architecture spine is in [ARCHITECTURE-SPINE.md](./_bmad-output/planning-artifacts/architecture/architecture-multi-agent-2026-10-03/ARCHITECTURE-SPINE.md).

## 1. Architecture at a glance

Use an **orchestrated service architecture**. The coordinator owns the trip-comparison workflow and final recommendation. Weather and Travel Advisor agents own their respective domains and are independently callable. The coordinator requests first-round work concurrently, asks for follow-up only when results conflict, and synthesizes a final response from validated agent results.

```mermaid
flowchart LR
    user[Traveler]
    cli[Local CLI]
    api[Authenticated REST API]
    coordinator[Coordinator and application service]
    weather[Weather Agent]
    travel[Travel Advisor Agent]
    mcp[MCP weather tools]
    nws[National Weather Service]
    data[Versioned travel reference data]
    openai[OpenAI API]

    user --> cli
    user --> api
    cli --> coordinator
    api --> coordinator
    coordinator -->|A2A| weather
    coordinator -->|A2A| travel
    weather -->|MCP over stdio| mcp
    mcp --> nws
    travel --> data
    coordinator --> openai
```

### Responsibilities and ownership

| Component | Owns | Must not own |
| --- | --- | --- |
| CLI adapter | Local interactive input/output; calls the application service | Comparison rules, agent protocol implementations |
| REST API | Versioned request/response boundary, authentication, input validation, health endpoints | Agent business logic or direct tool access |
| Coordinator/application service | Query normalization, agent discovery from configured trusted endpoints, parallel fan-out, conflict detection, follow-up, final synthesis | Weather/travel source internals, direct MCP calls, persistent shared state |
| Weather Agent | Weather interpretation and weather-source access | Travel prices, final destination selection |
| MCP weather process | Explicitly allow-listed weather tools and NWS access | Public client ingress or arbitrary tool execution |
| Travel Advisor Agent | Flight/hotel/event comparison using versioned reference data | Weather judgments or coordinator workflow |

The Weather Agent owns its MCP client and starts the weather MCP server as a child process over stdio; that process is packaged with the Weather Agent for deployment. The coordinator never connects directly to MCP.

## 2. Decisions and alternatives

| Area | Chosen direction | Trade-off / when to revisit |
| --- | --- | --- |
| Workflow shape | Coordinator-led orchestration with separate domain agents | Easier to reason about than peer-to-peer negotiation; introduce choreography only if independent agents must initiate workflows. |
| Local/cloud runtime | Docker Compose locally; Azure Container Apps (ACA) Consumption plan, scaling to zero until measured objectives require warm replicas | AKS is deferred unless Kubernetes control, add-ons, or organizational standards justify its operating cost. |
| Client interfaces | Keep the local CLI and add an authenticated, versioned REST API for cloud access; both call the same application service | Requires an HTTP/API surface in addition to the current interactive runbook. Do not deploy an interactive terminal as the production interface. |
| Model provider | Preserve the existing OpenAI API integration | Keep provider settings behind configuration; Azure OpenAI is a future option, not an implicit MVP migration. |
| State | No shared database for the MVP; travel reference data is versioned with the application; comparison state is request-scoped | Add persistence only when history, user accounts, tenancy, or durable workflows become product requirements. |
| PCI direction | Do not collect, process, transmit, or store cardholder data in the MVP | Future payment support must use a payment provider's hosted/tokenized capture and undergo formal scope/compliance assessment before handling payment flows. This architecture does not confer PCI DSS compliance. |

## 3. Request and agent contracts

### Client API

Expose the comparison operation under a versioned route such as `POST /api/v1/comparisons`. The API accepts a bounded, schema-validated trip request and returns a structured result with normalized cities, source results, any unavailable sources, and the recommendation. Keep the CLI as a thin local adapter over the same application-service interface.

Provide separate liveness and readiness endpoints. Liveness reports whether the process can run; readiness reports whether it can accept work (including required startup dependencies). Neither endpoint returns secrets or provider diagnostics. Authenticate every non-local deployment using a configured OIDC issuer/audience. Require the `TravelComparator.User` application role and deny access by default; provision approved users explicitly, with no anonymous access or self-registration. Local development binds to loopback and may use an explicit development auth profile. Authentication must never be disabled by a production configuration.

Use the same typed configuration contract across Compose and Azure. Required settings are `APP_ENV` (`local`, `development`, or `production`), `LOG_LEVEL`, `WEATHER_AGENT_URL`, `TRAVEL_AGENT_URL`, `OPENAI_API_KEY` (coordinator only), and `REQUEST_TIMEOUT_SECONDS` (integer, 30 for the MVP). `API_PORT` is an integer with a development-only default; `MAX_CITIES` is an integer capped at 4, matching the documented comparison scenarios. A2A audiences and local worker credentials are required for their respective deployment profiles. Fail startup when required settings are absent or malformed; no production endpoint or credential has a permissive default.

### Agent and tool boundaries

- Use **A2A 1.0.0** for coordinator-to-agent task exchange and capability discovery. Configure trusted worker service names/addresses from deployment configuration; never fetch or call arbitrary agent URLs supplied in user text or Agent Cards. In Azure, each app has a distinct managed identity; worker APIs validate the caller token's issuer, audience, expiry, and `invoke` role, and authorize only the coordinator identity.
- Use **MCP specification 2026-07-28** between the Weather Agent and its bundled weather-tool process. Expose only the named weather operations required by the application.
- Treat all user text, agent responses, Agent Cards, external data, and model output as untrusted. Validate protocol and domain schemas at each boundary; do not execute model-generated code or tool names.
- Keep one versioned canonical schema under `contracts/` for API and A2A requests, results, and errors. Dates use ISO 8601 calendar dates; timestamps use ISO 8601 with UTC offsets; money uses integer minor units plus an ISO 4217 currency; measurements carry explicit units. Standardize errors as `{code, source, retryable, correlation_id}`. Return `complete`, `partial`, or `failed` status consistently.
- Never let an agent silently turn missing data into a favorable result. If a source fails, either return a clearly marked partial comparison or fail the request according to the API contract; never fabricate prices, weather, or events.
- Follow-up is required when any city has weather status other than `GO`, the cheapest city differs from the weather-preferred city, or an event is severe. Among cities with complete prices and weather, recommend the lowest-cost `GO` city; if none exist, recommend the lowest-cost `CAUTION` city with the warning; if all are `NO_GO`, return no winner. Exclude cities with unresolved required-source failures.
- The coordinator owns a 30-second end-to-end deadline. Propagate remaining time to workers; permit at most one retry for explicitly retryable, idempotent operations with backoff inside that deadline. Reuse A2A work via a request idempotency key after uncertain completion; never launch duplicate work or retry authentication/validation errors.
- Return HTTP 200 for complete or partial comparisons, 4xx for caller/authentication errors, 502 when providers return no usable comparison, and 504 when the coordinator deadline expires. Agents use the same result/error envelope and map A2A task outcomes consistently.

## 4. Proposed implementation structure

The repository currently has no application source, dependency manifest, tests, Docker Compose file, or Azure infrastructure. This is a target layout to create; it is not an inventory of existing code.

```text
src/travel_comparator/
  api/                 # REST routes, authentication boundary, request/response schemas
  cli/                 # local adapter over application service
  application/         # coordinator use cases, fan-out, conflict detection, synthesis
  contracts/           # canonical request/result and protocol-boundary schemas
  agents/
    weather/           # Weather A2A service and bundled MCP process lifecycle
    travel/            # Travel Advisor A2A service and reference-data access
  providers/
    openai/            # model client adapter
    nws/               # weather-source adapter
data/
  travel_data.json     # reviewed, versioned MVP reference data
tests/
  unit/
  contract/
  integration/
  e2e/
deploy/
  compose.yaml         # laptop topology
  bicep/               # Azure resources and role assignments
.github/workflows/     # validation, image build, deployment
```

Keep dependencies flowing inward: adapters depend on application/domain contracts; domain logic does not depend on FastAPI, Azure SDKs, the OpenAI SDK, or transport frameworks. Document typed per-service configuration keys, required/optional settings, local/cloud endpoint mappings, and startup validation. Fail startup when required values are missing; never silently choose a production endpoint. Do not add a shared database or message broker until durable or asynchronous business requirements require one.

## 5. Local development and test architecture

The laptop environment is the first supported deployment target. Implement the services as containers and run them through Docker Compose so service names, ports, startup order, and environment configuration match the cloud topology as closely as practical.

**Target local workflow (after the application scaffold and Compose file are implemented):**

1. Install Python 3.14.x and Docker Desktop/Engine with Compose. Confirm the selected A2A and provider SDK releases support the pinned runtime.
2. Create a local environment file from a checked-in example. Keep the actual file out of source control; use a developer-owned OpenAI key.
3. Start the coordinator/API, Weather Agent (with its MCP child process), and Travel Advisor with `docker compose up --build`.
4. Run unit and contract tests without external credentials, then run integration tests against deterministic NWS/OpenAI stubs. Use a small, explicit smoke test with live providers only when needed.
5. Stop the stack with `docker compose down`. Do not put secrets in command history, test snapshots, logs, or committed fixtures.

Use Python 3.14.x and `uv` for dependency management, then commit `uv.lock` and pin the tested image digest before producing a release. Confirm that the chosen A2A and provider SDKs support this runtime. Treat FastAPI 0.142.2 as the current candidate on 2026-10-03, not as a tested lockfile pin; confirm compatibility before locking. Keep provider clients behind narrow adapters so unit and contract tests do not need live services. The execution guide currently describes manual terminal startup; update it to match the Compose workflow when implementation begins.

### Required test layers

| Layer | Required coverage |
| --- | --- |
| Unit | Query parsing/validation, conflict detection, pricing/event calculations, synthesis input shaping, timeout/error handling |
| Contract | A2A Agent Cards and task payloads, MCP tool input/output, API request/response schemas, compatibility fixtures |
| Integration | Compose startup, internal service discovery, Weather Agent-to-MCP lifecycle, external-provider adapters with stubs |
| End-to-end | Representative budget, weather-risk, event-conflict, and multi-city comparisons; verify no unsupported data is presented as fact |
| Security/release | Dependency and container scanning, secret scanning, input-size/rate limits, auth-negative tests, SBOM generation |
| Resilience | Worker timeout/unavailability, model API throttling, malformed agent/model output, graceful shutdown, bounded retry behavior |

Live integration tests must be separately selected and must not be a prerequisite for deterministic pull-request checks.

## 6. Security, privacy, and reliability baseline

### MVP security controls

- **Identity and access:** Require the `TravelComparator.User` Entra ID application role for cloud callers, assigned explicitly; deny anonymous access and self-registration. Each Container App uses a distinct managed identity; A2A workers validate issuer, audience, expiry, and the `invoke` role and authorize only the coordinator identity.
- **Local trust:** Run the direct CLI as the developer's signed-in OS user. Bind the API to loopback in laptop mode; Compose workers require a distinct local-only coordinator credential. Never reuse local credentials in Azure, include secret files in images, or pass provider credentials to the MCP child process.
- **Ingress:** Only the coordinator/API app may have external ingress. Worker apps use internal ingress and must not be targets of environment-level HTTP routes, gateways, or alternate public endpoints. Validate this invariant in Bicep tests and with an external reachability smoke test.
- **Secrets:** `.env`/local secret files are ignored by Git and created from examples with placeholders only. Store the OpenAI credential in Key Vault; only the coordinator identity may read it. Use managed identity, rotate provider credentials, and never put secrets in prompts, A2A payloads, logs, image layers, or MCP subprocess environments.
- **Input and agent safety:** Bound request sizes, validate city/date values and schemas, reject unsupported tool requests, constrain outbound hosts, and treat prompt instructions and agent output as untrusted data.
- **Provider data minimization:** Send OpenAI only the normalized trip fields needed to generate the recommendation. Do not send secrets, payment data, or unnecessary personal data to OpenAI or other third parties. Do not log full prompts or responses; confirm provider retention, training, and data-processing terms before production.
- **Egress:** Restrict application clients to configured HTTPS provider hosts: coordinator to OpenAI, Weather Agent to NWS, and no provider egress from the Travel Advisor. Enforce the destination allow-list in code/configuration, validate TLS certificates, block private/link-local/metadata addresses, and reject redirects to unapproved hosts. Choose network-level egress enforcement before production and account for its cost.
- **Transport and exposure:** HTTPS at public ingress; workers have internal-only ingress; no debug interface or MCP endpoint is public.
- **Telemetry:** Propagate a generated server-side request/task ID. Log only allow-listed service, duration, status, and error-category fields; exclude raw request/response bodies, prompts, itinerary/location fields, authorization headers, provider exception bodies, PAN/CVV, payment tokens, and secrets. Sanitize untrusted strings and set production retention/access policies.
- **Abuse and spend controls:** Enforce caller rate limits, request/time limits, maximum city count, bounded parallelism, retry budgets, and OpenAI token/cost budgets.
- **Supply chain:** Lock dependencies, scan source/dependencies/images, generate an SBOM, and deploy immutable reviewed image digests.

### Reliability behavior

Every outbound request has a deadline and bounded retries with backoff for retryable failures. Do not blindly retry non-idempotent work. Limit parallel fan-out to validated input counts. Expose health/readiness checks and graceful shutdown. Return explicit per-agent failure information; partial results must be visibly incomplete. Record and monitor request latency, failure rate, timeout rate, agent availability, model-token usage, and estimated provider spend. Define numeric SLOs and alert thresholds before production; none are specified by the current requirements.

### PCI DSS future readiness (not compliance)

**MVP boundary:** The comparator has no payment capability and must not accept or retain PAN, expiration date, security code, track/chip, PIN/PIN block, or payment tokens. Reject structured payment fields before orchestration and apply conservative PAN detection to free text; detection is best-effort and does not make arbitrary payment data safe to process. Never place payment data in prompts, agent messages, reference files, logs, traces, analytics, or support exports. Do not build a card-number field or payment-data store.

**If payment is added later:**

1. Prefer provider-hosted payment pages/fields and tokenization so the application receives only provider tokens and non-sensitive status metadata; never handle CVV.
2. Put payment orchestration and provider webhooks behind a separately reviewed boundary. Keep card-entry components, payment secrets, and payment logs outside the agent workflow.
3. Hosted/tokenized capture does not by itself determine PCI DSS scope or establish compliance. Reassess the complete data flow, network segmentation, identity, logging, retention, vulnerability management, incident response, and evidence requirements against the then-current standard before payment design or deployment.
4. Confirm scope and validation requirements with a qualified PCI assessor/acquirer; complete the required independent assessment and remediation.

This is a design direction for reducing future scope, not an attestation, certification, guarantee of reduced scope, or substitute for a formal PCI DSS assessment.

## 7. Azure deployment topology

Deploy the same immutable application images built and tested from the local project. Start with one Azure Container Apps environment on the Consumption plan:

```mermaid
flowchart TB
    client[Client]
    identity[Microsoft Entra ID]
    coordinator[ACA: Coordinator and API<br/>authenticated external ingress]
    weather[ACA: Weather Agent<br/>internal ingress]
    travel[ACA: Travel Advisor Agent<br/>internal ingress]
    keyvault[Azure Key Vault]
    registry[Azure Container Registry]
    monitor[Log Analytics and Application Insights]
    openai[OpenAI API]
    nws[NWS API]

    client -->|OIDC access token over HTTPS| coordinator
    identity -->|issues token| client
    coordinator -->|A2A over internal ACA networking| weather
    coordinator -->|A2A over internal ACA networking| travel
    weather -->|MCP stdio child process| nws
    coordinator --> openai
    keyvault -->|secret reference / managed identity| coordinator
    registry -->|immutable image digest| coordinator
    registry -->|immutable image digest| weather
    registry -->|immutable image digest| travel
    coordinator --> monitor
    weather --> monitor
    travel --> monitor
```

| Resource / boundary | MVP deployment rule |
| --- | --- |
| Azure Container Apps environment | Separate isolated environments for development and production; use the Consumption plan initially. Keep resource names, settings, and limits in infrastructure-as-code. |
| Coordinator/API app | Only app with external ingress. Require OIDC authentication and the `TravelComparator.User` role; enforce request-size and rate limits at the API boundary. |
| Weather and Travel Advisor apps | Internal ingress only; never route them through an environment-level public HTTP route. Validate A2A access tokens and allow only the coordinator's managed identity with the `invoke` role. |
| Container registry | Store scanned images; deploy by immutable digest, not mutable `latest` tags. |
| Secrets | Store the OpenAI credential in Key Vault; grant read access only to the coordinator managed identity. Never bake secrets into images or Bicep parameters. |
| Telemetry | Send structured logs, metrics, and traces to Azure Monitor/Log Analytics. Apply retention and access controls; redact sensitive values before export. |
| Network egress | Allow only configured HTTPS destinations: coordinator to OpenAI, Weather Agent to NWS, and Travel Advisor to none. Review provider domains and implement network-level egress enforcement before production. |
| Configuration | Keep non-secret configuration separate from secrets. Use distinct development and production identities, secrets, and data. |

Scale based on HTTP concurrency and observed load with explicit minimum/maximum replica bounds. Scale-to-zero is the cost-effective MVP default when occasional cold starts are acceptable. Before production, decide latency/availability objectives and set a minimum replica if the cold-start behavior conflicts with them. Add request and concurrency limits, per-principal rate limits, budgets/alerts, and model-token caps before exposing the API; do not assume scaling limits alone cap provider charges.

### Build, deploy, and rollback

1. Pull requests run formatting/linting, unit and contract tests, authentication-negative tests, secret/dependency checks, infrastructure validation, and a check that no worker route is public.
2. A protected main-branch workflow builds each container once, scans it, produces an SBOM, and pushes a content-addressed image to ACR.
3. GitHub Actions authenticates to Azure using workload identity federation/OIDC; no long-lived cloud deployment secret is stored in repository settings.
4. Bicep provisions the ACA environment and supporting resources. Deploy the exact image digest to a development environment and run smoke/health checks.
5. Promote the same digest to production only after explicit approval and environment-specific checks. Require passing authentication/authorization tests before external ingress is enabled. Use ACA revisions/traffic shifting for controlled rollout and rollback to a known-good revision.
6. Restrict production deployment permissions; audit deployment identity and configuration changes. Validate that only the coordinator has external ingress and that no environment-level route can target a worker.

Keep infrastructure changes reviewable and repeatable. Avoid manual-only portal configuration for resources, identity permissions, network boundaries, or secrets.

## 8. Data ownership and retention

The MVP has no shared database. `travel_data.json` (or its replacement reference dataset) is owned by the Travel Advisor and versioned/reviewed with the application. Weather results are owned by the Weather Agent and sourced from NWS. Comparison requests and results are transient and request-scoped; do not add persistent user history without an explicit retention, privacy, tenancy, and deletion design.

Each result should identify its source and relevant freshness/time window. Keep source data separate from model-generated wording so the final response can be checked against structured evidence. External API outages or stale reference data must be represented as such.

## 9. Delivery sequence and open decisions

1. Scaffold the Python application, lock dependencies, define canonical schemas, and implement deterministic unit/contract tests.
2. Implement the coordinator, worker boundaries, REST API and CLI adapters; retain explicit provider clients and stubs.
3. Add Dockerfiles and Compose; prove local startup, health checks, external-provider stubs, and representative end-to-end scenarios.
4. Add Bicep and Azure dev deployment, Entra ID auth, ACR, Key Vault references/managed identity, internal service routing, telemetry, budgets, and deployment workflow.
5. Measure real latency/cost and set SLOs, rate limits, replica bounds, retention, and alerts before production rollout.
6. Before any payment feature, obtain a payment/data-flow design and qualified PCI scope assessment.

Decisions intentionally left to implementation/product discovery: exact client sign-in journey and any roles beyond `TravelComparator.User`; production SLOs and load; Azure region and network/private-endpoint requirements; network-level egress design and cost; operational retention/alert thresholds; commercial data-provider licensing/freshness; and any future payment scope. Do not treat these as already resolved.

## 10. Verified technology references

- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/) — current released version 1.0.0 at the time of architecture.
- [Model Context Protocol Specification](https://modelcontextprotocol.io/specification/) — specification served as version 2026-07-28 at the time of architecture.
- [Azure Container Apps overview](https://learn.microsoft.com/en-us/azure/container-apps/overview), [scaling](https://learn.microsoft.com/en-us/azure/container-apps/scale-app), [service communication](https://learn.microsoft.com/en-us/azure/container-apps/connect-apps), [ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview), [managed identities](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity), and [secrets](https://learn.microsoft.com/en-us/azure/container-apps/manage-secrets).
- [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/) and [PyPI project](https://pypi.org/project/fastapi/). The target framework/runtime versions in the spine must be locked and revalidated when implementation starts.
- [Python version status](https://devguide.python.org/versions/) — Python 3.14 is in bug-fix support as of 2026-10-03; pin the tested image digest and recheck A2A/provider SDK compatibility.
- [PCI Security Standards Council document library](https://www.pcisecuritystandards.org/document_library/). Use the current official standard and applicable validation documents when payment scope is defined.
