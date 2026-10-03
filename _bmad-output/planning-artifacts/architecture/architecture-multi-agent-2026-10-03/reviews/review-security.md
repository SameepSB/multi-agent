# Security Architecture Review

**Artifact:** `ARCHITECTURE-SPINE.md`  
**Review scope:** Secured MVP that avoids PCI scope now and preserves future PCI DSS readiness. This is architecture feedback, not an application-code vulnerability audit.

## Verdict

The spine has sound security intent: it calls for API identity and authorization, bounded protocol data, constrained tools and destinations, managed identity and Key Vault, redacted telemetry, and an explicit no-cardholder-data MVP. However, it does not yet define enough of the actual trust-boundary controls to implement or expose the MVP safely. Resolve the access model, worker identity, egress/provider handling, and payment-flow constraints as implementation gates; the current deferrals leave important controls unspecified.

## Findings

### 1. Define the API authorization model before external exposure

**Location:** AD-5; Deferred — “Exact Entra ID client sign-in/authorization roles and production edge/WAF requirements”

AD-5 requires authorization, but the concrete identity, roles, and authorization rules are deferred. Authentication alone does not define who may compare trips, whether access is tenant- or user-scoped, or which operations a caller may invoke. The deferral says to settle this before exposure, but does not establish a minimum MVP policy or deployment gate.

**Recommendation:** Specify the MVP client identity flow and deny-by-default authorization policy (including any single-user or allowlisted-user assumption), token issuer/audience and required claims, and where the policy is enforced. Make successful policy tests a prerequisite to enabling public ingress.

**Consequence:** Implementations can satisfy “OIDC” while accepting any authenticated identity or applying inconsistent authorization across adapters.

### 2. Authenticate and authorize coordinator-to-worker calls

**Location:** AD-2, AD-4; Structural Seed — deployment diagram

“Internal ingress” and configured A2A endpoints constrain network reachability, but do not authenticate the coordinator to each worker or authorize a caller at the worker. The spine does not define workload identities, A2A token validation (issuer, audience, scope/role), or how a worker rejects direct or cross-service callers. The Compose service network also should not be treated as an identity boundary.

**Recommendation:** Define per-workload identity for the coordinator and each agent, mutually authenticated A2A calls or equivalent signed/audience-bound credentials, and worker-side caller authorization. State that agent ingress is private and authenticated in both ACA and local deployments; keep runtime identities separate and least-privileged.

**Consequence:** Any workload or compromised component with network reachability may be able to invoke a worker, impersonate the coordinator, or bypass coordinator policy.

### 3. Make local CLI and local service trust assumptions explicit

**Location:** AD-1, AD-4; Structural Seed — client-to-service diagram

The CLI adapter calls the application service while the REST adapter is described as authenticated. The architecture does not state whether local CLI access is intentionally equivalent to an authenticated user, whether it can call local HTTP endpoints without authentication, or how developer credentials and local service configuration are isolated. “Same container contracts” does not itself ensure equivalent security.

**Recommendation:** Document the local threat model and allowed trust boundary: identify the OS user as the local principal if that is the intent, prevent accidental unauthenticated network exposure, and make development-only credentials/configuration distinct from production identity. Specify that local secret files are excluded from images, source control, and tool subprocess environments.

**Consequence:** Local-only assumptions can leak into a deployed profile, or local processes and containers can use credentials and interfaces more broadly than intended.

### 4. Specify MCP process isolation and untrusted tool-result handling

**Location:** AD-2, AD-5; Structural Seed — Weather Agent to bundled weather tools

An explicit MCP tool allowlist limits tool selection, but the architecture does not constrain the launched process, arguments, inherited environment, filesystem/network access, resource use, or tool-result interpretation. “Treating model/agent output as untrusted” is an invariant, but does not say how external tool data is prevented from changing tool policy or becoming executable instructions or destinations.

**Recommendation:** Pin the permitted MCP server executable and tool schemas; prohibit shell construction and dynamic tool discovery; run the server with least privilege, bounded resources, and only necessary environment/network access. Validate tool inputs and outputs, treat NWS/tool content as untrusted data, and do not let model or agent output authorize new tools, hosts, or side effects.

**Consequence:** A compromised or manipulated tool result, unsafe argument, or over-privileged server process can escape the intended read-only weather boundary.

### 5. Establish data-minimization and provider-handling rules

**Location:** AD-5, AD-7, AD-8; Structural Seed — application service to OpenAI API

The diagram sends application data to OpenAI, but the spine does not define what user/trip fields or agent results may be sent, whether prompts are retained or used for training, the applicable provider settings/contract, or how provider errors and responses are handled. The no-cardholder-data rule is not a complete policy for personal travel data such as locations, dates, or itinerary details.

**Recommendation:** Inventory each outbound provider payload and classify fields; send only the minimum needed, prohibit credentials and payment data, and document provider retention/training controls, contractual terms, residency requirements, and deletion expectations. Apply the same restrictions to prompts, completions, retries, and diagnostic/error paths.

**Consequence:** Sensitive user data may leave the system without an explicit approved purpose or retention/handling boundary, even when the system never receives card data.

### 6. Define enforceable outbound network and destination controls

**Location:** AD-2, AD-5, AD-6; Structural Seed — provider/tool destinations and deployment diagram

“Constrain service destinations” is not translated into an egress policy. The diagram includes OpenAI and NWS, while the coordinator also calls configured A2A endpoints; it is unclear whether arbitrary URLs, redirects, DNS changes, or private/link-local destinations can be reached, or how TLS is required. The Deferred section postpones private endpoints and advanced segmentation without stating the minimum outbound controls for the MVP.

**Recommendation:** Enumerate permitted outbound hosts and ports for each workload and enforce them at the application and deployment/network layers where supported. Require certificate-validated TLS, reject redirects to unapproved destinations, prevent user/model-controlled URLs and private/link-local/metadata access, and document the minimum ACA network posture or compensating control.

**Consequence:** A configuration or input-handling mistake can turn a worker into an unintended network proxy, expose cloud metadata, or send data to an unapproved endpoint.

### 7. Separate runtime secrets and deployment credentials by principal

**Location:** AD-5, AD-9; Consistency Conventions — Configuration and secrets

Managed identity and Key Vault are named, but the architecture does not specify which workload identity can read which secret, how credentials are rotated/revoked, or how deployment OIDC permissions are separated from runtime permissions. It also does not state that secrets must not be passed to agent prompts or inherited by MCP child processes.

**Recommendation:** Assign distinct least-privilege identities to API/coordinator/workers and deployment automation; scope Key Vault access to only required secrets and name the rotation/revocation process. Explicitly prohibit secrets in prompts, A2A payloads, logs, image layers, and tool-process environments unless a documented tool contract requires a narrowly scoped credential.

**Consequence:** A compromised worker, tool, or deployment workflow may gain access to credentials and resources beyond its function.

### 8. Extend telemetry controls to personal data and diagnostic paths

**Location:** AD-7; Consistency Conventions — Reliability and telemetry

AD-7 names credentials, tokens, payment data, and full prompts, but not other personal/request data, provider response bodies, exception text, URLs/query parameters, or tracing attributes. “Redacted by default” does not identify an allowlisted telemetry schema, retention period, or access policy. A generated correlation ID is useful but should not be a user-controlled substitute for authorization or tenant context.

**Recommendation:** Define an allowlist of logged fields and explicitly exclude raw request/response bodies, prompts, itinerary/location fields, tokens, and provider exception payloads unless separately approved and redacted. Set retention and access controls, sanitize untrusted strings, and keep correlation identifiers non-sensitive and generated server-side.

**Consequence:** Operational diagnostics can become an unintended personal-data or payment-data store and increase breach impact or PCI scope.

### 9. Set a minimum public-ingress and abuse-control baseline

**Location:** AD-4; Deferred — “production edge/WAF requirements”

The spine states that only the authenticated API has external ingress, while deferring production edge/WAF requirements. It does not clarify the ACA ingress exposure mode, TLS termination/redirect policy, request-size and rate limits, or protection against abusive unauthenticated traffic. An edge WAF may be optional for this MVP, but the minimum API controls should not be left implicit.

**Recommendation:** Specify the exact ingress path and TLS boundary; keep workers non-public; require authentication before expensive orchestration/provider calls; bound request size, concurrency, and per-principal request rates; and define whether a WAF/API gateway is required or explicitly not required for the initial exposure.

**Consequence:** Public ingress can permit resource exhaustion or excessive third-party API spend even when identity checks are correctly implemented.

### 10. Tighten the PCI exclusion and future-readiness statement

**Location:** AD-5, AD-8; Deferred — “Payment implementation and PCI DSS scope/assessment”

AD-8 is a strong and appropriately explicit non-compliance caveat: the MVP must not handle cardholder data, and the spine does not claim PCI DSS compliance. The future suggestion to use “provider-hosted/tokenized capture,” however, could imply that tokenization alone guarantees out-of-scope status. The spine does not define which payment data is prohibited or how a later integration is evaluated across API payloads, logs, model/provider flows, infrastructure, and supporting services.

**Recommendation:** State that the MVP does not accept or route PAN, expiration date, security code, track/chip, PIN/PIN block, or payment tokens unless a separate approved architecture explicitly permits them; reject rather than forward unexpected payment fields. For a future payment feature, require a documented data-flow and scope assessment before design/deployment, confirm provider/service-provider responsibilities and applicable validation with the assessor/acquirer, and do not claim PCI scope reduction solely from hosted capture or tokenization.

**Consequence:** An unexpected payment field or future tokenized flow may enter systems thought to be excluded, while the architecture or product is incorrectly represented as PCI-compliant or out of scope.

## Positive controls retained

- AD-5 establishes security controls at every trust boundary and calls for bounded typed input/output, destination and tool constraints, managed identity, and Key Vault.
- AD-7 requires generated correlation IDs and redaction rather than logging full prompts by default.
- AD-8 explicitly prohibits cardholder-data handling in the MVP and says the spine does not claim PCI DSS compliance.
- AD-4 intends to expose only the coordinator/API and keep agent ingress internal.
- AD-9 requires immutable-image promotion and OIDC-based deployment automation.

