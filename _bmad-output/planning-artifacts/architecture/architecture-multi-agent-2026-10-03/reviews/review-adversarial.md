# Adversarial Architecture Spine Review

**Verdict:** The spine establishes useful boundaries, but independent implementations can satisfy its current rules and still disagree on wire behavior, authorization, result handling, recommendation outcomes, retry behavior, and runtime configuration. Amend the relevant ADs or add binding conventions before parallel implementation.

**Scope:** Adversarial compatibility review of the adopted rules and consistency conventions in `ARCHITECTURE-SPINE.md`. Each finding gives a pair of plausible implementations that both follow the stated rules. Only material interoperability or behavior gaps are included.

## Findings

### 1. Canonical API/A2A schemas and domain semantics are not fixed

- **Location:** AD-2, AD-5; Consistency Conventions — Naming and interfaces; Data and errors
- **Trigger condition:** Two implementations create their own “typed” API/A2A payloads because the spine specifies protocols and broad response attributes, but not canonical field names, required/optional/null semantics, units, date/time-zone rules, currency, or schema evolution.
- **Pair:** One Weather Agent returns `temperature_c` and an ISO timestamp in the destination time zone; another returns `temperature` plus a unit and a UTC timestamp. Both validate bounded typed output and use A2A 1.0.0, but consumers cannot safely interpret or substitute one for the other. Likewise, two coordinators can normalize a date-only travel request against different time zones while both claiming to normalize it.
- **Guard / required change:** Add a versioned canonical request, agent-result, and API-response schema (or a binding schema artifact), including units, date/time semantics, nullability, enums, and compatibility/evolution rules. Require both adapters and agents to conform to it.
- **Potential consequence:** Individually valid implementations produce incompatible payloads or materially different comparisons; integration requires undocumented translation and can silently misstate conditions or costs.

### 2. Failure, partial-result, and HTTP semantics are underspecified

- **Location:** AD-6; Consistency Conventions — Data and errors
- **Trigger condition:** “Source-specific failure” and “explicitly marked partial result” do not define a shared error taxonomy, A2A task outcome mapping, or how the coordinator maps those outcomes to the REST response.
- **Pair:** One agent reports a source outage as a successful A2A task containing `availability=unavailable`; another reports the same outage as a failed task with an error category. Both explicitly report the source failure and neither invents data. A coordinator may return a partial comparison with HTTP 200 for either representation, while another may map the failed task to HTTP 502 or reject the whole comparison.
- **Guard / required change:** Specify canonical error/availability categories and result envelope, task-state-to-result mapping, partial-result policy, and REST status/body semantics (including when a request is a failure versus a successful partial response).
- **Potential consequence:** Clients cannot reliably distinguish complete, partial, and failed comparisons; retries, UX, and monitoring behave differently across otherwise conforming implementations.

### 3. Service-to-service authentication and API authorization contracts are incomplete

- **Location:** AD-4, AD-5; Deferred — exact Entra ID client sign-in/authorization roles
- **Trigger condition:** The spine requires authenticated API access and internal-only worker ingress but does not bind the identity mechanism, token audience/claims, or authorization policy for coordinator-to-agent calls. The deferred external-client roles also leave the public API contract unsettled.
- **Pair:** One coordinator relies on ACA internal ingress/network isolation and sends A2A calls without a service credential; another obtains a workload-identity token and requires a specific audience on every agent call. Both keep worker ingress internal and enforce typed input/output at protocol boundaries. They cannot communicate when deployed together. Similarly, API implementations can accept any valid OIDC identity versus require an agreed role/scope.
- **Guard / required change:** Define the required authentication and authorization contract for public API clients and internal service calls: accepted issuer/audience, token acquisition/propagation, per-service identity/authorization, and unauthenticated local-development behavior. Resolve the deferred client role policy before external exposure.
- **Potential consequence:** A secure implementation can reject another conforming service at runtime, or an internally reachable worker can accept calls without verified service identity; API clients also face incompatible access requirements.

### 4. Retry and idempotency behavior can amplify work or change outcomes

- **Location:** AD-6; Consistency Conventions — Reliability and telemetry
- **Trigger condition:** “Bounded retry policy,” “retry only safe operations,” and “retry budgets” provide no common attempt/time budget, backoff, retryable error set, or idempotency/replay contract.
- **Pair:** One coordinator retries a timed-out A2A request once after a short backoff; another retries it several times within its own bounded deadline. Both retry only operations they judge safe. If the first agent task is still running when the retry arrives, the second implementation can launch duplicate model/tool work, incur extra cost, or receive two different results.
- **Guard / required change:** Set shared per-operation retry limits and deadline budgets, retryable error categories, backoff rules, and an idempotency key/task-reuse contract for calls whose completion is uncertain. Define how retry budgets compose across coordinator, agent, and provider layers.
- **Potential consequence:** Duplicate work and cost, inconsistent results, and one implementation timing out while another returns success for the same request.

### 5. Coordinator synthesis and conflict resolution lack deterministic rules

- **Location:** AD-1; AD-3
- **Trigger condition:** The coordinator is assigned synthesis and conflict-follow-up ownership, but the spine does not specify which result fields are authoritative, what constitutes a conflict, or how competing recommendations are resolved.
- **Pair:** Two coordinators receive the same valid but conflicting weather and travel-agent recommendations. One treats an explicit source warning as a conflict and requests follow-up; the other compares only normalized recommendation fields and does not. If follow-up does not resolve it, one favors the Travel Advisor while the other favors the Weather Agent. Both keep agents from invoking one another and leave final recommendation ownership with the coordinator.
- **Guard / required change:** Add a binding synthesis convention covering conflict detection, follow-up conditions, source authority per field, and deterministic handling of unresolved or missing inputs; specify which fields agents may recommend versus decide.
- **Potential consequence:** The same inputs can produce incompatible final recommendations and follow-up calls across implementations, defeating the stated goal of a single coherent comparison workflow.

### 6. The shared container/configuration contract is not operationally defined

- **Location:** AD-4, AD-9; Consistency Conventions — Configuration and secrets; Deployment
- **Trigger condition:** “Same container contracts,” service-name networking, environment-specific settings, and digest promotion do not define required setting names, types, defaults, validation, or endpoint-discovery behavior.
- **Pair:** One coordinator image expects `WEATHER_AGENT_URL` and defaults locally to `http://weather:8000`; another expects `A2A_WEATHER_ENDPOINT` and requires an explicit value. Both use the same immutable image in Compose and ACA, keep secrets out of images, and use configured service endpoints. The first starts in Compose while the second fails, or an environment supplies a setting name only one recognizes.
- **Guard / required change:** Define a versioned configuration contract for each service: canonical keys, types, required/optional status, allowed defaults, local/cloud endpoint mapping, startup validation, and secret-versus-non-secret classification.
- **Potential consequence:** A promoted image may fail to start or silently target the wrong service in an environment despite following the stated deployment strategy.
