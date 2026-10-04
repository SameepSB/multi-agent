# Travel Comparator — Runbook

The runnable implementation lives in this repository and uses Python 3.14, `uv`, Docker Compose, and Azure Container Apps. The CLI and authenticated REST API share the same request-scoped coordinator. The coordinator calls private Weather and Travel Advisor A2A agents; the Weather Agent owns a weather-tools MCP child over stdio.

Example question:

> Compare Austin, Miami, and Denver for a 5-day trip from New York.

## Local setup

Prerequisites: Docker with Compose, Python 3.14, and `uv` for local tests/CLI tooling. From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env`. Replace `LOCAL_API_TOKEN` and `LOCAL_COORDINATOR_TOKEN` with **different** random values of at least 24 characters. Keep `STUB_PROVIDERS=true` for the no-credential demo; `OPENAI_API_KEY=replace-me` is not used in stub mode. Never commit `.env`.

Build and start the API and agents:

```powershell
docker compose --env-file .env -f deploy/compose.yaml up --build -d
docker compose --env-file .env -f deploy/compose.yaml ps
```

Only the API is published, on loopback at `127.0.0.1:8080`. The workers are reachable only on the Compose network. Readiness discovers both agents:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health/ready
```

### Run the CLI

The API container has the same settings and can reach the private worker services:

```powershell
docker compose --env-file .env -f deploy/compose.yaml exec api travel-comparator "Compare Austin, Miami, and Denver for a 5-day trip from New York"
```

In stub mode, CLI query parsing is deterministic and does not call OpenAI.

### Call the REST API

Set the shell variable to the same value as `LOCAL_API_TOKEN` in `.env` (Compose does not export `.env` values to the invoking shell), then send a canonical v1 request:

```powershell
$env:LOCAL_API_TOKEN = '<same local API token as .env>'
$body = '{"origin":"New York","destinations":["Denver","Austin","Miami"],"duration_days":5}'
Invoke-RestMethod -Uri http://127.0.0.1:8080/api/v1/comparisons `
  -Method Post -ContentType application/json `
  -Headers @{ Authorization = "Bearer $env:LOCAL_API_TOKEN" } -Body $body
```

The result includes per-city weather and travel provenance, unavailable sources, any follow-up findings, and a deterministic recommendation. An idempotency key may be sent with the `Idempotency-Key` header; a successful replay for the same principal/key/request returns the cached result, while a changed request returns 409. This cache is bounded and process-local, not durable or shared between replicas. `GET /health/live` and `GET /health/ready` do not require authentication; comparison requests do.

Stop the stack:

```powershell
docker compose --env-file .env -f deploy/compose.yaml down
```

## Data behavior and safety

- `STUB_PROVIDERS=true` supplies deterministic weather for offline development and tests.
- `STUB_PROVIDERS=false` uses National Weather Service alerts/forecast and requires outbound access to `api.weather.gov` plus a genuine monitored contact in `NWS_USER_AGENT` (for example, the application name and an operator email/URL). A requested departure date uses that date's daytime forecast; if it is outside the returned forecast window, weather is reported unavailable instead of substituting a different day's forecast. Live mode also requires an OpenAI API key for comparison narrative; natural-language CLI parsing uses the same configured model.
- Flight and lodging amounts are versioned **illustrative synthetic estimates**. They are not live, quoted, available, or bookable prices. The preserved five-day NYC examples are Denver **$900**, Austin **$1,030**, and Miami **$1,665**.
- A missing source produces a clearly marked partial result; with no usable evidence, the API returns a failure instead of inventing a winner. A shared 30-second deadline bounds fan-out and one safe retry.
- The request contract rejects unsupported places, duplicate destinations, payment-card fields/numbers, and oversized bodies. No payment data is accepted or stored. The product is not a payment system and makes no PCI DSS compliance claim.

## Verify locally

```powershell
uv sync --locked --dev
uv run --locked pytest -q
uv run --locked ruff check src tests
uv run --locked ruff format --check src tests
```

Compose configuration is checked in CI with `.env.example`; a local stack smoke test additionally requires Docker Engine/Compose. The Python tests stub all external services.

## Azure deployment and promotion

CI runs deterministic tests, lint and format checks, a locked dependency audit, Compose validation, and Terraform validation. The development release workflow builds and scans the image, publishes a CycloneDX SBOM, pushes to ACR, resolves the resulting SHA-256 digest, deploys that exact digest, verifies only the API has external ingress, and probes readiness. The production promotion workflow accepts a full `sha256:...` digest from a successful development deployment and deploys that same image. Configure approval/branch controls in the GitHub Environments; production promotion is restricted to `main`.

Create protected GitHub Environments named `development` and `production`, then configure these **environment variables** in both:

`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `AZURE_RESOURCE_GROUP`, `NAME_PREFIX`, `ACR_NAME`, `ACA_ENVIRONMENT_NAME`, `KEY_VAULT_NAME`, `OPENAI_SECRET_URI`, `OIDC_ISSUER`, `OIDC_JWKS_URL`, `NWS_USER_AGENT`, `USER_API_AUDIENCE`, `WEATHER_A2A_AUDIENCE`, and `TRAVEL_A2A_AUDIENCE`.

Use a lowercase alphanumeric-and-hyphen `NAME_PREFIX` (3–10 characters, starting with a letter and ending alphanumeric) and a globally unique lowercase alphanumeric `ACR_NAME` (5–50 characters). Terraform creates the resource group, ACR, Key Vault, Log Analytics and ACA environment; state lives in an Azure Storage account created by `deploy/scripts/terraform-apply.sh` (set `TFSTATE_RESOURCE_GROUP` and a globally unique `TFSTATE_STORAGE_ACCOUNT`, plus `AZURE_LOCATION`, `KEY_VAULT_NAME`). Run the **Provision infrastructure** workflow first (with `store_openai_secret` to put `OPENAI_API_KEY` secret into Key Vault), then **Deploy development**. The Azure deployment principal needs GitHub OIDC federated credentials for each environment and narrowly scoped rights to deploy the foundation, Container Apps, and role assignments. The principal needs Contributor and User Access Administrator on the subscription/resource scope. Entra app registrations, resource audiences, the `TravelComparator.User` API role, each worker's `invoke` role, and approved user/group assignments are prerequisites: assign `TravelComparator.User` only to approved API callers and grant the coordinator identity `invoke` on each worker. The templates create distinct user-assigned API/worker identities, grant ACR pull to each, and grant Key Vault Secrets User only to the API identity. Ensure required NWS/OpenAI network egress.

After a successful development deployment, copy both the reported `sha256:...` digest and its development run ID into the corresponding inputs when running **Promote production** on `main`. The workflow verifies the successful development run and its artifact record before deploying that digest. Re-run production promotion with an earlier successful development digest/run ID to roll back. No Azure infrastructure was deployed as part of local development; identity/app-role provisioning and environment protection remain operator setup.
