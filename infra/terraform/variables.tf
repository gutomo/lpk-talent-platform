variable "prefix" {
  description = "リソース名の接頭辞。小文字英数とハイフンのみ（ACR 名等はハイフン除去して使う）"
  type        = string
  default     = "lpk-poc"
}

variable "location" {
  description = "Azure リージョン"
  type        = string
  default     = "japaneast"
}

variable "image_tag" {
  description = "backend / frontend コンテナイメージのタグ。CI は git SHA を渡す"
  type        = string
  default     = "latest"
}

variable "provider_mode" {
  description = "発音評価・STT・TTS のプロバイダ。stub（資格情報不要）| azure"
  type        = string
  default     = "stub"
}

variable "llm_provider_mode" {
  description = "会話・面接・ルーブリック採点の LLM。stub | bedrock"
  type        = string
  default     = "stub"
}

# --- 既存リソース参照（BUILD_PLAN：Speech / SES は tfvars で渡す） ---

variable "azure_speech_key" {
  description = "既存 Azure AI Speech リソースのキー。provider_mode=azure のとき必須"
  type        = string
  default     = ""
  sensitive   = true
}

variable "azure_speech_region" {
  description = "Azure AI Speech のリージョン"
  type        = string
  default     = "japaneast"
}

variable "azure_speech_endpoint" {
  description = "Speech のカスタムサブドメイン利用時のみ設定（空なら region ベース）"
  type        = string
  default     = ""
}

variable "aws_access_key_id" {
  description = "Bedrock / SES 用の AWS アクセスキー。llm_provider_mode=bedrock のとき必須"
  type        = string
  default     = ""
  sensitive   = true
}

variable "aws_secret_access_key" {
  description = "Bedrock / SES 用の AWS シークレットキー"
  type        = string
  default     = ""
  sensitive   = true
}

variable "aws_region" {
  description = "Bedrock を呼ぶ AWS リージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "bedrock_model_id" {
  description = "Bedrock の Claude モデル ID"
  type        = string
  default     = "anthropic.claude-sonnet-4-20250514-v1:0"
}

variable "postgres_admin_login" {
  description = "PostgreSQL Flexible Server の管理者ユーザー名"
  type        = string
  default     = "lpk_admin"
}
