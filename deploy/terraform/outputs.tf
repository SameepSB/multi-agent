output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "container_registry_name" {
  value = azurerm_container_registry.this.name
}

output "registry_login_server" {
  value = azurerm_container_registry.this.login_server
}

output "key_vault_name" {
  value = azurerm_key_vault.this.name
}

output "environment_name" {
  value = azurerm_container_app_environment.this.name
}

output "api_fqdn" {
  value = try(azurerm_container_app.api[0].ingress[0].fqdn, "")
}
