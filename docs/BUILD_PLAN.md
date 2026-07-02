# BUILD_PLAN.md：LPK Talent Platform PoC 実行計画

対象パッケージ：「LPK向け 生成AI日本語・面接・人材品質可視化パッケージ」
構成3本柱：(1) AI日本語・発音・面接トレーナー / (2) 学生別 Talent Passport 自動生成 / (3) 日本企業向け候補者レポート・ダッシュボード

## ゴール（この10分デモが通ればPoC成立）
1. 学生がスマホでログイン → 発音練習1本 → 単語別スコアと弱点語が表示される
2. 音声で面接ロールプレイ（介護、3〜5ターン）→ ルーブリック評価とインドネシア語フィードバック
3. 教師ダッシュボードに直前の練習結果とアラートが反映される
4. その学生の Talent Passport を生成 → 日本語PDF（A4）が崩れず出力される
5. 企業向け共有リンクを開く → 候補者比較テーブル → 個別Passport閲覧

## Claude Code への実行指示
- フェーズ順に実行。各タスク完了時に `[ ]` を `[x]` に更新。
- 各フェーズ末の「受け入れ」をクリアしたら停止し、結果と `git status` を報告してからコミット（conventional commits、マイルストーンごとに1アトミックコミット）。
- 不明点・仕様の穴は推測で実装せず、選択肢を提示して確認する。
- CLAUDE.md の「地雷」「実装ルール」を常に優先する。

## KPI計測（提案書のPoC KPIをアプリ内で測定可能にする）

| KPI | 目標 | 測定方法 |
|---|---|---|
| 学生のAI利用率 | 週3回以上 | events から週次アクティブ日数を集計 |
| 面接練習回数 | 1人10回以上 | interview_sessions のカウント |
| 模擬面接スコア | 平均10〜20%改善 | 初回3回平均 vs 直近3回平均 |
| N4/JFT模試点数 | 改善傾向 | mock_sessions のスコア推移 |
| 先生の添削時間 | 20〜30%削減 | アプリ外（ヒアリング）。参考値として添削キュー滞留時間を表示 |

---

## Phase 0：土台整備（1日）

**0-A. 既存リポジトリがある場合（音声AI日本語チューターdemo）**
- [ ] 音声ループ（録音 → ffmpeg変換 → Azure発音評価 → Claude会話 → TTS）の動作確認
- [ ] docs/DESIGN.md と現状コードの差分を棚卸しし、CLAUDE.md記載のリポジトリ構成へ整理

**0-B. 既存リポジトリを流用しない場合**
- [ ] FastAPI + React/Vite scaffold、docker compose（postgres）、Makefile、CI（lint + test）を新規作成

**共通**
- [x] Alembic導入、初期マイグレーション
- [x] データモデル作成（下記「初期データモデル」）
- [ ] 認証：email + password（argon2）+ セッション、ロール制御（student / teacher / admin）
- [ ] events記録の仕組み（全学習アクションを記録、KPI集計の元データ）
- [ ] seedスクリプト：LPK 1、先生2、学生30（架空インドネシア名）、企業1、過去60日分の練習履歴を傾向つきで生成（優秀層 / 平均層 / リスク学生1名を仕込む）

**受け入れ**：`make dev` で起動。3ロールでログイン可。教師画面に学生30名が見え、seedにリスク学生が含まれている。

### 初期データモデル
- organizations（type: lpk / company）
- users（org_id, role: student / teacher / admin, locale）
- cohorts（sector, start_date）, enrollments
- content_items（module: pronunciation / drill, sector, text_ja, furigana, gloss_id, level, meta jsonb）
- pronunciation_attempts（user_id, item_id, scores jsonb, weak_words jsonb）
- conversation_sessions / interview_sessions（scenario, sector, mode: text / voice, status）
- interview_turns（session_id, seq, role, text_ja, stt jsonb）
- interview_evaluations（session_id, rubric_version, scores jsonb, feedback jsonb, total）
- quiz_items（review_flag）, quiz_attempts, mock_sessions
- attendance_records, attitude_reviews（checklist jsonb）
- passports（snapshot jsonb, version, pdf_ref）, share_links（token, expires_at, revoked, view_log）
- events（user_id, type, meta jsonb）

---

## Phase 1：発音・会話トレーナー本実装（1.5日）
- [ ] コンテンツバンクseed：介護40 / 食品製造20 / 外食20 / 汎用40フレーズ（text_ja、ふりがな、インドネシア語の意味、level）
- [ ] 発音評価API `/speech/assess`：WebM/Opus → ffmpeg WAV(16kHz mono) → Azure Pronunciation Assessment（accuracy / fluency / completeness + 単語・音素スコア。prosodyは使わない）
- [ ] 学生UI：課題文表示 → タップ録音 → 単語別色分け結果 → 弱点語リスト自動更新
- [ ] AI会話練習：既存の介護シナリオを流用し、自己紹介 / 職場会話 / 報連相 の3シナリオを追加
- [ ] streak（連続利用日数）表示

**受け入れ**：Android Chrome実機で発音練習1本完了、スコア表示、弱点語が集計され、教師画面の学生詳細に反映される。

---

## Phase 2：面接ロールプレイ（2日）
- [ ] 面接官ペルソナprompt 3種（優先順：介護 → 食品製造 → 外食）。企業設定、質問フロー（自己紹介 → 志望理由 → 想定質問 → 逆質問）、5〜8ターン
- [ ] テキストモードを先行実装（プロンプトとフローの検証用）
- [ ] 音声モード：録音 → STT(ja-JP) → Bedrock Claude → Neural TTS再生のターン制カスケード（既存音声ループを流用）
- [ ] ルーブリック評価：軸 = 日本語力 / 内容の一貫性 / 敬語・礼儀 / 報連相 / 発話明瞭さ（発音スコア連携）。構造化JSON出力、rubric_version保存、総合0〜100
- [ ] フィードバック画面：インドネシア語の解説 + 日本語の模範解答例
- [ ] 面接履歴一覧とスコア推移グラフ

**受け入れ**：音声モードで5ターンの面接を完走 → 評価が保存・表示され、2回目以降にスコア推移が描画される。

---

## Phase 3：N4 / JFT-Basicドリル（1日）
- [ ] オリジナル問題バンク100問をseed（文法40 / 語彙40 / 読解20。N4 / JFT-Basic水準タグ。過去問の複製は禁止）
- [ ] 問題生成スクリプト：Claudeで問題案を生成 → review_flag付きで保存（人間の確認前は出題しない）
- [ ] デイリークイズ10問 + 誤答再出題（簡易SRS）
- [ ] 模試モード25問、スコア換算。listening問題はTTSで音源生成
- [ ] 画面に「非公式・試験対策用」表記

**受け入れ**：デイリークイズ完了、模試スコアがトレンドチャートに載る。

---

## Phase 4：Talent Passport（1.5日）
- [ ] 集計サービス：passport snapshot(jsonb) = 日本語レベル推移（N5→N4）、発音平均、会話スコア、面接準備度（直近評価 + 文字起こし抜粋）、職種別チェックリスト、出席率、生活態度、リスクフラグ
- [ ] リスクフラグはルールベース：出席率80%未満 / スコア下降 / 7日間未利用
- [ ] 教師入力UI：出席（月次% or 日次）、態度チェックリスト（報連相・時間厳守・寮生活・マナー等5項目）
- [ ] Passport画面（日本語）→ WeasyPrintでA4 PDF（1〜2枚、Noto Sans JP同梱、企業提出用の候補者紹介シート体裁）
- [ ] 共有リンク：ランダム32byteトークン、有効期限30日、失効操作、閲覧ログ

**受け入れ**：seed学生のPDFが日本語で崩れず生成（豆腐なし）。未ログインで共有リンク閲覧可、失効後はアクセス不可。

---

## Phase 5：ダッシュボード3種（1.5日）
- [ ] 教師：クラス一覧（進捗 / 最終利用 / アラート）、学生詳細（スコア推移・弱点語・面接履歴・文字起こし）、添削キュー
- [ ] 経営者KPI：N4到達率、模試平均、出席率、練習量、週次トレンド、PoC KPIカード
- [ ] 企業ビュー：候補者比較テーブル（ソート可）→ 各Passportへ。トークンアクセス（ログイン不要）
- [ ] リスクフラグ学生のアラートバッジ

**受け入れ**：3ビューがseedデータで描画され、仕込みのリスク学生にアラートが表示される。

---

## Phase 6：計測・デプロイ・デモ準備（1.5日）
- [ ] KPI集計APIと経営者画面への表示（上のKPI表と同一定義）
- [ ] Terraform拡張：既存のACA scaffold（versions / variables / main / outputs / tfvars.example）を流用し、PostgreSQL Flexible Server（B1ms）と Key Vault を追加。Speech / SES は既存リソース参照（tfvars）
- [ ] GitHub Actions：build → push → apply（手動ゲート）、migrationジョブ
- [ ] 本番用seed投入スクリプト
- [ ] docs/DEMO.md：10分デモ台本 + フォールバック（事前録画）メモ

**受け入れ**：公開URLで冒頭の10分デモが通しで完走。スモークチェックリスト全通過。

---

## 見積り
合計 約9〜10営業日（1人 + Claude Code併用）。Phase 2と4が価値の核なので、遅延時はPhase 3（ドリル）を最小化して守る。

## リスクと対策
- ja-JPはprosody非対応：accuracy / fluency / completeness + 音素レベルのみで設計（確定事項）
- モバイルSafariのマイク挙動：デモ標準機はAndroid Chromeに固定。Phase 1で実機確認
- LLM評価のブレ：temperature 0.2、few-shot、JSONスキーマ強制、rubric_version保存
- 著作権：JLPT / JFTの公式問題・過去問は使わない。完全オリジナル + 非公式表記
- PII（UU No.27 Tahun 2022）：パスポート番号・住所は扱わない。seedは架空。共有リンクに有効期限と失効
- WeasyPrintのCJK：Noto Sans JPをコンテナ同梱、豆腐検出をテストに含める
- Bedrockクロスクラウドのレイテンシ：ターン制で許容。リアルタイム双方向は狙わない

## バックログ（PoC後、提案書の残りアイデア）
- 書類OCR・COE / ビザチェックリスト（提案書 #4）
- 求人票AIマッチング（#5）
- 日本到着後の生活・職場サポートbot（#6）
- WhatsApp連携（WABA取得後、Airaの知見を流用）
- 動画面接（PoCは音声 + 文字起こしで代替）
- 顧客本番パス：Azure AI Foundry / M365 / Power BI / Copilot Studio への載せ替え
