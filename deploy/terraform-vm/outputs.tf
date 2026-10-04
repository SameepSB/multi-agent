output "vm_name" {
  value = azurerm_linux_virtual_machine.this.name
}

output "vm_fqdn" {
  value = azurerm_public_ip.this.fqdn
}

output "vm_identity_client_id" {
  value = azurerm_user_assigned_identity.vm.client_id
}
