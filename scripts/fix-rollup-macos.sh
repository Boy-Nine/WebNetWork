#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/web-client"

echo "修复 macOS / Codex Node 环境下 Rollup native 包签名问题..."
# 本项目将 rollup 显式别名到 @rollup/wasm-node，避免加载 macOS .node 原生包。
npm install rollup@npm:@rollup/wasm-node@4.61.1 --save-dev
npm run build

echo "✅ Rollup/Vite 本机构建已恢复（使用 WASM Rollup，速度略慢但更稳）"
