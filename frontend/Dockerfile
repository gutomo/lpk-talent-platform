# frontend 配信イメージ：Vite ビルド成果物を nginx で配信し、/api を backend へプロキシする
# （vite dev proxy と同じ /api プレフィックス書き換え。同一オリジンなので CORS 不要）。
#   docker build -t lpk-frontend frontend
FROM node:22-alpine AS build
WORKDIR /app
# package.json に packageManager が無いため CI（pnpm v9）と合わせて major 固定
RUN npm install -g pnpm@9
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# nginx 公式 entrypoint が起動時に BACKEND_ORIGIN を envsubst して conf.d/default.conf を生成する。
# NGINX_ENTRYPOINT_LOCAL_RESOLVERS を立てると entrypoint が /etc/resolv.conf から
# NGINX_LOCAL_RESOLVERS をエクスポートする（テンプレートの resolver で使用）。
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
ENV BACKEND_ORIGIN=http://localhost:8001 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
EXPOSE 8080
