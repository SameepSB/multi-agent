#!/usr/bin/env bash
# Runs ON the VM (as root) via `az vm run-command`. The workflow prepends `export` lines for:
# IMAGE_REF, KEY_VAULT_NAME, VM_FQDN, VM_CLIENT_ID, STUB_PROVIDERS, NWS_USER_AGENT, COMPOSE_B64.
set -euo pipefail
: "${IMAGE_REF:?}" "${KEY_VAULT_NAME:?}" "${VM_FQDN:?}" "${VM_CLIENT_ID:?}" "${COMPOSE_B64:?}"

dir=/opt/travel-comparator
mkdir -p "$dir"
cd "$dir"

# First boot installs Docker and the Azure CLI through cloud-init.
for _ in $(seq 1 60); do
  if [ -f "$dir/.cloud-init-done" ] && command -v az >/dev/null && docker compose version >/dev/null 2>&1; then
    break
  fi
  sleep 10
done
command -v az >/dev/null || { echo "Azure CLI is not installed yet." >&2; exit 1; }

az login --identity --client-id "$VM_CLIENT_ID" --output none
registry="${IMAGE_REF%%/*}"
az acr login --name "${registry%%.*}" --output none

secret() {
  az keyvault secret show --vault-name "$KEY_VAULT_NAME" --name "$1" --query value --output tsv
}

api_token="$(secret vm-api-token)"
openai_key="replace-me"
if [ "${STUB_PROVIDERS:-false}" != "true" ]; then
  openai_key="$(secret openai-api-key)"
fi

# The worker credential never leaves the VM and is generated once.
if [ -f .env ] && grep -q '^LOCAL_COORDINATOR_TOKEN=' .env; then
  coordinator_token="$(grep '^LOCAL_COORDINATOR_TOKEN=' .env | cut -d= -f2-)"
else
  coordinator_token="$(openssl rand -hex 24)"
fi

umask 077
cat > .env <<ENV
IMAGE_REF=${IMAGE_REF}
LOCAL_API_TOKEN=${api_token}
LOCAL_COORDINATOR_TOKEN=${coordinator_token}
OPENAI_API_KEY=${openai_key}
STUB_PROVIDERS=${STUB_PROVIDERS:-false}
NWS_USER_AGENT=${NWS_USER_AGENT:-}
ENV
umask 022

echo "$COMPOSE_B64" | base64 -d > compose.yaml
cat > Caddyfile <<CADDY
${VM_FQDN} {
	encode gzip
	reverse_proxy api:8080
}
CADDY

docker compose --env-file .env -f compose.yaml pull
docker compose --env-file .env -f compose.yaml up -d --remove-orphans
docker image prune -f >/dev/null

for _ in $(seq 1 30); do
  if docker compose --env-file .env -f compose.yaml ps api --format '{{.Health}}' | grep -q healthy; then
    echo RELEASE_OK
    exit 0
  fi
  sleep 5
done
docker compose --env-file .env -f compose.yaml logs --tail 50 api >&2 || true
echo "API container did not become healthy." >&2
exit 1
