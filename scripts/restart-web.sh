#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
API_BASE="${PUBLIC_API_BASE:-http://0.0.0.0:3088}"
if [[ -f deploy.env ]]; then
  # shellcheck disable=SC1091
  source deploy.env
  API_BASE="${PUBLIC_API_BASE:-$API_BASE}"
fi

echo "构建 Web 镜像，API_BASE=$API_BASE"
docker build --build-arg "VITE_API_BASE=$API_BASE" -t chromenetwork-web:latest ./web-client

echo "重启 Web 容器 chromenetwork-web-1"
docker rm -f chromenetwork-web-1 >/dev/null 2>&1 || true
docker run -d --name chromenetwork-web-1 --network chromenetwork_default -p "${WEB_PORT:-3090}:80" --restart unless-stopped chromenetwork-web:latest
sleep 1
curl -fsS "http://0.0.0.0:${WEB_PORT:-3090}/health" && echo
