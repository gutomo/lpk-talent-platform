# DEMO.md：LPK Talent Platform デモ台本

> この版は面接ロールプレイ（テキスト / 音声モード）を中心に記載する。音声モードが主眼。
> 発音練習・会話練習・教師ダッシュボードは実装済だが手順は未記載。Talent Passport PDF と企業向け共有ビューは未実装。末尾「今後追記」を参照。
> 10分デモ全体の到達目標は BUILD_PLAN.md「ゴール」を参照（内容はここに重複させない）。

## 0. 前提と起動

### 動作環境
- デモ標準機は Android Chrome（BUILD_PLAN の地雷：モバイル Safari のマイク挙動が不安定なため固定）。
- 開発機の PC Chrome でも可。いずれもマイク権限の許可が必要。
- 音声モードはブラウザの `MediaRecorder`（WebM/Opus）とマイクを使う。マイクは https か `localhost` でのみ許可される点に注意。

### プロバイダモード
音声モードは STT・LLM・TTS の3系統に依存する。既定の stub なら資格情報なしで通しで動く。設定は `backend/.env`。

| 設定 | stub（既定） | 実プロバイダ |
|---|---|---|
| `provider_mode` | STT は定型の日本語回答を返す。録音内容は不問。ffmpeg 不要 | `azure`：Azure AI Speech で実音声を ja-JP 文字起こし |
| `llm_provider_mode` | 面接官の質問とルーブリック評価が決定的モック | `bedrock`：Bedrock の Claude が生成 |
| TTS（面接官の読み上げ） | 合成せず、ブラウザ内蔵の ja-JP 音声で読み上げ | `provider_mode=azure` のとき Azure Neural TTS の MP3（ja-JP-NanamiNeural） |

- 資格情報なしデモ（推奨）：`.env` を触らず既定 stub のまま。録音（入口）と読み上げ（出口）は本物で、認識テキストと評価だけが定型になる。
- 実プロバイダデモ：`provider_mode=azure`（+ `AZURE_SPEECH_KEY` / `azure_speech_region`）、`llm_provider_mode=bedrock`（+ AWS 資格情報）。azure のときのみサーバ側で ffmpeg の WAV(16kHz mono) 変換が走るので、backend 環境に ffmpeg を用意する。

### 起動
別々のターミナルで順に実行する。

1. `make db`（Postgres を docker で起動）
2. `make migrate`
3. `make seed`（DB を初期化して架空データ投入。末尾にデモアカウントを表示する）
4. `make backend`（http://localhost:8001 ）
5. `make frontend` → ブラウザで http://localhost:5173 を開く

### デモアカウント
`make seed` の出力が正。標準 seed では以下になる。

- 学生（デモの主役）：`siti.rahmawati@student.lpk-demo.example` / `siswa-demo-123`
- 教師：`misaki.tanaka@lpk-demo.example` / `sensei-demo-123`
- 学生 UI は Bahasa Indonesia。以下に出す画面ラベルはインドネシア語表示。

## 1. 面接ロールプレイ（テキストモード、対比用・約30秒）
1. 学生でログイン。ホームの「Latihan wawancara AI」を開く。
2. 上部「Mode:」を **Teks** のまま、シナリオ「Wawancara: perawatan lansia（介護施設の採用面接、A2）」をタップ。
3. 面接官の質問に日本語で入力して送信。5回答で自動的にルーブリック評価が出る。

## 2. 面接ロールプレイ（音声モード）★本命

介護シナリオ「Wawancara: perawatan lansia」は候補者ターン5回で完了する（BUILD_PLAN のゴール「介護、3〜5ターン」に対応）。

### 2-0. 事前チェック
- backend / frontend が起動済み。学生でログイン済み。
- マイクが使え、ブラウザに ja-JP の読み上げ音声がある（Chrome は既定で有）。
- （実プロバイダ時のみ）backend 環境に ffmpeg がある。

### 2-1. 操作手順
1. ホーム → 「Latihan wawancara AI」。
2. 画面上部の「Mode:」トグルを **🎤 Suara** に切り替える。
   - モードは新規セッションに適用される。開始後は切り替えられないので、シナリオを選ぶ前に切り替える。
3. シナリオ「Wawancara: perawatan lansia」をタップ → 音声モードのセッション開始。
   - 面接官の開幕質問（自己紹介）が自動で読み上げられる。聞き直しは各面接官吹き出しの 🔊。
4. 下部の「🎤 Bicara」をタップ → マイク許可 → 録音開始。
   - 録音中は赤い「⏹ Berhenti」と「Merekam N detik」。45秒で自動停止する。
5. 話し終えたら「⏹ Berhenti」。「Memproses...」の後に、
   - 自分の回答（認識テキスト）が右側の吹き出しに出る。
   - 面接官の次の質問が左側に出て、自動で読み上げられる。
6. 4〜5 を計5回。5回目の回答後にルーブリック評価カードが出る（総合点 + 5軸 + インドネシア語の講評・アドバイス・模範解答）。
7. 一覧に戻ると、履歴一覧とスコア推移グラフに今の回が反映される。

### 2-2. stub と azure での画面の違い（説明用）
- stub：録音内容にかかわらず回答は定型の日本語（例「シティと申します。インドネシアから参りました。」）。読み上げはブラウザ内蔵音声。疎通と操作感の確認向け。
- azure：実際に話した日本語がそのまま認識テキストになる。読み上げは Nanami の自然な声。品質デモ向け。

### 2-3. トラブルとフォールバック
- マイク不許可：赤字「Mikrofon tidak bisa digunakan...」。ブラウザのマイク権限を許可して再度「🎤 Bicara」。
- 無音・認識失敗（azure 時）：「Suara tidak dikenali...」。もう一度はっきり話す。
- 読み上げが鳴らない：OS/ブラウザに ja-JP 音声が無い場合がある。🔊 で再試行するか、画面のテキストで代替する。
- 会場の音声が不安定：Mode を **Teks** に切り替えて同じ面接を実施する。事前録画も用意しておく（BUILD_PLAN Phase 6）。

## 今後追記
- 発音練習（実装済、手順未記載）
- 会話練習（実装済、手順未記載）
- 教師ダッシュボード（実装済、手順未記載）
- Talent Passport PDF（未実装）
- 企業向け共有リンク・候補者比較ビュー（未実装）
- Azure Container Apps の公開 URL での再現（未実施）
