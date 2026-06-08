#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT/deploy.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ "$ENV_FILE" == "$ROOT/deploy.env" && -f "$ROOT/deploy.env.example" ]]; then
    cp "$ROOT/deploy.env.example" "$ROOT/deploy.env"
    echo "未找到 deploy.env，已从 deploy.env.example 复制一份。请按需修改后重新执行。"
  else
    echo "配置文件不存在：$ENV_FILE" >&2
    exit 1
  fi
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

required=(PUBLIC_API_BASE PUBLIC_WEB_BASE BACKEND_PORT WEB_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD JWT_SECRET_KEY)
for key in "${required[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    echo "缺少配置：$key" >&2
    exit 1
  fi
done

DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"

cat > "$ROOT/backend/.env" <<EOF_ENV
DATABASE_URL=${DATABASE_URL}
JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_EXPIRE_MINUTES=${JWT_EXPIRE_MINUTES:-10080}
MAX_HTML_SIZE_MB=${MAX_HTML_SIZE_MB:-5}
MAX_RESPONSE_BODY_MB=${MAX_RESPONSE_BODY_MB:-2}
MAX_UPLOAD_BYTES=${MAX_UPLOAD_BYTES:-12582912}
CORS_ORIGINS=${CORS_ORIGINS:-*}
EOF_ENV

cat > "$ROOT/web-client/.env.production" <<EOF_ENV
VITE_API_BASE=${PUBLIC_API_BASE}
EOF_ENV

cat > "$ROOT/web-client/.env" <<EOF_ENV
VITE_API_BASE=${PUBLIC_API_BASE}
EOF_ENV

cat > "$ROOT/chrome-extension/config.js" <<EOF_JS
// 此文件由 scripts/apply-config.sh 根据 deploy.env 自动生成。
// 修改地址请改项目根目录 deploy.env，然后重新执行脚本。
window.WEB_CAPTURE_CONFIG = {
  API_BASE: '${PUBLIC_API_BASE}',
  WEB_BASE: '${PUBLIC_WEB_BASE}'
};
EOF_JS

cat > "$ROOT/docker-compose.override.yml" <<EOF_YAML
# 此文件由 scripts/apply-config.sh 根据 deploy.env 自动生成。
services:
  db:
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
  backend:
    env_file:
      - ./backend/.env
    environment:
      DATABASE_URL: ${DATABASE_URL}
    ports:
      - "${BACKEND_PORT}:3088"
  web:
    build:
      args:
        VITE_API_BASE: ${PUBLIC_API_BASE}
    ports:
      - "${WEB_PORT}:80"
EOF_YAML

cat <<EOF_OK
配置已生成：
- $ROOT/backend/.env
- $ROOT/web-client/.env
- $ROOT/web-client/.env.production
- $ROOT/chrome-extension/config.js
- $ROOT/docker-compose.override.yml

当前对外地址：
- API: ${PUBLIC_API_BASE}
- Web: ${PUBLIC_WEB_BASE}

下一步：
  docker compose up -d --build
EOF_OK
