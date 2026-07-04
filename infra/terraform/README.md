# infra/terraform：Azure デプロイ（PoC）

構成：Azure Container Apps（Consumption、scale-to-zero）+ ACR + PostgreSQL Flexible Server（B1ms）+ Key Vault + Log Analytics。
Speech / SES は新規作成せず、既存リソースの資格情報を terraform.tfvars で渡す（BUILD_PLAN Phase 6）。

注意：ACA は linux/amd64 イメージのみ対応。イメージビルドでは `--platform linux/amd64` を必ず指定する。

## 初回構築（bootstrap）

コンテナイメージが ACR に存在しない状態で container app を作ると provisioning が失敗するため、2段階で apply する。

```sh
az login
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # 必要なら編集
terraform init

# 1) 先に ACR（と RG）だけ作る
terraform apply -target=azurerm_container_registry.main

# 2) イメージを build して push（リポジトリルートで）
ACR=$(terraform output -raw acr_login_server)
az acr login --name "${ACR%%.*}"
docker build --platform linux/amd64 -f backend/Dockerfile -t "$ACR/lpk-backend:latest" .
docker build --platform linux/amd64 -t "$ACR/lpk-frontend:latest" frontend
docker push "$ACR/lpk-backend:latest"
docker push "$ACR/lpk-frontend:latest"

# 3) 全体を apply
terraform apply

# 4) migration → seed（seed は scripts/seed の手順参照）
az containerapp job start -g $(terraform output -raw resource_group_name) \
  -n $(terraform output -raw migrate_job_name)

# 5) 公開 URL
terraform output frontend_url
```

## CI（GitHub Actions）から apply する場合

local state のままでは runner 間で state を共有できない。先に state 用ストレージを一度だけ作り、
versions.tf の `backend "azurerm"` ブロックのコメントを外して `terraform init -migrate-state` する。

```sh
az group create -n lpk-poc-tfstate -l japaneast
az storage account create -n lpkpoctfstate -g lpk-poc-tfstate -l japaneast --sku Standard_LRS
az storage container create -n tfstate --account-name lpkpoctfstate
```

## 設計メモ

- backend は内部 ingress のみ。frontend の nginx が同一オリジンで `/api/*` を中継するため CORS・クロスサイト cookie の問題が出ない。https 終端は frontend 側の ACA ingress。
- DB 接続文字列・Speech キー・AWS 資格情報は Key Vault に置き、ACA の secret 参照（user-assigned identity）で注入する。
- PostgreSQL は PoC 簡略化のため public access + 「Azure 内サービスのみ許可」ファイアウォール。本番提案では VNet 統合 + Private Endpoint に置き換える。
- migration は手動トリガーの ACA Job（backend と同一イメージで `alembic upgrade head`）。
