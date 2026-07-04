terraform {
  required_version = ">= 1.9"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.20"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # GitHub Actions から apply する場合は remote state を使う（README.md の bootstrap 手順参照）。
  # ローカル検証は local state のままで良い。
  # backend "azurerm" {
  #   resource_group_name  = "lpk-poc-tfstate"
  #   storage_account_name = "lpkpoctfstate"
  #   container_name       = "tfstate"
  #   key                  = "lpk-poc.tfstate"
  # }
}

provider "azurerm" {
  features {}
}
