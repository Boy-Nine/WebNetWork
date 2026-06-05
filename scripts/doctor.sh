#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ok=0
fail=0
warn=0
say(){ printf '%s\n' "$*"; }
pass(){ say "✅ $*"; ok=$((ok+1)); }
bad(){ say "❌ $*"; fail=$((fail+1)); }
note(){ say "⚠️  $*"; warn=$((warn+1)); }
run(){ local name="$1"; shift; if "$@" >/tmp/chromenetwork_doctor.out 2>&1; then pass "$name"; else bad "$name"; sed -n '1,80p' /tmp/chromenetwork_doctor.out; fi }

say "API Capture 项目自检"
say "工作目录：$ROOT"
say ""

if [[ -f deploy.env ]]; then pass "deploy.env 存在"; else bad "deploy.env 不存在"; fi
if [[ -f chrome-extension/config.js ]]; then pass "插件 config.js 存在"; else bad "插件 config.js 不存在，请执行 ./scripts/apply-config.sh"; fi

if [[ -f deploy.env ]]; then
  # shellcheck disable=SC1091
  source deploy.env
  if [[ "${JWT_SECRET_KEY:-}" == "please-change-this-secret-at-least-32-bytes" || "${JWT_SECRET_KEY:-}" == "change-me-in-production-change-me-32bytes" ]]; then
    note "JWT_SECRET_KEY 仍是示例值；线上部署前必须改成 openssl rand -hex 32 生成的随机值"
  elif [[ ${#JWT_SECRET_KEY} -lt 32 ]]; then
    note "JWT_SECRET_KEY 长度小于 32，建议更换为至少 32 位随机字符串"
  else
    pass "JWT_SECRET_KEY 已配置为非默认值"
  fi
  if [[ "${POSTGRES_PASSWORD:-}" == "webgrabber" || "${POSTGRES_PASSWORD:-}" == "postgres" || -z "${POSTGRES_PASSWORD:-}" ]]; then
    note "POSTGRES_PASSWORD 仍是默认/弱密码；线上部署前必须修改"
  else
    pass "POSTGRES_PASSWORD 已配置为非默认值"
  fi
  if [[ "${CORS_ORIGINS:-*}" == "*" ]]; then
    note "CORS_ORIGINS=* 适合本地调试；线上建议改为 Web 域名和 chrome-extension://插件ID"
  else
    pass "CORS_ORIGINS 已限制来源"
  fi
fi

run "后端 Python 语法" python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
if [[ -d web-client/node_modules ]]; then pass "Web node_modules 存在"; else note "Web node_modules 不存在，可执行 npm --prefix web-client install"; fi
run "Web TypeScript 类型检查" npm --prefix web-client run typecheck
run "Web npm 高危漏洞检查" npm --prefix web-client audit --audit-level=high
run "插件 popup.js 语法" node --check chrome-extension/popup.js
run "插件 background.js 语法" node --check chrome-extension/background.js
run "插件 content.js 语法" node --check chrome-extension/content.js
run "插件 injected.js 语法" node --check chrome-extension/injected.js

if command -v docker >/dev/null 2>&1; then
  pass "docker 命令存在：$(command -v docker)"
  if docker compose version >/tmp/chromenetwork_doctor.out 2>&1; then
    pass "docker compose 可用：$(cat /tmp/chromenetwork_doctor.out | head -1)"
  else
    note "docker compose 不可用；可运行 ./scripts/repair-docker-mac.sh 尝试修复，或重装 Docker Desktop"
    sed -n '1,40p' /tmp/chromenetwork_doctor.out
  fi
else
  note "docker 命令不存在；如需容器部署请安装/修复 Docker Desktop"
fi

if curl -fsS http://0.0.0.0:3088/api/health >/tmp/chromenetwork_doctor.out 2>&1; then pass "后端健康：http://0.0.0.0:3088/api/health"; else note "后端健康检查未通过，服务可能未启动"; fi
if curl -fsS http://0.0.0.0:3090/health >/tmp/chromenetwork_doctor.out 2>&1; then pass "Web 健康：http://0.0.0.0:3090/health"; else note "Web 健康检查未通过，服务可能未启动"; fi

say ""
say "自检完成：✅ $ok / ⚠️ $warn / ❌ $fail"
if [[ $fail -gt 0 ]]; then exit 1; fi
