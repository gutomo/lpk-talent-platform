output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "acr_login_server" {
  description = "docker push 先。CI の build → push で使う"
  value       = azurerm_container_registry.main.login_server
}

output "frontend_url" {
  description = "デモの公開 URL"
  value       = "https://${azurerm_container_app.frontend.ingress[0].fqdn}"
}

output "backend_internal_fqdn" {
  description = "backend の内部 FQDN（frontend の nginx が /api を中継する先）"
  value       = azurerm_container_app.backend.ingress[0].fqdn
}

output "postgres_fqdn" {
  value = azurerm_postgresql_flexible_server.main.fqdn
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "migrate_job_name" {
  description = "az containerapp job start で起動する migration ジョブ名"
  value       = azurerm_container_app_job.migrate.name
}

output "seed_job_name" {
  description = "scripts/seed/seed_remote.sh で起動する seed ジョブ名"
  value       = azurerm_container_app_job.seed.name
}
