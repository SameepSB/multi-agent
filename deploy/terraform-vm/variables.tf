variable "name_prefix" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  description = "Resource group created by the infrastructure Terraform."
  type        = string
}

variable "acr_name" {
  type = string
}

variable "key_vault_name" {
  type = string
}

variable "vm_size" {
  type    = string
  default = "Standard_B2s"
}

variable "admin_username" {
  type    = string
  default = "azureuser"
}

variable "ssh_public_key" {
  description = "Public key for the VM admin user. Port 22 is not opened; the VM is managed through az vm run-command."
  type        = string
}

variable "dns_label" {
  description = "DNS label, unique per region, for <label>.<region>.cloudapp.azure.com."
  type        = string
}
