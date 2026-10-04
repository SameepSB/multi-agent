variable "name_prefix" {
  description = "Short resource name prefix."
  type        = string

  validation {
    condition     = length(var.name_prefix) >= 3 && length(var.name_prefix) <= 10
    error_message = "name_prefix must be 3-10 characters."
  }
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "acr_name" {
  description = "Globally unique container registry name."
  type        = string
}

variable "key_vault_name" {
  description = "Globally unique Key Vault name."
  type        = string
}

variable "log_retention_days" {
  type    = number
  default = 30
}

variable "container_image" {
  description = "Immutable image reference with @sha256 digest. Empty creates infrastructure only."
  type        = string
  default     = ""

  validation {
    condition     = var.container_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.container_image))
    error_message = "container_image must be empty or reference an @sha256 digest."
  }
}

variable "openai_secret_uri" {
  description = "Versioned Key Vault secret URI for the OpenAI key."
  type        = string
  default     = ""
}

variable "oidc_issuer" {
  type    = string
  default = ""
}

variable "oidc_jwks_url" {
  type    = string
  default = ""
}

variable "nws_user_agent" {
  type    = string
  default = ""
}

variable "user_api_audience" {
  type    = string
  default = ""
}

variable "weather_a2a_audience" {
  type    = string
  default = ""
}

variable "travel_a2a_audience" {
  type    = string
  default = ""
}
