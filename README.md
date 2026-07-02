# LPK Talent Platform (PoC)

生成AI日本語・面接・人材品質可視化パッケージの PoC 実装。
行動規範は [CLAUDE.md](CLAUDE.md)、フェーズ計画は [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) を参照。

## 現状
Phase 0 スライス1（土台スケルトン）まで。backend の `/health`、frontend の疎通表示、
docker compose(postgres)、CI が動く。データモデル / 認証 / seed は後続スライス。

## 必要ツール
python 3.12（uv が取得）, uv, node 22, pnpm 9, docker, ffmpeg, git。
`make` は任意（未導入なら下の直接コマンドを使う）。

## 起動（直接コマンド）
`make` が無い環境向けの一次手順。

### backend
ポートは 8001（8000 は既存の voice-ai-tutor demo が使うため回避）。
```
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8001
# 確認: http://localhost:8001/health -> {"status":"ok"}
```

### frontend
```
cd frontend
pnpm install
pnpm dev
# http://localhost:5173 （/api は backend:8001 にproxy）
```

### DB（任意。/health は DB非依存で通る）
```
docker compose up -d db
# 確認: http://localhost:8001/health/db
```

## テスト / lint
```
cd backend  && uv run ruff check && uv run pytest
cd frontend && pnpm lint && pnpm build
```

## make を使う場合
`make backend` / `make frontend` / `make test` / `make lint` / `make migrate`。
