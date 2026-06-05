#!/usr/bin/env bash
set -euo pipefail
PLUGIN_DIR="$HOME/.docker/cli-plugins"
mkdir -p "$PLUGIN_DIR"

echo "检查 Docker CLI..."
if ! command -v docker >/dev/null 2>&1; then
  if [[ -x /Applications/Docker.app/Contents/Resources/bin/docker ]]; then
    sudo ln -sf /Applications/Docker.app/Contents/Resources/bin/docker /usr/local/bin/docker
    echo "已修复 /usr/local/bin/docker 链接"
  else
    echo "未找到 Docker CLI，请重新安装或打开 Docker Desktop" >&2
    exit 1
  fi
fi

if [[ -f "$HOME/.docker/config.json" ]]; then
  cp "$HOME/.docker/config.json" "$HOME/.docker/config.json.bak-$(date +%Y%m%d%H%M%S)"
  python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.docker/config.json'
try:
    data = json.loads(p.read_text())
except Exception:
    data = {}
# Docker Desktop 缺少 docker-credential-desktop 时会导致 build/pull 失败。
data.pop('credsStore', None)
p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
PY
  echo "已备份并清理 ~/.docker/config.json 中可能失效的 credsStore"
fi

for name in compose buildx scout; do
  target="/Applications/Docker.app/Contents/Resources/cli-plugins/docker-$name"
  link="$PLUGIN_DIR/docker-$name"
  if [[ -e "$link" && ! -x "$link" ]]; then rm -f "$link"; fi
  if [[ -x "$target" ]]; then ln -sf "$target" "$link"; fi
done

echo "验证："
docker --version || true
docker compose version || true
