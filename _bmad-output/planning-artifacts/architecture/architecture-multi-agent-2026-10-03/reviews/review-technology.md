# Technology and deployment claims review

**Reviewed:** 2026-10-03  
**Artifact:** `ARCHITECTURE-SPINE.md`  
**Scope:** Protocol versions, Python/FastAPI selections, and Azure Container Apps deployment claims. The spine was not edited.

## Verdict

The protocol versions and FastAPI patch listed are current against the cited primary sources on the review date. Python 3.12 remains in security support, but is no longer the current feature-release line; the selected runtime needs its compatibility rationale made explicit. Two precision issues remain: the exact FastAPI patch conflicts with the spine’s stated deferral of patch-level selection, and “internal-only” agent ingress omits an Azure routing exception. ACA Consumption, scale-to-zero, immutable revisions, and digest-based deployment are generally supportable claims, subject to the ingress qualification below.

## Findings

### 1. Python selection is supported, but not the current feature line

**Location:** Stack, line 96

Python 3.12 was still supported on 2026-10-03, so `3.12.x` is not an invalid or end-of-life selection. However, Python.org identifies 3.12.15 (released 2026-09-30) as a security release in the security-fixes-only phase, says it no longer receives regular bug fixes or binary installers, and identifies Python 3.14 as the latest feature-release series. The spine does not say whether 3.12 is chosen for dependency/platform compatibility or merely as a current version, and `3.12.x` also leaves the patch/build to be selected later.

**Recommendation:** State that 3.12 is an intentional compatibility choice and record its security-only lifecycle, or evaluate the current feature series. In either case, select and test an exact interpreter/container base during implementation.

### 2. FastAPI patch is current, but conflicts with the explicit deferral

**Location:** Stack, line 97; Deferred, line 150

FastAPI’s official release notes list `0.142.2`, dated 2026-09-30, as the latest release shown on the review date, so the value is not stale. But the stack pins that exact patch while Deferred says exact package patch releases are deferred and should be locked during implementation. This makes the architecture both select and defer the same decision; the document also does not state that this patch has been tested with the selected Python/runtime.

**Recommendation:** Treat `0.142.2` as a dated candidate/current reference rather than an adopted pin, or move patch-level selection to the implementation lock and document the tested Python/FastAPI combination there.

### 3. “Internal-only” ingress needs an explicit routing guard

**Location:** AD-4, line 49; Deployment convention, line 90; structural diagram, line 122

Azure documents internal ingress as making an app FQDN reachable only within its Container Apps environment, but explicitly notes that an app with internal ingress can still receive external traffic when targeted by an environment-level HTTP route. Therefore, “Internal-only agent ingress” is not by itself a complete guarantee that agent apps cannot be reached from outside. The spine does not explicitly prohibit routes from exposing worker apps.

**Recommendation:** Require that environment-level HTTP routes, gateways, and other external paths never target agent apps; keep only the intended coordinator/API on externally reachable paths, and verify that rule in deployment configuration and tests.

## Claims checked and found supported

- **A2A `1.0.0`:** The official A2A site publishes the v1.0.0 documentation and describes v1.0 as its first stable, production-ready release. This is a valid protocol baseline; the spine does not claim it is the newest release.
- **MCP `2026-07-28` over stdio:** The official MCP release announcement says this is the next specification version, and the versioned specification includes a stdio transport. This date-form specification version and transport pairing are valid.
- **ACA Consumption and scale-to-zero:** Microsoft documents Consumption as a serverless plan/profile that supports scale-to-zero; its scaling guide documents a default minimum of zero. The spine appropriately conditions scale-to-zero on accepting cold-start latency. Confirm the actual scale rule and replica settings during implementation.
- **Revisions and image digests:** Microsoft describes Container Apps revisions as immutable snapshots and documents updating the app image. Azure CLI accepts digest-form image references; using the same image digest in separate environments is a reasonable promotion strategy, while each environment still has its own app configuration/revision.

## Sources

Primary sources consulted on 2026-10-03:

1. Python.org, [Python 3.12.15 release](https://www.python.org/downloads/release/python-31215/) — release date, security-only status, installer status, and current feature series.
2. FastAPI, [Release notes](https://fastapi.tiangolo.com/release-notes/) — `0.142.2` release date and the latest listed releases.
3. A2A, [v1.0 announcement](https://a2a-protocol.org/v1.0.0/announcing-1.0/) and [v1.0.0 documentation](https://a2a-protocol.org/v1.0.0/) — stable v1.0 release and versioned specification.
4. MCP, [2026-07-28 release announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/), [specification](https://modelcontextprotocol.io/specification/2026-07-28), and [stdio transport](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio).
5. Microsoft Learn, [Container Apps plan types](https://learn.microsoft.com/en-us/azure/container-apps/plans), [workload profiles](https://learn.microsoft.com/en-us/azure/container-apps/workload-profiles-overview), and [scaling](https://learn.microsoft.com/en-us/azure/container-apps/scale-app) — Consumption behavior and scaling.
6. Microsoft Learn, [Container Apps ingress](https://learn.microsoft.com/en-us/azure/container-apps/ingress-overview) — internal ingress semantics and the environment-level HTTP routing exception.
7. Microsoft Learn, [Container Apps revisions](https://learn.microsoft.com/en-us/azure/container-apps/revisions) and [revision management](https://learn.microsoft.com/en-us/azure/container-apps/revisions-manage); [Azure CLI `containerapp`](https://learn.microsoft.com/en-us/cli/azure/containerapp) — immutable revisions and image update workflow.
