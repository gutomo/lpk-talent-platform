# LPK Talent Platform PoC のインフラ一式。
# 構成：ACA（Consumption、scale-to-zero）+ ACR + PostgreSQL Flexible Server B1ms + Key Vault。
# 注意：ACA は linux/amd64 イメージのみ対応（CLAUDE.md の「ARM64」は ACA 非対応が判明済み）。
# 初回構築はイメージが ACR に無いと container app の provisioning が失敗するため、
# README.md の bootstrap 手順（ACR を先に作成 → push → 全体 apply）に従うこと。

data "azurerm_client_config" "current" {}

# ACR / Key Vault / PostgreSQL はグローバル一意名が必要なためランダム接尾辞を付ける
resource "random_string" "suffix" {
  length  = 5
  lower   = true
  upper   = false
  numeric = true
  special = false
}

resource "random_password" "postgres" {
  length  = 24
  special = false # URL エンコード不要にするため英数のみ
}

locals {
  suffix         = random_string.suffix.result
  acr_name       = "${replace(var.prefix, "-", "")}acr${local.suffix}"
  kv_name        = substr("${var.prefix}-kv-${local.suffix}", 0, 24)
  pg_name        = "${var.prefix}-pg-${local.suffix}"
  backend_image  = "${azurerm_container_registry.main.login_server}/lpk-backend:${var.image_tag}"
  frontend_image = "${azurerm_container_registry.main.login_server}/lpk-frontend:${var.image_tag}"
  database_url = join("", [
    "postgresql+psycopg://",
    var.postgres_admin_login,
    ":",
    random_password.postgres.result,
    "@",
    azurerm_postgresql_flexible_server.main.fqdn,
    ":5432/lpk?sslmode=require",
  ])
}

resource "azurerm_resource_group" "main" {
  name     = "${var.prefix}-rg"
  location = var.location
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.prefix}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_container_app_environment" "main" {
  name                       = "${var.prefix}-env"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
}

resource "azurerm_container_registry" "main" {
  name                = local.acr_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic"
  admin_enabled       = false
}

# ACA からの image pull と Key Vault 参照に使う共通 ID
resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.prefix}-app-identity"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

# --- PostgreSQL Flexible Server（B1ms、PoC 規模） ---

resource "azurerm_postgresql_flexible_server" "main" {
  name                          = local.pg_name
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  version                       = "16"
  administrator_login           = var.postgres_admin_login
  administrator_password        = random_password.postgres.result
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  backup_retention_days         = 7
  public_network_access_enabled = true

  lifecycle {
    ignore_changes = [zone] # フェイルオーバー等でゾーンが変わっても再作成しない
  }
}

# ACA（Consumption）は固定 egress IP を持たないため、PoC は Azure 内サービスからの接続を許可する。
# 本番提案時は VNet 統合 + Private Endpoint に置き換える。
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_services" {
  name             = "allow-azure-services"
  server_id        = azurerm_postgresql_flexible_server.main.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

resource "azurerm_postgresql_flexible_server_database" "lpk" {
  name      = "lpk"
  server_id = azurerm_postgresql_flexible_server.main.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# --- Key Vault（DB 接続文字列と外部プロバイダの資格情報を集約） ---

resource "azurerm_key_vault" "main" {
  name                       = local.kv_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
}

resource "azurerm_key_vault_access_policy" "deployer" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Recover", "Purge"]
}

resource "azurerm_key_vault_access_policy" "app" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_user_assigned_identity.app.principal_id

  secret_permissions = ["Get", "List"]
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = local.database_url
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "azure_speech_key" {
  name         = "azure-speech-key"
  value        = var.azure_speech_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "aws_access_key_id" {
  name         = "aws-access-key-id"
  value        = var.aws_access_key_id
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

resource "azurerm_key_vault_secret" "aws_secret_access_key" {
  name         = "aws-secret-access-key"
  value        = var.aws_secret_access_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [azurerm_key_vault_access_policy.deployer]
}

# --- backend（FastAPI、内部 ingress のみ。frontend の nginx が /api を中継する） ---

resource "azurerm_container_app" "backend" {
  name                         = "${var.prefix}-backend"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = false
    target_port      = 8001
    # 環境内の nginx から http で受ける（内部通信。外向きは frontend 側で https 終端）
    allow_insecure_connections = true

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  secret {
    name                = "database-url"
    identity            = azurerm_user_assigned_identity.app.id
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
  }

  secret {
    name                = "azure-speech-key"
    identity            = azurerm_user_assigned_identity.app.id
    key_vault_secret_id = azurerm_key_vault_secret.azure_speech_key.versionless_id
  }

  secret {
    name                = "aws-access-key-id"
    identity            = azurerm_user_assigned_identity.app.id
    key_vault_secret_id = azurerm_key_vault_secret.aws_access_key_id.versionless_id
  }

  secret {
    name                = "aws-secret-access-key"
    identity            = azurerm_user_assigned_identity.app.id
    key_vault_secret_id = azurerm_key_vault_secret.aws_secret_access_key.versionless_id
  }

  template {
    min_replicas = 0
    max_replicas = 2

    container {
      name   = "backend"
      image  = local.backend_image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "APP_ENV"
        value = "prod"
      }
      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "PROVIDER_MODE"
        value = var.provider_mode
      }
      env {
        name  = "LLM_PROVIDER_MODE"
        value = var.llm_provider_mode
      }
      env {
        name        = "AZURE_SPEECH_KEY"
        secret_name = "azure-speech-key"
      }
      env {
        name  = "AZURE_SPEECH_REGION"
        value = var.azure_speech_region
      }
      env {
        name  = "AZURE_SPEECH_ENDPOINT"
        value = var.azure_speech_endpoint
      }
      env {
        name        = "AWS_ACCESS_KEY_ID"
        secret_name = "aws-access-key-id"
      }
      env {
        name        = "AWS_SECRET_ACCESS_KEY"
        secret_name = "aws-secret-access-key"
      }
      env {
        name  = "AWS_REGION"
        value = var.aws_region
      }
      env {
        name  = "BEDROCK_MODEL_ID"
        value = var.bedrock_model_id
      }
      env {
        name  = "COOKIE_SECURE"
        value = "true"
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8001
        path      = "/health"
      }

      readiness_probe {
        transport = "HTTP"
        port      = 8001
        path      = "/health"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_key_vault_access_policy.app]
}

# --- frontend（nginx。外部 ingress、https 終端はACAが行う） ---

resource "azurerm_container_app" "frontend" {
  name                         = "${var.prefix}-frontend"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = true
    target_port      = 8080

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    max_replicas = 1

    container {
      name   = "frontend"
      image  = local.frontend_image
      cpu    = 0.25
      memory = "0.5Gi"

      env {
        name  = "BACKEND_ORIGIN"
        value = "http://${azurerm_container_app.backend.ingress[0].fqdn}"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull]
}

# --- migration ジョブ（手動トリガー。CI の deploy 後に alembic upgrade head を流す） ---

resource "azurerm_container_app_job" "migrate" {
  name                         = "${var.prefix}-migrate"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id

  replica_timeout_in_seconds = 600
  replica_retry_limit        = 0

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "database-url"
    identity            = azurerm_user_assigned_identity.app.id
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
  }

  template {
    container {
      name    = "migrate"
      image   = local.backend_image
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["alembic", "upgrade", "head"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_key_vault_access_policy.app]
}

# --- seed ジョブ（手動トリガー。全行を消して架空デモデータを再投入する） ---
# 起動は scripts/seed/seed_remote.sh（完了待ちとデモアカウント表示まで行う）。
# PoC の DB は全て架空データなので --reset 固定で問題ない（CLAUDE.md の PII 方針）。

resource "azurerm_container_app_job" "seed" {
  name                         = "${var.prefix}-seed"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  container_app_environment_id = azurerm_container_app_environment.main.id

  # argon2 ハッシュ 30名分 + 60日分の履歴生成のため migrate より余裕を持たせる
  replica_timeout_in_seconds = 900
  replica_retry_limit        = 0

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "database-url"
    identity            = azurerm_user_assigned_identity.app.id
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
  }

  template {
    container {
      name    = "seed"
      image   = local.backend_image
      cpu     = 0.5
      memory  = "1Gi"
      command = ["python", "/srv/scripts/seed/seed_demo.py", "--reset"]

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_key_vault_access_policy.app]
}
