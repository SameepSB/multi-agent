data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

data "azurerm_container_registry" "this" {
  name                = var.acr_name
  resource_group_name = data.azurerm_resource_group.this.name
}

data "azurerm_key_vault" "this" {
  name                = var.key_vault_name
  resource_group_name = data.azurerm_resource_group.this.name
}

resource "azurerm_user_assigned_identity" "vm" {
  name                = "${var.name_prefix}-vm-id"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
}

resource "azurerm_role_assignment" "vm_acr_pull" {
  scope                            = data.azurerm_container_registry.this.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_user_assigned_identity.vm.principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_role_assignment" "vm_key_vault_read" {
  scope                            = data.azurerm_key_vault.this.id
  role_definition_name             = "Key Vault Secrets User"
  principal_id                     = azurerm_user_assigned_identity.vm.principal_id
  skip_service_principal_aad_check = true
}

resource "azurerm_virtual_network" "this" {
  name                = "${var.name_prefix}-vm-vnet"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  address_space       = ["10.20.0.0/24"]
}

resource "azurerm_subnet" "this" {
  name                 = "vm"
  resource_group_name  = data.azurerm_resource_group.this.name
  virtual_network_name = azurerm_virtual_network.this.name
  address_prefixes     = ["10.20.0.0/26"]
}

# Only HTTP(S) is exposed. Azure's default rules deny all other inbound traffic;
# the VM is managed through `az vm run-command`, not SSH.
resource "azurerm_network_security_group" "this" {
  name                = "${var.name_prefix}-vm-nsg"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name

  security_rule {
    name                       = "allow-http-https"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_ranges    = ["80", "443"]
    source_address_prefix      = "Internet"
    destination_address_prefix = "*"
  }
}

resource "azurerm_subnet_network_security_group_association" "this" {
  subnet_id                 = azurerm_subnet.this.id
  network_security_group_id = azurerm_network_security_group.this.id
}

resource "azurerm_public_ip" "this" {
  name                = "${var.name_prefix}-vm-ip"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  allocation_method   = "Static"
  sku                 = "Standard"
  domain_name_label   = var.dns_label
}

resource "azurerm_network_interface" "this" {
  name                = "${var.name_prefix}-vm-nic"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.this.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.this.id
  }
}

resource "azurerm_linux_virtual_machine" "this" {
  name                            = "${var.name_prefix}-vm"
  location                        = data.azurerm_resource_group.this.location
  resource_group_name             = data.azurerm_resource_group.this.name
  size                            = var.vm_size
  admin_username                  = var.admin_username
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.this.id]
  custom_data                     = base64encode(file("${path.module}/cloud-init.yaml"))

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.vm.id]
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  depends_on = [
    azurerm_role_assignment.vm_acr_pull,
    azurerm_role_assignment.vm_key_vault_read,
  ]
}
