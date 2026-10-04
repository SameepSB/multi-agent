terraform {
  required_version = ">= 1.9.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }

  # Configured at init time by deploy/scripts/terraform-apply.sh.
  backend "azurerm" {}
}

provider "azurerm" {
  # Credentials and subscription come from ARM_* environment variables.
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}
