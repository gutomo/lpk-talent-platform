# CLAUDE.md：LPK Talent Platform（生成AI日本語・面接・人材品質可視化パッケージ PoC）

> このファイルはClaude Codeがセッション開始時に自動で読み込む「行動規範」。
> フェーズ別の実行手順は docs/BUILD_PLAN.md、既存の音声ループ設計は docs/DESIGN.md を参照（内容をここに重複させない）。

## 現在のリポジトリ状態（2026-07時点）
- 実装前。存在するのは docs（CLAUDE.md / BUILD_PLAN.md）と .clauderules のみで、コードはまだ無い。
- 未作成：backend / frontend / infra 一式、docs/DESIGN.md、docs/DEMO.md、git初期化。
- したがって下記「コマンド」「リポジトリ構成」は到達目標であり現状ではない。実作業は BUILD_PLAN.md の Phase 0 から始める（既存の音声ループdemoを流用しない場合は 0-B）。

## プロジェクト概要
- 「LPK向け 生成AI日本語・面接・人材品質可視化パッケージ」のPoC実装。
- 3コンポーネント：
  1. AI日本語・発音・面接トレーナー（学生向けスマホWeb）
  2. 学生別 Talent Passport 自動生成（日本語PDF + 企業向け共有リンク）
  3. 候補者レポート・ダッシュボード（教師 / LPK経営者 / 日本企業の3ビュー）
- PoC想定規模：学生30〜50名、先生2〜3名。KPI定義は BUILD_PLAN.md 冒頭。
- 既存の音声AI日本語チューターdemo（介護「朝の声かけ + バイタルチェック」、A2/N4）を土台に拡張する。既存リポジトリを流用しない場合は BUILD_PLAN Phase 0-B から。

## 技術スタック（確定。変更する場合は必ず事前確認）
- Backend：Python 3.12 + FastAPI（uvで管理）
- Frontend：React + Vite + TypeScript（モバイルファースト）
- 発音採点・STT：Azure AI Speech（ja-JP、Pronunciation Assessment + STT）
- 会話・面接・ルーブリック採点：Amazon Bedrock の Claude（Sonnet）
- 音声合成：Azure Neural TTS（ja-JP）
- DB：PostgreSQL 16 + SQLAlchemy 2 + Alembic
- 音声変換：ffmpeg（WebM/Opus → WAV 16kHz mono）
- PDF生成：WeasyPrint + Noto Sans JP（Talent Passport）
- メール：Amazon SES（または SendGrid）
- IaC / デプロイ：Terraform + Azure Container Apps（linux/amd64、scale-to-zero。ACA は ARM64 イメージ非対応のため）
- 補足：顧客本番提案では Azure AI Foundry / M365 系へ載せ替えるパスを想定。demoはBedrockのまま。

## ロールとUI言語
- student：スマホWeb。UI言語は Bahasa Indonesia、学習対象は日本語。AIフィードバックは idの解説 + jaの例文。
- teacher / admin（LPK経営者）：ダッシュボード。UI言語は日本語。
- 日本企業：ログイン無しの共有リンク閲覧 + 候補者比較ビュー。日本語のみ。

## リポジトリ構成（拡張後の目標）
```
backend/app/{routers,services,models,schemas,prompts,content}
frontend/src/{pages,components,api,i18n}
docs/{DESIGN.md,BUILD_PLAN.md,DEMO.md}
infra/terraform/
scripts/seed/
```

## コマンド
- 起動：`docker compose up`（postgres）+ `make dev`
- backend：`uv run fastapi dev` / `uv run pytest` / `uv run ruff check`
- frontend：`pnpm dev` / `pnpm build` / `pnpm lint`
- migration：`uv run alembic upgrade head`

## 実装ルール
- スコアは全て0〜100。ルーブリックはJSONスキーマで定義し、結果に rubric_version を必ず保存。
- LLM評価は temperature 0.2、構造化出力（JSON強制）。プロンプトは backend/app/prompts/ で版管理。
- 全学習アクションを events テーブルに記録（KPI集計の唯一の元データ）。
- ドリル問題は完全オリジナル。JLPT / JFTの過去問・公式問題を複製しない。「非公式・試験対策用」表記を必ず出す。
- PII最小化（インドネシア UU No.27 Tahun 2022 対応方針）：パスポート番号・住所は扱わない。seedは全て架空データ。
- i18n：frontend/src/i18n/{id,ja}.json。UI文言のハードコード禁止。

## 地雷（先行検証で確定済み。踏まないこと）
- Azure発音評価の prosody スコアは ja-JP 非対応。accuracy / fluency / completeness + 音素レベルのみ使う。
- MediaRecorder の既定は WebM/Opus。Azureに渡す前にサーバ側で ffmpeg WAV(16kHz mono) 変換が必須。
- Bedrockはクロスクラウド呼び出し。ターン制で設計し、リアルタイム双方向会話は狙わない。
- WeasyPrintのCJK：Noto Sans JP をコンテナに同梱し font-family を明示。PDFの豆腐チェックをテストに含める。
- WhatsApp連携はやらない（WABA審査回避のため）。バックログ扱い。

## 作業の進め方（must）
- 計画提示 → 承認 → 1スライス実装 → ビルド & スモーク → 停止して報告、の順で進める。
- コミット前に `git status` を提示する。マイルストーンごとに1アトミックコミット（conventional commits）。
- 動作未確認の機能を README やドキュメントで「完了」「デプロイ済み」と書かない。
- 文体：em dash は使わない。読点・セミコロン・ピリオドで節を区切る。

## スコープ外（PoCではやらない）
書類OCR / COEチェックリスト、求人マッチングエンジン、日本到着後サポートbot、WhatsApp、決済、動画面接（音声 + 文字起こしで代替）、Power BI / M365連携。

## 完了条件（DoD）
- lint / type / test が通る。
- seedデータで docs/DEMO.md の10分デモが通しで動く。
- Azure Container Apps 上の公開URLで同じデモを再現できる。
