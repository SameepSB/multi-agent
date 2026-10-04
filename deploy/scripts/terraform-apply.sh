#!/usr/bin/env bash
# Initializes Terraform against a per-environment remote state and applies it.
# Expects ARM_* credentials, TF_VAR_* inputs and the variables below in the environment.
set -euo pipefail

: "${ENVIRONMENT_NAME:?}" "${AZURE_LOCATION:?}"
: "${TFSTATE_RESOURCE_GROUP:?}" "${TFSTATE_STORAGE_ACCOUNT:?}"

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../${TF_ROOT_DIR:-terraform}" && pwd)"
container="tfstate"

az group create --name "$TFSTATE_RESOURCE_GROUP" --location "$AZURE_LOCATION" --output none
if ! az storage account show --name "$TFSTATE_STORAGE_ACCOUNT" --resource-group "$TFSTATE_RESOURCE_GROUP" --output none 2>/dev/null; then
  az storage account create \
    --name "$TFSTATE_STORAGE_ACCOUNT" \
    --resource-group "$TFSTATE_RESOURCE_GROUP" \
    --location "$AZURE_LOCATION" \
    --sku Standard_GRS \
    --min-tls-version TLS1_2 \
    --allow-blob-public-access false \
    --allow-shared-key-access false \
    --output none
fi

# State is read and written with Entra ID, so the deployer needs blob data access.
storage_id="$(az storage account show --name "$TFSTATE_STORAGE_ACCOUNT" --resource-group "$TFSTATE_RESOURCE_GROUP" --query id --output tsv)"
principal_id="$(az ad sp show --id "$ARM_CLIENT_ID" --query id --output tsv)"
if [ -z "$(az role assignment list --assignee "$principal_id" --scope "$storage_id" --role "Storage Blob Data Contributor" --query '[0].id' --output tsv)" ]; then
  az role assignment create \
    --assignee-object-id "$principal_id" \
    --assignee-principal-type ServicePrincipal \
    --role "Storage Blob Data Contributor" \
    --scope "$storage_id" \
    --output none
fi

for attempt in $(seq 1 12); do
  if az storage container create --name "$container" --account-name "$TFSTATE_STORAGE_ACCOUNT" --auth-mode login --output none 2>/dev/null; then
    break
  fi
  if [ "$attempt" = 12 ]; then
    echo "Could not create the Terraform state container." >&2
    exit 1
  fi
  sleep 10
done

cd "$root"
terraform init -input=false -reconfigure \
  -backend-config="resource_group_name=${TFSTATE_RESOURCE_GROUP}" \
  -backend-config="storage_account_name=${TFSTATE_STORAGE_ACCOUNT}" \
  -backend-config="container_name=${container}" \
  -backend-config="key=${TFSTATE_KEY:-${ENVIRONMENT_NAME}.tfstate}" \
  -backend-config="use_azuread_auth=true"
terraform apply -input=false -auto-approve
