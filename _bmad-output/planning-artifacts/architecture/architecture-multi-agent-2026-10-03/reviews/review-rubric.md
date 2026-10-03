# Architecture Spine Rubric Review

**Target:** `ARCHITECTURE-SPINE.md`  
**Inputs checked:** accepted choices in `.memlog.md`, `readme.md`, and `Travel_Comparator_execution_steps.md`  
**Verdict:** **Needs revision.** The spine captures the main architecture and passes the mechanical lint, but material policy and environment gaps still allow divergent implementations.

## Material gaps

1. **Agent boundaries and workflow policy:** Require authorization for internal coordinator-to-agent calls. Clarify whether capability discovery uses Agent Cards from configured trusted endpoints, and define or explicitly defer the coordinator's conflict-follow-up triggers and failure-versus-partial-result policy.
2. **Payment-data ingress:** The prohibition is not operationalized for free-form user input. Require detection/rejection or removal before prompts, agent messages, and telemetry; explicitly exclude PAN/CVV from those paths.
3. **Deployment and operations envelope:** Decide or explicitly defer dev/prod environment isolation and identity/secret/data separation. Carry forward required caller rate limits, city/request bounds, provider spend caps, monitoring/retention/alert decisions, and data freshness/licensing policy; set operational limits before production.
4. **Release gates:** “Validate tests/scans” does not require the source-defined security/release checks or production approval. State mandatory CI gates and authorized production promotion while retaining immutable-digest promotion and rollback.

The extra ports/adapters diagram is a candidate to remove for seed minimality; the FastAPI patch pin should be labeled provisional or deferred consistently. These are secondary to the material gaps above.

**Validation:** `lint_spine.py` passed with 0 findings. No edits were made to the spine.
