locals {
  deploy_apps = var.container_image != ""

  workers = {
    weather = {
      module = "weather_server"
      port   = 5001
    }
    travel = {
      module = "travel_server"
      port   = 5003
    }
  }

  identities = {
    weather = azurerm_user_assigned_identity.weather
    travel  = azurerm_user_assigned_identity.travel
  }

  base_env = {
    APP_ENV                 = "production"
    LOG_LEVEL               = "INFO"
    REQUEST_TIMEOUT_SECONDS = "30"
    MAX_CITIES              = "4"
    STUB_PROVIDERS          = "false"
    NWS_USER_AGENT          = var.nws_user_agent
    OIDC_ISSUER             = var.oidc_issuer
    OIDC_JWKS_URL           = var.oidc_jwks_url
    WEATHER_A2A_AUDIENCE    = var.weather_a2a_audience
    TRAVEL_A2A_AUDIENCE     = var.travel_a2a_audience
    TRAVEL_DATA_PATH        = "/app/data/travel_data.json"
  }
}

resource "azurerm_container_app" "worker" {
  for_each = local.deploy_apps ? local.workers : {}

  name                         = "${var.name_prefix}-${each.key}"
  resource_group_name          = azurerm_resource_group.this.name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [local.identities[each.key].id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = local.identities[each.key].id
  }

  ingress {
    external_enabled           = false
    target_port                = each.value.port
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = 3

    container {
      name    = "${var.name_prefix}-${each.key}"
      image   = var.container_image
      cpu     = 0.5
      memory  = "1Gi"
      command = ["uvicorn"]
      args = [
        "travel_comparator.agents.${each.value.module}:create_app",
        "--factory",
        "--host",
        "0.0.0.0",
        "--port",
        tostring(each.value.port),
      ]

      dynamic "env" {
        for_each = merge(local.base_env, {
          TRUSTED_COORDINATOR_OBJECT_ID = azurerm_user_assigned_identity.api.principal_id
        })
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}

resource "azurerm_container_app" "api" {
  count = local.deploy_apps ? 1 : 0

  name                         = "${var.name_prefix}-api"
  resource_group_name          = azurerm_resource_group.this.name
  container_app_environment_id = azurerm_container_app_environment.this.id
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  registry {
    server   = azurerm_container_registry.this.login_server
    identity = azurerm_user_assigned_identity.api.id
  }

  secret {
    name                = "openai-api-key"
    key_vault_secret_id = var.openai_secret_uri
    identity            = azurerm_user_assigned_identity.api.id
  }

  ingress {
    external_enabled           = true
    target_port                = 8080
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = 3

    container {
      name    = "${var.name_prefix}-api"
      image   = var.container_image
      cpu     = 0.5
      memory  = "1Gi"
      command = ["uvicorn"]
      args = [
        "travel_comparator.api.main:create_app",
        "--factory",
        "--host",
        "0.0.0.0",
        "--port",
        "8080",
      ]

      dynamic "env" {
        for_each = merge(local.base_env, {
          API_PORT                   = "8080"
          OIDC_AUDIENCE              = var.user_api_audience
          WEATHER_AGENT_URL          = "https://${azurerm_container_app.worker["weather"].ingress[0].fqdn}"
          TRAVEL_AGENT_URL           = "https://${azurerm_container_app.worker["travel"].ingress[0].fqdn}"
          MANAGED_IDENTITY_CLIENT_ID = azurerm_user_assigned_identity.api.client_id
        })
        content {
          name  = env.key
          value = env.value
        }
      }

      env {
        name        = "OPENAI_API_KEY"
        secret_name = "openai-api-key"
      }
    }
  }

  lifecycle {
    precondition {
      condition     = can(regex("/secrets/[^/]+/[^/]+$", var.openai_secret_uri))
      error_message = "openai_secret_uri must be a versioned Key Vault secret URI."
    }
  }

  depends_on = [
    azurerm_role_assignment.acr_pull,
    azurerm_role_assignment.api_key_vault_read,
  ]
}
