# 网页数据捕获插件 + 后端解析存储 + Web数据管理平台（优化版）

完整工具链：Chrome Extension 捕获网页 HTML / Fetch / XHR，FastAPI 后端认证、解析与存储，React PC 管理端查询详情并导出 Excel。

## 技术栈

- 插件：Chrome Extension Manifest V3，content script 注入页面脚本，重写 `fetch` / `XMLHttpRequest`
- 后端：Python 3.11 + FastAPI + SQLAlchemy + PostgreSQL JSONB + JWT + bcrypt
- Web：React 18 + TypeScript + Ant Design 5 + Axios + 原生 Blob 导出 Excel 兼容 HTML
- 部署：Docker Compose

## 文件树

```text
/Users/admin/Documents/ChromeNetWork
├── chrome-extension/
│   ├── manifest.json
│   ├── popup.html
│   ├── popup.css
│   ├── popup.js
│   ├── background.js
│   ├── content.js
│   ├── injected.js
│   └── icons/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── routes/
│   │   ├── user.py
│   │   └── capture.py
│   ├── utils/
│   │   ├── security.py
│   │   └── parser.py
│   ├── sql/init.sql
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── web-client/
│   ├── src/main.tsx
│   ├── src/style.css
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
├── docker-compose.yml
└── README.md
```


## 全局配置：本地/线上只改一个文件

本项目现在统一使用根目录 `/Users/admin/Documents/ChromeNetWork/deploy.env` 做全局部署配置。以后本地调试、局域网访问、线上部署，优先只改这个文件。

默认配置已经把对外地址从 `localhost/127.0.0.1` 改成 `0.0.0.0`：

```env
PUBLIC_API_BASE=http://0.0.0.0:3088
PUBLIC_WEB_BASE=http://0.0.0.0:3090
BACKEND_PORT=3088
WEB_PORT=3090
```

如果你想让同一局域网的其他设备访问，把 `0.0.0.0` 改成你本机 IP，例如：

```env
PUBLIC_API_BASE=http://192.168.1.23:3088
PUBLIC_WEB_BASE=http://192.168.1.23:3090
```

Mac 查看本机局域网 IP：

```bash
ipconfig getifaddr en0
# 或
ifconfig | grep 'inet '
```

线上部署时改成域名：

```env
PUBLIC_API_BASE=https://api.example.com
PUBLIC_WEB_BASE=https://capture.example.com
JWT_SECRET_KEY=请改成至少32位随机字符串
POSTGRES_PASSWORD=请改成数据库强密码
CORS_ORIGINS=https://capture.example.com,chrome-extension://你的插件ID
```

改完 `/Users/admin/Documents/ChromeNetWork/deploy.env` 后执行：

```bash
cd /Users/admin/Documents/ChromeNetWork
./scripts/apply-config.sh
docker compose up -d --build
```

`apply-config.sh` 会自动生成/更新：

- `/Users/admin/Documents/ChromeNetWork/backend/.env`
- `/Users/admin/Documents/ChromeNetWork/web-client/.env`
- `/Users/admin/Documents/ChromeNetWork/web-client/.env.production`
- `/Users/admin/Documents/ChromeNetWork/chrome-extension/config.js`
- `/Users/admin/Documents/ChromeNetWork/docker-compose.override.yml`

所以你不需要再分别去改 Web、插件、Docker 的地址。

> 注意：`0.0.0.0` 适合服务监听和本机测试；如果 Chrome 扩展要在别的电脑访问你的服务，请使用你的本机局域网 IP 或线上 HTTPS 域名。

## 当前端口规划与避免冲突

本项目已避开常见的 `5173` / `8000`：

- 后端 API：`PUBLIC_API_BASE`，默认 `http://0.0.0.0:3088`
- FastAPI 文档：`PUBLIC_API_BASE/docs`
- Web PC 管理端：`PUBLIC_WEB_BASE`，默认 `http://0.0.0.0:3090`
- PostgreSQL：Docker 内部使用 `5432`，默认不映射到宿主机，避免和本机数据库冲突。

如需改 Web 或后端端口，直接改 `/Users/admin/Documents/ChromeNetWork/deploy.env`：

```env
BACKEND_PORT=3088
WEB_PORT=3090
PUBLIC_API_BASE=http://你的IP或域名:3088
PUBLIC_WEB_BASE=http://你的IP或域名:3090
```

然后重新执行：

```bash
./scripts/apply-config.sh
docker compose up -d --build
```

## npm install / audit 注意点

你看到的：

```text
up to date ...
1 high severity vulnerability
```

不是 `npm install` 失败，而是 npm 安装成功后给出的安全审计提示。之前来源是 `xlsx` 包，`npm audit` 显示该包存在 high severity 且 `No fix available`。当前已移除 `xlsx`、`exceljs`、`file-saver`，改为原生 `Blob` 生成 Excel 可打开的 `.xls` HTML 文件，因此 `npm audit` 已为 0 漏洞。

建议使用：

```bash
cd /Users/admin/Documents/ChromeNetWork/web-client
npm install
npm audit --audit-level=high
npm run build
```


## 一键自检与常用维护脚本

项目现在提供 3 个维护脚本，建议每次改完代码先跑自检：

```bash
cd /Users/admin/Documents/ChromeNetWork
./scripts/doctor.sh
```

`doctor.sh` 会检查：

- `deploy.env` 与插件 `config.js` 是否存在
- 后端 Python 语法
- Web TypeScript 类型
- npm 高危漏洞
- 插件 JS 语法
- Docker / docker compose 是否可用
- 后端/Web 健康接口

如果 Docker Desktop 的 CLI 链接、compose 插件或 credential helper 损坏，可先尝试：

```bash
./scripts/repair-docker-mac.sh
```

如果只是要重建并重启 WebPC 容器，可用：

```bash
./scripts/restart-web.sh
```

> 注意：`restart-web.sh` 依赖 Docker 可用；如果 `doctor.sh` 提示 `docker 命令不存在`，请先重新打开/更新 Docker Desktop，或运行 `repair-docker-mac.sh`。

### 本机 Node / Rollup 注意

部分 macOS + Node 24 环境可能遇到 Rollup 原生 optional 包签名问题，表现为本机 `npm run build` 报 `@rollup/rollup-darwin-arm64` 相关错误。项目已将 `rollup` 显式别名到 `@rollup/wasm-node`，避免加载 macOS 原生 `.node` 包。

可先尝试自动修复：

```bash
./scripts/fix-rollup-macos.sh
```

生产部署以 Docker Linux 构建为准：

```bash
./scripts/restart-web.sh
```

日常开发可先用：

```bash
npm --prefix web-client run typecheck
```

确认 TypeScript 通过；真正发布时走 Docker 构建。

## 快速启动

```bash
cd /Users/admin/Documents/ChromeNetWork
./scripts/apply-config.sh
docker compose up --build
```

服务地址：

- 后端 API：默认 `http://0.0.0.0:3088`，以 `deploy.env` 的 `PUBLIC_API_BASE` 为准
- API 文档：默认 `http://0.0.0.0:3088/docs`
- Web 管理端：默认 `http://0.0.0.0:3090`，以 `deploy.env` 的 `PUBLIC_WEB_BASE` 为准


## 线上服务器部署启动指南

下面以一台 Linux 服务器为例，假设你的服务器公网域名是：

- API 域名：`https://api.example.com`
- PC 管理端域名：`https://capture.example.com`

如果你暂时没有域名，也可以先用服务器 IP + 端口测试，例如：

- 后端：`http://服务器IP:3088`
- PC 管理端：`http://服务器IP:3090`

> 注意：Chrome 扩展请求线上接口时，建议最终使用 HTTPS 域名；生产环境不要继续使用 `localhost`。

### 1. 服务器准备

服务器需要安装：

- Docker
- Docker Compose v2
- Git

Ubuntu / Debian 可参考：

```bash
sudo apt update
sudo apt install -y git ca-certificates curl

# 安装 Docker，若服务器已安装可跳过
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# 重新登录 SSH 后验证
 docker --version
 docker compose version
```

如果云厂商安全组或服务器防火墙开启了限制，需要放行：

- `3088/tcp`：后端 API，如果你不用 nginx 反向代理，需放行
- `3090/tcp`：PC 管理端，如果你不用 nginx 反向代理，需放行
- `80/tcp`、`443/tcp`：如果使用 nginx + 域名 + HTTPS，需放行

PostgreSQL 默认只在 Docker 内部访问，本项目没有把 `5432` 暴露到公网，不建议开放数据库端口。

### 2. 上传或拉取项目代码

方式一：服务器上直接 git clone：

```bash
cd /opt
git clone <你的仓库地址> ChromeNetWork
cd /opt/ChromeNetWork
```

方式二：本地打包上传：

```bash
# 本地执行
cd /Users/admin/Documents
tar --exclude='ChromeNetWork/web-client/node_modules' \
    --exclude='ChromeNetWork/web-client/dist' \
    --exclude='ChromeNetWork/.git' \
    -czf ChromeNetWork.tar.gz ChromeNetWork

scp ChromeNetWork.tar.gz root@服务器IP:/opt/

# 服务器执行
cd /opt
tar -xzf ChromeNetWork.tar.gz
cd /opt/ChromeNetWork
```

### 3. 修改生产配置

线上、本地、局域网都只改 `/opt/ChromeNetWork/deploy.env`。

#### 3.1 使用服务器 IP 临时部署

```env
PUBLIC_API_BASE=http://服务器IP:3088
PUBLIC_WEB_BASE=http://服务器IP:3090
BACKEND_PORT=3088
WEB_PORT=3090
POSTGRES_PASSWORD=改成强密码
JWT_SECRET_KEY=改成至少32位随机字符串
CORS_ORIGINS=*
```

#### 3.2 使用正式 HTTPS 域名部署

```env
PUBLIC_API_BASE=https://api.example.com
PUBLIC_WEB_BASE=https://capture.example.com
BACKEND_PORT=3088
WEB_PORT=3090
POSTGRES_PASSWORD=改成强密码
JWT_SECRET_KEY=改成至少32位随机字符串
CORS_ORIGINS=https://capture.example.com,chrome-extension://你的插件ID
```

生成随机 JWT 密钥示例：

```bash
openssl rand -hex 32
```

如果你还不知道 Chrome 扩展 ID，第一次加载扩展后可在 `chrome://extensions/` 里看到。开发/测试阶段可以先用 `CORS_ORIGINS=*`，生产建议改成明确域名和扩展来源。

改完后执行：

```bash
cd /opt/ChromeNetWork
./scripts/apply-config.sh
```

脚本会自动生成后端 `.env`、Web `.env`、插件 `config.js` 和 Docker override 配置。不要再分别手动改 `popup.js`、`main.tsx`、`docker-compose.yml`。

### 4. 启动服务

在服务器执行：

```bash
cd /opt/ChromeNetWork
./scripts/apply-config.sh
docker compose up -d --build
```

查看容器状态：

```bash
docker compose ps
```

正常应看到：

- `db`：healthy
- `backend`：healthy
- `web`：healthy

查看日志：

```bash
docker compose logs -f backend
docker compose logs -f web
docker compose logs -f db
```

### 5. 验证线上服务

```bash
curl http://0.0.0.0:3088/api/health
curl -I http://0.0.0.0:3090
```

如果你直接暴露端口，也可以从本机电脑访问：

```bash
curl http://服务器IP:3088/api/health
```

浏览器访问：

```text
http://服务器IP:3090
```

或者你的域名：

```text
https://capture.example.com
```

### 6. 推荐的 Nginx 反向代理 HTTPS 部署

生产环境推荐不要直接暴露 `3088/3090`，而是用 nginx 统一走 HTTPS：

```nginx
server {
    listen 80;
    server_name api.example.com capture.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    client_max_body_size 15m;

    location / {
        proxy_pass http://127.0.0.1:3088;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 443 ssl http2;
    server_name capture.example.com;

    ssl_certificate /etc/letsencrypt/live/capture.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/capture.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3090;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

证书可以用 certbot 申请，例如：

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d api.example.com -d capture.example.com
```

使用 nginx 反向代理后，云安全组只需要开放 `80/443`，`3088/3090` 可以只允许本机访问或不对公网开放。

### 7. Chrome 扩展上线使用步骤

1. 修改根目录 `deploy.env`：
   - `PUBLIC_API_BASE` 改为线上后端地址
   - `PUBLIC_WEB_BASE` 改为线上 PC 管理端地址
2. 执行 `./scripts/apply-config.sh` 生成 `chrome-extension/config.js`
3. 打开 Chrome：`chrome://extensions/`
4. 开启“开发者模式”
5. 点击“加载已解压的扩展程序”
6. 选择 `/opt/ChromeNetWork/chrome-extension` 对应的本地目录副本
7. 打开目标网页后刷新一次
8. 点击插件，登录账号，点击“开始记录”
9. 在页面中触发搜索/翻页/点击产生接口后，点击“停止并上报”；再点击“查看接口数据”进入线上 PC 管理端查看记录

如果是给其他电脑使用，需要把 `chrome-extension` 目录发给对方，或在 Chrome 扩展页点击“打包扩展程序”生成 `.crx`。

### 8. 常用运维命令

```bash
cd /opt/ChromeNetWork

# 启动 / 更新并重建
docker compose up -d --build

# 停止服务
docker compose down

# 查看状态
docker compose ps

# 看后端日志
docker compose logs -f backend

# 看最近 100 行日志
docker compose logs --tail=100 backend

# 重启后端
docker compose restart backend

# 进入数据库
docker compose exec db psql -U webgrabber -d webgrabber
```

备份数据库：

```bash
cd /opt/ChromeNetWork
mkdir -p backups
docker compose exec -T db pg_dump -U webgrabber webgrabber > backups/webgrabber_$(date +%F_%H%M%S).sql
```

恢复数据库：

```bash
cat backups/xxx.sql | docker compose exec -T db psql -U webgrabber -d webgrabber
```

### 9. 线上部署注意事项

- 必须修改 `JWT_SECRET_KEY`，不要使用示例值。
- 必须修改 PostgreSQL 密码，并同步修改 `DATABASE_URL`。
- 生产环境建议使用 HTTPS，否则 Chrome 扩展请求、浏览器安全策略、登录态都更容易遇到限制。
- 如果 PC Web 页面打开正常但登录报错，优先检查 `deploy.env` 的 `PUBLIC_API_BASE`，然后重新执行 `./scripts/apply-config.sh && docker compose up -d --build`。
- 如果插件登录/上传失败，优先检查 `deploy.env` 的 `PUBLIC_API_BASE` 和 `chrome-extension/config.js` 是否已重新生成，并在 Chrome 扩展页点“重新加载”。
- 如果上传大页面失败，检查 nginx `client_max_body_size`，建议至少 `15m`；同时后端有 `MAX_UPLOAD_BYTES`、`MAX_HTML_SIZE_MB` 限制。
- `docker compose down -v` 会删除数据库 volume，生产环境不要随便加 `-v`。
- 更新代码后执行 `docker compose up -d --build`，否则 Web 端构建时写入的 API 地址不会更新。

## 后端开发模式

```bash
cd /Users/admin/Documents/ChromeNetWork
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
export DATABASE_URL='postgresql+psycopg2://webgrabber:webgrabber@0.0.0.0:5432/webgrabber'
export JWT_SECRET_KEY='please-change-this-secret-at-least-32-bytes'
uvicorn backend.main:app --reload --host 0.0.0.0 --port 3088
```

环境变量见 `/Users/admin/Documents/ChromeNetWork/backend/.env.example`：

```env
DATABASE_URL=postgresql+psycopg2://webgrabber:webgrabber@db:5432/webgrabber
JWT_SECRET_KEY=please-change-this-secret-at-least-32-bytes
JWT_EXPIRE_MINUTES=10080
MAX_HTML_SIZE_MB=5
MAX_RESPONSE_BODY_MB=2
MAX_UPLOAD_BYTES=12582912
```

## Web 管理端开发模式

```bash
cd /Users/admin/Documents/ChromeNetWork/web-client
npm install
npm run dev
# 默认监听在 http://0.0.0.0:3090
```

可用 `.env` 覆盖 API：

```env
VITE_API_BASE=http://0.0.0.0:3088
```


## 插件 UI 与动画专项说明（API Capture v1.2）

本轮插件侧重点从“能用”升级到“好用、稳定、反馈清晰”：

- 插件名称已统一为 **API Capture**，版本 `1.2.0`。
- 点击扩展图标默认打开 **Chrome 右侧 Side Panel**，不会因为你在网页中翻页、搜索、点击而自动关闭。
- `popup.html` 现在只是精美入口页；真正的记录面板在 `/Users/admin/Documents/ChromeNetWork/chrome-extension/sidepanel.html`。
- 插件面板宽度按 400px 设计，采用卡片式布局、12px+ 圆角、柔和阴影、浅色渐变背景和毛玻璃卡片。

### 主题切换

侧边栏右上角有主题按钮：

- `◐`：跟随系统主题（默认）
- `☀`：强制浅色主题
- `☾`：强制深色主题

主题配置会保存到 Chrome 扩展本地存储：

```js
chrome.storage.local.theme
```

如果要恢复默认，连续点击主题按钮切回 `◐` 即可。

### 记录状态动画

插件记录流程的视觉反馈：

- 打开面板：整体淡入 + 轻微上移动画。
- 登录 / 注册切换：横向滑动 + 淡入淡出。
- 输入框聚焦：蓝色边框和光晕。
- 开始记录：按钮按压涟漪，状态切换为 `Recording`，圆形计数器进入红橙色脉冲动画。
- 捕获新接口：计数器弹动，并显示 `+1` 飞行动画。
- 停止并上报：按钮 loading，显示 shimmer 条纹上传进度条，状态切换为 `Uploading`。
- 上报成功 / 失败：顶部 toast 滑入提示；失败按钮会轻微 shake，数据保留可重试。
- 登出：主内容淡出后回到登录卡片。

动画样式集中在：

```text
/Users/admin/Documents/ChromeNetWork/chrome-extension/popup.css
```

核心动画包括：`panelIn`、`cardIn`、`formSwitch`、`ripple`、`pulseRing`、`dotPulse`、`countBump`、`plusFly`、`shimmerMove`、`toastIn/toastOut`、`shake`、`liveIn`。

### 减少动态效果

插件支持系统级 `prefers-reduced-motion: reduce`。如果用户系统开启“减少动态效果”，插件会自动把动画和过渡时长降到极短，并禁用 hover 位移，避免造成视觉负担。

### 更新插件后必须做的一步

修改 `/Users/admin/Documents/ChromeNetWork/chrome-extension` 下任何文件后，Chrome 不会自动重新加载开发版扩展。需要手动：

1. 打开 `chrome://extensions/`
2. 找到 **API Capture**
3. 点击“重新加载”
4. 回到目标网页刷新一次，再打开右侧记录面板

## 固定插件侧边栏与接口拦截说明

当前插件已改为 Chrome Side Panel 固定侧边栏模式：

- 点击扩展图标会打开浏览器右侧固定面板。
- 在网页里点击、翻页、搜索时，面板不会像 popup 一样自动关闭。
- 如果你刚更新代码，需要到 `chrome://extensions/` 点击本扩展的“重新加载”。
- 如仍没打开侧边栏，可右键扩展图标，选择“打开侧边栏”。

关于“为什么没有出现 xxx 正在调试此浏览器”：

- 当前默认捕获方式不是 `chrome.debugger`。
- 插件使用 content script 注入 `injected.js`，在页面环境中重写 `fetch` 和 `XMLHttpRequest`。
- 所以不会出现 Chrome 的调试提示条。
- 这仍然是在拦截页面新发起的 XHR/Fetch；只是不使用 DevTools Protocol。
- 只有未来切换到 `chrome.debugger` 高级模式时，才会出现“正在调试此浏览器”的提示。

## 插件手动记录模式

当前插件采用“手动记录式”流程：

1. 打开目标网页。
2. 点击插件图标。
3. 登录后点击“开始记录”。
4. 在目标网页中执行搜索、点击、翻页等操作，让页面新发起 XHR/Fetch。
5. 插件弹窗会显示“记录中... 已捕获 N 个接口”。
6. 点击“停止并上报”，插件会停止记录并把本次会话捕获的接口列表上传到 `/api/capture/upload`。
7. 上传成功后清空本次缓存，可以在同一页面再次开始记录。
8. 如果上报失败，数据会保留在当前页面，可以重试；也可以点击“放弃记录”清空。

特点：

- 只记录点击“开始记录”之后新发起的请求。
- 不回溯开始之前已经发生的请求。
- 每个标签页独立记录。
- 单次最多保留 200 个接口，响应体默认最多 2MB。
- 上报后后端会写入 `capture_sessions` 和 `captured_apis`。

插件通信动作：

- `startRecording`：开始并清空上一次缓存。
- `stopRecording`：停止记录，不清空。
- `getCapturedRequests`：读取当前会话接口列表。
- `clearCapturedRequests`：上报成功或放弃时清空。

## 加载 Chrome 扩展

1. 打开 `chrome://extensions/`
2. 开启“开发者模式”
3. 点击“加载已解压的扩展程序”
4. 选择 `/Users/admin/Documents/ChromeNetWork/chrome-extension`
5. 打开目标网页并刷新，让 `content.js` 在 `document_start` 注入
6. 点击插件图标，注册/登录，点击“开始记录”，在页面中触发接口后点击“停止并上报”

## 接口解析存储说明

当前版本上传捕获数据后，后端会做两层存储：

1. `capture_records`：保留原始捕获包，包含页面 URL、HTML 快照、xhrList 原始 JSON。
2. `capture_sessions`：记录一次插件捕获动作，用于关联同一批接口。
3. `captured_apis`：核心接口数据表，每条 XHR/Fetch 拆成一条接口记录。

`captured_apis` 中会保存：

- `user_id`：所属用户
- `method`：GET/POST/PUT/DELETE 等
- `url`：完整接口 URL
- `request_headers` / `response_headers`
- `request_params`：GET query 或 JSON/form body 解析结果
- `request_body_raw`：原始请求体
- `response_status`：HTTP 状态码
- `response_body`：JSON 响应解析结果
- `response_body_text` / `response_body_raw`：非 JSON 或原始响应体
- `duration_ms`：耗时
- `page_url`：所属页面
- `captured_at`：捕获时间

解析逻辑在 `/Users/admin/Documents/ChromeNetWork/backend/utils/api_parser.py`：

- GET：解析 URL query 到 `request_params`。
- POST/PUT/PATCH/DELETE：优先尝试 JSON body；失败后尝试 `application/x-www-form-urlencoded`；再失败则保存 raw。
- 响应体：优先尝试 JSON，成功写入 `response_body`；失败写入 `response_body_text`，同时保留 `response_body_raw`。

WebPC 默认调用 `/api/apis/list` 展示 `captured_apis` 解析后的接口数据，而不是原始捕获包。


## 本轮稳定性与安全优化说明

### 上传接口单条容错

`POST /api/capture/upload` 现在对 `xhrList` 中的单条异常数据做隔离处理：

- 某一个接口解析失败，不会导致整批上传失败。
- 成功解析的接口仍会写入 `captured_apis` / 标签数据表。
- 返回值新增：

```json
{
  "skippedCount": 1,
  "skipped": [
    { "index": 3, "url": "https://...", "error": "..." }
  ]
}
```

这样插件上报一批接口时，即使有个别异常响应体/格式，也不会把整次记录浪费掉。

### doctor 安全自检

`./scripts/doctor.sh` 现在会额外检查线上常见误配：

- `JWT_SECRET_KEY` 是否仍为示例值或长度不足
- `POSTGRES_PASSWORD` 是否仍为默认弱密码
- `CORS_ORIGINS` 是否仍为 `*`

本地调试允许出现警告；线上部署前请处理这些警告。推荐生成 JWT 密钥：

```bash
openssl rand -hex 32
```

然后写入 `deploy.env`：

```env
JWT_SECRET_KEY=生成的随机值
POSTGRES_PASSWORD=强密码
CORS_ORIGINS=https://capture.example.com,chrome-extension://你的插件ID
```

改完后执行：

```bash
./scripts/apply-config.sh
./scripts/doctor.sh
```

## API 文档摘要

FastAPI 自动文档：默认 `http://0.0.0.0:3088/docs`

### 注册

`POST /api/user/register`

```json
{ "phone": "13800138000", "password": "123456" }
```

返回：

```json
{ "code": 0, "message": "注册成功", "userId": 1 }
```

### 登录

`POST /api/user/login`

返回：

```json
{ "code": 0, "token": "jwt", "userId": 1, "phone": "13800138000" }
```

### 上传捕获数据

`POST /api/capture/upload`

Header：`Authorization: Bearer <token>`

```json
{
  "url": "https://example.com/page",
  "title": "页面标题",
  "htmlContent": "<html>...</html>",
  "xhrList": [],
  "captureTime": "2026-06-03T12:00:00Z"
}
```

返回：

```json
{ "code": 0, "message": "上传成功", "recordId": 123 }
```

### 查询列表

`GET /api/data/list?page=1&pageSize=20&startTime=...&endTime=...&urlKeyword=...`

返回：

```json
{ "code": 0, "data": { "total": 100, "list": [] } }
```

### 详情

`GET /api/data/{id}`

返回该记录 HTML、XHR JSON 和解析摘要。

### 导出 JSON

`GET /api/data/export?startTime=...&endTime=...&urlKeyword=...`

Web 管理端调用该接口后用 SheetJS 生成 Excel。

## 数据库初始化 SQL

ORM 会自动建表。手动 SQL 位于：

`/Users/admin/Documents/ChromeNetWork/backend/sql/init.sql`

主要表：

- `users`：手机号、密码哈希、注册时间
- `capture_records`：用户ID、URL、标题、HTML、XHR JSONB、解析摘要、捕获时间

## 关键实现说明

### 插件劫持逻辑

`/Users/admin/Documents/ChromeNetWork/chrome-extension/content.js` 在 `document_start` 注入 `/Users/admin/Documents/ChromeNetWork/chrome-extension/injected.js`。

`injected.js` 做三件事：

1. 重写 `window.fetch`：记录 method、url、headers、requestBody；使用 `response.clone().text()` 读取响应副本，避免影响页面自身读取响应。
2. 重写 `XMLHttpRequest.open/send/setRequestHeader`：保存请求元信息，并在 `loadend` 时记录状态码、响应体和耗时。
3. 将记录保存到 `window.__capturedRequests`，最多保留最近 50 个请求；响应体最大约 2MB，超出截断并标记。

popup 点击捕获时通过：

```js
chrome.tabs.sendMessage(tab.id, { action: 'getData' })
```

content script 返回：URL、标题、HTML 快照、XHR 列表。上传成功后 popup 再发送：

```js
chrome.tabs.sendMessage(tab.id, { action: 'clearData' })
```

清空当前页面缓存，避免重复上传。

## 安全与性能

- 密码使用 bcrypt 哈希。
- JWT 使用服务端密钥签名并严格校验，后端从 token 获取 userId，忽略前端伪造的 userId。
- ORM 查询防 SQL 注入。
- 后端限制上传大小：HTML 默认 5MB、单个请求/响应体默认 2MB、XHR 列表最多 200 条。
- 插件端最多保存最近 50 条请求，控制内存占用。
- Web 端不执行 HTML，只在 `<pre>` 中作为文本展示，降低 XSS 风险。

## 注意事项

- 该捕获方案无法捕获注入前已经完成的极早期请求；建议安装插件后刷新目标页面再捕获。
- 某些 Chrome 内置页、扩展商店页、受保护页面不允许 content script 注入。
- 二进制响应、流式响应、特殊跨域响应可能只能记录摘要或 unreadable 标记。

## UI 增强说明

### Chrome 插件 Popup

- 宽度 400px，卡片式布局，圆角 16px，轻量阴影。
- 使用蓝色渐变主按钮， hover 有轻微上浮反馈。
- 支持 `prefers-color-scheme`，在系统深色模式下自动切换深色变量。
- 登录/注册表单包含手机号、密码图标、实时校验、内联错误提示。
- 登录后显示头像圆圈、欢迎语、脱敏手机号、用户 ID。
- 捕获上传过程中按钮禁用并显示旋转 loading，成功/失败使用顶部 toast 提示。

### Web 管理端

- 使用专业后台布局：左侧导航栏 + 顶部导航 + 内容卡片区。
- 内容最大宽度 1200px，居中展示。
- 筛选区、统计区、表格区均为卡片式设计。
- 表格支持横向滚动、斑马纹、hover 高亮、URL tooltip。
- 详情使用 Drawer：页面快照、网络请求列表、解析摘要三 Tab。
- 网络请求以折叠面板展示，支持复制请求 JSON；HTML 支持复制和新窗口预览。
- 小屏幕下侧栏可收起，筛选项纵向排列，表格横向滚动。

## 动画优化说明

### 动画原则

项目统一使用 Material 风格缓动曲线：

```css
cubic-bezier(.4, 0, .2, 1)
```

优先动画属性为 `transform` 与 `opacity`，减少布局重排；复杂列表场景仅使用轻量 CSS stagger。

### Chrome 插件动画

动画样式位于：

`/Users/admin/Documents/ChromeNetWork/chrome-extension/popup.css`

主要效果：

- popup 打开：整体淡入 + `scale(.98) -> scale(1)`。
- 卡片挂载：`translateY(10px) -> 0` 轻微上浮淡入。
- 登录/注册切换：表单交叉淡变 + 横向滑动。
- 输入框聚焦：边框颜色过渡 + 外发光 + 轻微上移。
- 错误提示：从下方滑入，使用 `max-height / opacity / transform` 过渡。
- 按钮点击：`scale(.97)`，并通过 JS 注入坐标实现 CSS ripple 水波纹。
- 上传 loading：旋转 spinner，按钮文字透明度变化。
- toast：顶部滑入，自动淡出滑出。
- 登出：主内容淡出后切换到未登录态。

### Web 管理端动画

动画样式位于：

`/Users/admin/Documents/ChromeNetWork/web-client/src/style.css`

React 动画使用：

- `framer-motion`：页面内容淡入 + 横向滑动。
- Ant Design 默认 Drawer/Tabs 动画，叠加自定义 CSS 微调。

主要效果：

- 登录卡片：淡入 + 上移 + 缩放恢复。
- 背景装饰圆：低频 floating 动画。
- 内容区：进入时淡入上移。
- 侧栏：折叠/展开平滑过渡。
- 菜单项：hover 横向微移，激活项左侧指示条平滑出现。
- 统计卡片/筛选卡片/表格卡片：hover 上浮 + 阴影加深。
- 表格加载：Ant Design Skeleton + 自定义 shimmer 渐变波纹。
- 查询刷新：表格半透明 loading overlay 淡入。
- 表格行：每行按 30ms stagger 依次淡入上浮。
- Drawer：遮罩淡入，内容轻微缩放淡入。
- Tabs：内容区交叉淡变。
- 导出 Excel：按钮显示 `生成中...` 和 loading，完成后 toast 提示。

### 减少动态效果兼容

插件与 Web 均支持：

```css
@media (prefers-reduced-motion: reduce) { ... }
```

当用户系统开启“减少动态效果”时，会将动画和过渡时长降到极短，并禁用 hover 位移动效。

## 时间段查询说明

PC 管理端“数据管理”页支持按捕获时间查询：

- 日期控件选择开始/结束时间后点“查询”。
- “今天”“最近7天”会自动填充时间段并立即查询。
- 当前筛选条件会显示在筛选卡片底部。
- 导出 Excel 使用与当前列表相同的时间段和 URL 关键字条件。

后端接口参数：

```text
GET /api/data/list?page=1&pageSize=20&startTime=2026-06-03T00:00:00%2B08:00&endTime=2026-06-03T23:59:59%2B08:00
GET /api/data/export?startTime=...&endTime=...&urlKeyword=...
```

兼容别名：`start/end/keyword`。后端优先按 `capture_time` 查询；如老数据缺少 `capture_time`，会 fallback 到 `created_at`。

## Docker Web 容器 node_modules 注意点

Web 服务在 Docker 中使用生产构建：`web-client/Dockerfile` 会先 `npm ci && npm run build`，再用 nginx 托管静态文件。

这样避免容器运行时执行 `npm install && vite dev`，也避免 Mac 本机 `node_modules` 挂进 Linux 容器导致 Vite/esbuild 出现 `SIGBUS`。

如需本地开发热更新，可不走 Docker web 服务，直接执行：

```bash
cd /Users/admin/Documents/ChromeNetWork/web-client
npm install
npm run dev
```

## 已知潜在问题修复记录

- `passlib[bcrypt]` 与新版 `bcrypt 5.x` 不兼容会导致注册 500：已固定 `bcrypt==4.0.1`，并改用 `bcrypt_sha256` 规避 bcrypt 72 bytes 密码限制。
- 后端启动早于 PostgreSQL 可连接会失败：已加入 DB healthcheck 与后端建表重试。
- PC Web 时间段查询：已修复查询按钮可能使用旧状态的问题；后端同时兼容 `startTime/endTime` 与 `start/end`，并按 `capture_time` 查询，旧数据 fallback `created_at`。
- Docker Web 运行方式：已改为 `npm ci && npm run build` 后由 nginx 托管，避免运行时 Vite dev server 和跨平台 `node_modules` 引起的 `SIGBUS`。
- Web Docker 构建上下文：已添加 `/Users/admin/Documents/ChromeNetWork/web-client/.dockerignore`，避免上传 `node_modules/dist` 导致构建慢。

## 继续优化记录（稳定版）

- 前端依赖已从 `latest` 改为固定稳定版本，避免未来安装拉到不兼容版本。
- 前端升级到 `vite@6.4.3`、`axios@1.17.0`，本地 `npm audit` 已为 0 漏洞。
- Docker Web 构建改用 `node:20-bookworm-slim`，避免 Alpine/musl 原生依赖导致构建 `SIGBUS`。
- Docker Compose 已为 backend/web 增加 healthcheck，web 会等待 backend healthy 后启动。
- PC 管理端增加“刷新”“最近30天”、当前筛选条件和最近刷新时间展示。
- PC 管理端错误提示会解析 FastAPI validation error，不再直接显示 `[object Object]`。

## 自检优化记录（端到端验收后）

本轮已自动验收并修复以下问题：

- 修复 `/api/data/export` 被 `/api/data/{record_id}` 动态路由抢占导致 422 的问题：现在 `export` 路由声明在动态 id 路由之前。
- 修复上传解析摘要 `status_counts` 只统计 `status`、不统计插件字段 `responseStatus` 的问题。
- 新增记录删除能力：`DELETE /api/data/{record_id}`，Web 端支持单条删除、勾选批量删除。
- 插件 content script 增加防重复安装标记，避免 popup 主动注入时重复注册 message listener。
- 插件 popup 捕获时如果 content script 未注入，会尝试主动注入一次再重试。
- Web 构建新增 `vite.config.ts`：手动分包并过滤 Ant Design 的无害 `use client` 构建噪音。
- 已完成端到端验证：注册、登录、上传不同时间数据、按时间段查询、URL 关键字查询、详情、导出、删除。
- 已完成浏览器验证：登录、列表展示、详情抽屉、今天筛选、删除按钮布局。

最终校验：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
npm --prefix web-client audit
npm --prefix web-client run build
docker compose ps
curl http://0.0.0.0:3088/api/health
curl -I http://0.0.0.0:3090
```

当前结果：后端、数据库、Web 均为 healthy；前端 audit 为 0 vulnerabilities。

## 全流程真实拦截验证记录

已使用本地测试页完成模拟真实网页拦截：

- 测试页地址：`http://127.0.0.1:3103/page`
- 页面自动发起：
  - `fetch POST /api/fetch`
  - `XMLHttpRequest POST /api/xhr`
- 使用与插件相同的 `/chrome-extension/injected.js` 注入逻辑验证：
  - 成功捕获 `method`
  - 成功捕获绝对 URL
  - 成功捕获 request headers
  - 成功捕获 request body
  - 成功捕获 response status
  - 成功捕获 response body
  - 成功捕获 duration/timestamp

随后将捕获数据上传后端，并直接通过 PostgreSQL 验证：

```sql
select id,user_id,url,page_title,jsonb_array_length(xhr_data),parsed_summary,capture_time
from capture_records
where id = <record_id>;
```

验证结果：数据库中 `xhr_data` 数组长度正确，`parsed_summary.status_counts` 正确统计 `200`，requestBody/responseStatus 均正常入库。

PC Web 验证：

- 管理端列表能显示真实拦截记录。
- 时间段筛选正常。
- URL 关键字筛选后端正常。
- 详情抽屉能展示 HTML 快照和网络请求列表。
- 导出按钮显示“导出成功”，导出接口返回同条件数据。

本轮进一步修复：

- 插件捕获 URL 从相对路径优化为绝对 URL，便于后端管理端检索和导出。
- fetch 使用 `Request` 对象且 body 不在 `init.body` 时，尝试读取 `req.clone().text()` 作为 requestBody。

### 查询解析接口列表

`GET /api/apis/list?page=1&pageSize=20&urlKeyword=&method=POST&statusCode=200&startTime=&endTime=`

返回当前用户的接口调用列表。

### 导出解析接口

`GET /api/apis/export`

参数同 `/api/apis/list`，返回全部符合条件的接口记录 JSON，WebPC 会转换为 Excel。

### 接口详情

`GET /api/apis/{api_id}`

返回完整请求头、请求参数、请求体、响应头、响应体等。

## 自动拆解渠道/商品数据落表

现在后端不只保存原始捕获包和接口记录，还会在上传时自动尝试从每个接口的 JSON 响应里拆解业务数据，落到 `channel_product_records` 表。

执行链路：

1. 插件“停止并上报”调用 `POST /api/capture/upload`。
2. 后端先把每个 XHR/Fetch 拆成 `captured_apis` 一行。
3. 对每条接口的 `response_body` 调用 `/Users/admin/Documents/ChromeNetWork/backend/utils/channel_parser.py`。
4. 如果响应里能找到明确的商品/渠道列表字段，就按映射写入 `channel_product_records`。
5. 返回值里会带 `channelRecordCount`，表示本次自动拆解落表条数。

核心原则：**有字段就填，没有字段就保持空，不根据猜测乱填**。同时每条拆解记录会保留 `raw_item` 原始 JSON，方便后续追溯和补映射。

### 字段映射关系

| 页面字段 | 数据库列名 | 说明 |
|---|---|---|
| 平台用户 | `platform_user` | 来自 `平台用户/platformUser/userName` 等明确字段 |
| 用户id | `source_user_id` | 来自 `用户id/userId/uid` 等明确字段 |
| 平台 | `platform` | 淘宝/京东等平台字段 |
| 创建时间 | `source_created_at` | 接口原始创建时间，字符串保留 |
| 搜索词 | `search_keyword` | 搜索关键词 |
| 渠道标题 | `channel_title` | 商品/渠道标题 |
| 渠道链接 | `channel_url` | 商品/渠道详情链接 |
| skuId | `sku_id` | SKU ID |
| 价格 | `price` | 原样保存，不强转数字 |
| 销量 | `sales` | 原样保存 |
| 渠道图片 | `channel_image` | 图片 URL |
| 店铺名称 | `shop_name` | 店铺名 |
| 店铺ID | `shop_id` | 店铺 ID |
| 店铺链接 | `shop_url` | 店铺 URL |
| 广告标签 | `ad_tag` | 广告/推广标签 |
| 商品活动 | `product_activity` | 商品活动信息 |
| 优惠力度 | `discount_strength` | 优惠/券/折扣信息 |
| 平台细分 | `platform_category` | 平台类目/细分 |
| 商品信息 | `product_info` | 商品描述/信息 |
| 榜单信息 | `ranking_info` | 排名/榜单信息 |
| 发货地 | `ship_from` | 发货地 |
| 商品营销 | `product_marketing` | 商品营销信息 |
| 店铺营销 | `shop_marketing` | 店铺营销信息 |
| 货号 | `article_number` | 商品货号 |
| 序号 | `serial_number` | 序号 |
| 核心标签 | `core_tags` | 核心标签/标签数组会用逗号拼接 |
| 活动来源 | `activity_source` | 活动来源 |
| 频道页标 | `channel_page_title` | 频道页标/频道页标题 |
| 店铺标签 | `shop_tags` | 店铺标签 |
| 原始 item | `raw_item` | 原始 JSONB，完整保留 |

自动解析支持常见列表位置，例如：`data.list`、`data.items`、`records`、`rows`、`goodsList`、`itemList`、`products` 等。只有列表元素命中至少 2 个明确字段别名时才会落表，避免把普通配置 JSON 误当商品数据。

### 新增接口

#### 查询拆解后的渠道/商品数据

`GET /api/channel-records/list`

参数：

- `page`：页码，默认 1
- `pageSize`：每页数量，默认 20，最大 100
- `keyword`：模糊搜索标题、链接、搜索词、店铺名
- `skuId`：精确筛选 SKU
- `shopId`：精确筛选店铺 ID

#### 导出拆解后的渠道/商品数据

`GET /api/channel-records/export`

参数同 `/list`，返回最多 20000 条 JSON；WebPC 会导出为 Excel。

#### 查看拆解详情

`GET /api/channel-records/{record_id}`

返回字段映射结果和 `raw_item` 原始 JSON。

### WebPC 查看入口

PC 管理端左侧新增：**渠道商品数据**。

该页面展示的是 `channel_product_records` 表中的拆解结果，支持：

- 关键词查询
- skuId 查询
- 店铺ID 查询
- 详情查看
- Excel 导出

### 数据库验证 SQL

```bash
cd /Users/admin/Documents/ChromeNetWork
docker compose exec db psql -U webgrabber -d webgrabber
```

```sql
select id,user_id,platform,search_keyword,channel_title,sku_id,price,shop_name,created_at
from channel_product_records
order by id desc
limit 20;
```

### 本轮验证结果

已完成后端真实上传验证：

- 上传 1 个包含 `data.list` 商品数组的接口响应。
- `/api/capture/upload` 返回 `channelRecordCount: 1`。
- `/api/channel-records/list?keyword=pocket4` 可以查到拆解后的记录。
- 数据库 `channel_product_records` 中 `sku_id=SKU123` 正常入库。
- WebPC 构建成功，并已验证左侧“渠道商品数据”页面可打开、筛选栏和表格正常渲染。

校验命令：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
cd /Users/admin/Documents/ChromeNetWork/web-client && npm run build
cd /Users/admin/Documents/ChromeNetWork && docker compose up -d --build backend web
curl http://0.0.0.0:3088/api/health
```

## 渠道商品明细表筛选与个人数据隔离

WebPC 左侧 **渠道商品数据** 已升级为明细表筛选页。当前登录用户只能查询自己的 `channel_product_records` 数据，后端所有列表、导出、详情接口都会先执行：

```python
ChannelProductRecord.user_id == 当前JWT用户ID
```

所以即使前端传入别人的 `user_id/session_id/api_id`，也不会越权返回其他用户的数据。

### 明细表支持的筛选条件

通用条件：

- `keyword`：全局模糊搜索，覆盖平台用户、用户id、平台、搜索词、渠道标题、渠道链接、skuId、店铺名称、店铺ID、货号
- `startTime` / `endTime`：按本条拆解数据的入库时间 `created_at` 查询
- `skuId`
- `shopId`

字段条件：

| 前端筛选项 | API 参数 | 数据库列 |
|---|---|---|
| 平台用户 | `platformUser` | `platform_user` |
| 用户id | `sourceUserId` | `source_user_id` |
| 平台 | `platform` | `platform` |
| 创建时间 | `sourceCreatedAt` | `source_created_at` |
| 搜索词 | `searchKeyword` | `search_keyword` |
| 渠道标题 | `channelTitle` | `channel_title` |
| 渠道链接 | `channelUrl` | `channel_url` |
| skuId | `skuId` | `sku_id` |
| 价格 | `price` | `price` |
| 销量 | `sales` | `sales` |
| 渠道图片 | `channelImage` | `channel_image` |
| 店铺名称 | `shopName` | `shop_name` |
| 店铺ID | `shopId` | `shop_id` |
| 店铺链接 | `shopUrl` | `shop_url` |
| 广告标签 | `adTag` | `ad_tag` |
| 商品活动 | `productActivity` | `product_activity` |
| 优惠力度 | `discountStrength` | `discount_strength` |
| 平台细分 | `platformCategory` | `platform_category` |
| 商品信息 | `productInfo` | `product_info` |
| 榜单信息 | `rankingInfo` | `ranking_info` |
| 发货地 | `shipFrom` | `ship_from` |
| 商品营销 | `productMarketing` | `product_marketing` |
| 店铺营销 | `shopMarketing` | `shop_marketing` |
| 货号 | `articleNumber` | `article_number` |
| 序号 | `serialNumber` | `serial_number` |
| 核心标签 | `coreTags` | `core_tags` |
| 活动来源 | `activitySource` | `activity_source` |
| 频道页标 | `channelPageTitle` | `channel_page_title` |
| 店铺标签 | `shopTags` | `shop_tags` |

所有字段筛选目前使用模糊匹配，方便对接口返回的非标准文本做检索；导出 Excel 会复用当前筛选条件。

### 验证记录

已验证：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
npm --prefix web-client run build
docker compose up -d --build backend web
curl http://0.0.0.0:3088/api/health
```

接口验证：

- 使用拥有数据的用户按 `skuId=SKU123&platform=淘宝&searchKeyword=pocket4&shopId=shop123` 查询，返回 `total=1`。
- 使用另一个新用户携带自己的 JWT 查询同一个 `skuId=SKU123`，返回 `total=0`，确认个人数据隔离正常。
- WebPC 已打开并验证“渠道商品数据”页面、筛选区、字段筛选明细表渲染正常。

## 插件实时接口明细展示

插件侧边栏现在不是等“停止并上报”之后才展示接口，而是：

1. 点击 **开始记录** 后立即清空本次会话旧数据。
2. 插件每 1 秒从当前页面读取一次已捕获的 XHR/Fetch。
3. 每个新接口会实时显示在侧边栏 **实时接口明细** 区域。
4. 列表中展示：请求方法、接口 URL、状态码、耗时、请求体、响应体。
5. 点击单条接口可以展开查看 request body / response body。
6. 点击 **停止并上报** 时，只是停止记录并把当前列表提交后端。
7. 上报成功后清空实时列表；上报失败则保留当前列表，方便重试。

注意：实时列表只展示“开始记录之后新发起”的请求。开始前已经完成的接口不会回填；如果目标页已经加载完接口，需要点击开始记录后再触发搜索、翻页、筛选、点击等动作。

修改涉及文件：

- `/Users/admin/Documents/ChromeNetWork/chrome-extension/sidepanel.html`
- `/Users/admin/Documents/ChromeNetWork/chrome-extension/popup.js`
- `/Users/admin/Documents/ChromeNetWork/chrome-extension/content.js`
- `/Users/admin/Documents/ChromeNetWork/chrome-extension/popup.css`

验证命令：

```bash
node --check chrome-extension/popup.js
node --check chrome-extension/content.js
node --check chrome-extension/injected.js
```

更新插件后需要到 `chrome://extensions/` 点击本扩展的 **重新加载**，再打开目标网页刷新一次。

## 插件接口实时明细进一步优化：URL / Body / 搜索词 / Response

插件侧边栏的实时接口明细现在会按“接口粒度”展示并提交以下核心字段：

- `url`：接口完整 URL，包含 query 参数
- `method`：GET / POST / PUT / DELETE 等
- `requestHeaders`：请求头
- `requestBody`：提交的 body，支持 JSON、表单、URLSearchParams、FormData 摘要
- `searchKeyword`：插件尽量从接口和页面中提取的搜索词
- `responseStatus`：状态码
- `responseHeaders`：响应头
- `responseBody`：响应体文本，超出限制会截断
- `duration`：耗时 ms
- `timestamp`：接口发生时间

### 搜索词提取策略

插件会按优先级提取搜索词：

1. URL query：`keyword`、`keywords`、`search`、`search_word`、`searchKeyword`、`query`、`q`、`wd`、`term` 等。
2. Request Body JSON：递归查找上述字段。
3. Request Body 表单：解析 `application/x-www-form-urlencoded` 风格字段。
4. 页面输入框兜底：`input[type=search]`、`name*=keyword/search`、`placeholder*=搜索/关键词` 等。

提取到后，插件实时列表会显示：

```text
搜索词：xxx
URL：...
Request Body：...
Response：...
```

点击 **停止并上报** 后，`searchKeyword` 会随每条接口一起提交给后端。

### 后端搜索词入库

`captured_apis` 已新增字段：

```sql
search_keyword TEXT
```

后端也会再次兜底解析搜索词，来源包括：

- 插件提交的 `searchKeyword`
- URL query
- 解析后的 `request_params`
- 原始 request body JSON / 表单

WebPC 的 **接口数据管理** 页面已增加：

- 搜索词筛选框
- 表格“搜索词”列
- 导出 Excel 的“搜索词”列
- 接口详情中也会展示 `search_keyword`

### 业务明细表继承搜索词

如果接口响应拆解成 `channel_product_records` 时，响应 item 自身没有搜索词字段，但该接口请求里明确提取到了 `searchKeyword`，后端会把该搜索词填到业务明细表的：

```sql
channel_product_records.search_keyword
```

仍然遵守原则：

- 有明确搜索词才填
- 没有就空
- 不从标题/链接里臆造搜索词

### 验证记录

已完成验证：

- 插件脚本语法：`node --check chrome-extension/popup.js/content.js/injected.js` 通过。
- 后端编译：`python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py` 通过。
- WebPC 构建：`npm --prefix web-client run build` 通过。
- Docker 重建：`docker compose up -d --build backend web` 成功。
- 实际上传包含 `requestBody={"keyword":"运动鞋"}` 的接口后：
  - `/api/apis/list?searchKeyword=运动鞋` 返回 `search_keyword=运动鞋`。
  - `/api/channel-records/list?searchKeyword=运动鞋` 返回拆解后的商品明细，并继承 `search_keyword=运动鞋`。

## 接口过滤/解析规则：减少无用 URL，暴露 Response 解析配置

为了解决“无用 URL 接口太多”的问题，系统新增了 **接口过滤规则** 配套能力。

### WebPC 规则管理

WebPC 左侧新增：**过滤解析规则**。

可以配置：

- 规则名称
- 请求方法：GET / POST / PUT / DELETE，可为空表示所有方法
- URL 匹配方式：
  - `contains`：包含某段 URL
  - `equals`：完全等于
  - `regex`：正则匹配
- URL 匹配内容：例如 `/api/search-products`
- Params 过滤 JSON：例如

```json
{ "keyword": "鞋" }
```

表示 request params/body 中必须包含 `keyword` 且值里包含 `鞋`。

- Response 列表路径：例如

```text
payload.goods
```

表示从响应 JSON 的 `payload.goods` 数组中取列表。

- Response 字段映射 JSON：例如

```json
{
  "channel_title": "name",
  "channel_url": "link",
  "sku_id": "sku",
  "price": "price",
  "shop_name": "shop.name"
}
```

左边是数据库业务字段，右边是 response item 中的路径。支持点号路径。

### 插件如何使用规则

插件点击 **开始记录** 时会自动请求：

```text
GET /api/rules/list?enabledOnly=true
```

然后把规则注入当前页面捕获脚本。

- 如果当前账号没有启用规则：插件记录所有接口。
- 如果当前账号有启用规则：插件只记录命中 URL + Params 的接口。
- 未命中的接口不会进入实时列表，也不会上报后端。
- 插件顶部会显示过滤数量：`丢弃 x · 过滤 y`。
- 命中的接口实时明细中会显示：`规则：xxx`。

这样可以在源头减少无用接口。

### 后端如何使用规则解析 Response

上传后端后，每条接口会再次用当前用户启用规则匹配：

1. 匹配 method。
2. 匹配 URL。
3. 匹配 request params/body。
4. 命中后把 `matched_rule_id`、`matched_rule_name` 写入 `captured_apis`。
5. 优先用规则中的 `response_list_path` + `field_mapping` 拆解业务明细表。
6. 如果没有命中规则，才走原来的通用自动解析。

`captured_apis` 新增：

```sql
matched_rule_id INTEGER
matched_rule_name VARCHAR(255)
```

`capture_rules` 新增表：

```sql
id, user_id, name, enabled, method, url_pattern, url_match_type,
params_filter, response_list_path, field_mapping, remark, created_at
```

### 规则接口

```text
GET    /api/rules/list?enabledOnly=true
POST   /api/rules
PUT    /api/rules/{rule_id}
DELETE /api/rules/{rule_id}
```

所有规则都按当前 JWT 用户隔离；用户只能维护自己的规则。

### 验证记录

已验证：

- 新增规则：URL 包含 `/api/search-products`，Params 要求 `keyword` 包含 `鞋`。
- 上传命中接口后，`captured_apis` 写入 `matched_rule_name=商品搜索接口规则`。
- 使用规则 `response_list_path=payload.goods` 和字段映射成功解析：
  - `channel_title <- name`
  - `channel_url <- link`
  - `sku_id <- sku`
  - `price <- price`
  - `shop_name <- shop.name`
- `channel_product_records` 成功落表 `sku_id=RULESKU2`。

验证命令：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
node --check chrome-extension/popup.js
node --check chrome-extension/content.js
node --check chrome-extension/injected.js
npm --prefix web-client run build
docker compose up -d --build backend web
curl http://0.0.0.0:3088/api/health
```

## 规则权限模型调整：公共可用，创建者可编辑

规则现在不是按用户私有隔离使用，而是：

- **公共可读/可用**：所有登录用户都能加载全部启用规则。
- **创建者可编辑**：只有创建该规则的用户可以修改或删除。
- **数据仍个人隔离**：规则是公共的，但接口记录、业务明细数据仍按上传用户自己的 `user_id` 隔离。

### 行为说明

插件开始记录时：

```text
GET /api/rules/list?enabledOnly=true
```

会返回全部公共启用规则。也就是说，A 创建的规则，B 的插件也会加载并用于过滤接口。

但编辑/删除时后端会校验：

```text
rule.user_id == 当前 JWT 用户 ID
```

否则返回：

```text
403 Only creator can edit/delete this rule
```

WebPC 规则表会显示：

- 创建人手机号
- 当前用户是否可编辑
- 非创建者显示“无权限”

### 验证记录

已验证：

- 用户 A 创建规则。
- 用户 B 调用 `/api/rules/list?enabledOnly=true` 可以看到该公共规则。
- 用户 B 删除该规则返回 `403`。
- 后端、WebPC 构建和健康检查均通过。

## 规则选择模型：公共规则池 + 用户自行打勾启用

规则现在是三层模型：

1. **公共规则池**：所有登录用户都能看到所有公共规则。
2. **创建者维护**：只有规则创建者能编辑/删除该规则。
3. **个人勾选启用**：每个用户自己选择哪些公共规则对自己的插件生效。

也就是说：

```text
用户 A 创建规则 R
用户 B/C/D 都能在 WebPC 看到规则 R
用户 B/C/D 需要自己打√勾选规则 R
只有勾选后，插件开始记录时才会加载规则 R
```

### WebPC 使用方式

进入左侧：**过滤解析规则**。

规则列表第一列为：

```text
启用到我的插件
```

打开开关后，该规则才会对当前登录用户的插件生效。

### 插件加载规则

插件开始记录时请求：

```text
GET /api/rules/list?enabledOnly=true&selectedOnly=true
```

因此插件只会加载：

- 公共启用规则
- 当前登录用户已打√选择的规则

如果当前用户没有勾选任何规则，插件会记录所有接口；如果勾选了规则，插件只记录命中这些规则的接口。

### 权限说明

- 看规则：所有登录用户都可以。
- 勾选规则：每个用户都可以给自己勾选/取消勾选。
- 编辑/删除规则：只有创建者可以。
- 查询接口数据/业务明细：仍然只能看自己的数据。

### 新增关系表

```sql
user_rule_selections(user_id, rule_id)
```

用于记录每个用户勾选了哪些公共规则。

### 验证记录

已验证：

- 用户 A 创建规则后，用户 B 能在公共规则列表看到。
- 用户 B 初始 `selected=false`，`can_edit=false`。
- 用户 B 未勾选时，`selectedOnly=true` 不返回该规则。
- 用户 B 调用勾选接口后，`selectedOnly=true` 返回该规则。
- 用户 B 仍然不能编辑/删除用户 A 创建的规则。

## 标签体系：一个接口只能对应一个标签

新增 **标签** 能力，用来把不同规则命中的接口分到不同业务数据域。

### 核心关系

```text
标签 Label
  └── 规则 Rule 绑定一个标签
        └── 接口命中该规则后，只归属这个标签
              ├── captured_apis.label_id / label_name
              └── channel_product_records.label_id / label_name
```

也就是说：

- 用户可以自己创建标签。
- 每条规则最多绑定一个标签。
- 每个接口命中一条规则后，只会对应一个标签。
- 标签会同步写入接口表和业务明细表。

### 新增表

```sql
data_labels(
  id,
  user_id,
  creator_phone,
  name,
  table_name,
  remark,
  created_at
)
```

`table_name` 是该标签对应的业务表标识。当前实现为了避免动态建表和迁移风险，物理数据仍统一落在：

```text
captured_apis
channel_product_records
```

并通过：

```text
label_id
label_name
```

区分“相应标签的数据表”。如果后续确定每个标签都要创建真实物理表，可以基于 `data_labels.table_name` 再做动态建表/同步写入。

### 新增接口

```text
GET    /api/labels/list
POST   /api/labels
DELETE /api/labels/{label_id}
```

标签公共可见，只有创建者可以删除。

### 规则绑定标签

创建/编辑规则时增加：

```json
{
  "label_id": 1
}
```

命中该规则后，后端会写入：

```sql
captured_apis.label_id
captured_apis.label_name
channel_product_records.label_id
channel_product_records.label_name
```

### WebPC

在 **过滤解析规则** 页面增加：

- 创建标签
- 规则绑定标签
- 规则列表展示标签

在接口数据管理和渠道商品数据表格中展示“标签”列。

### 验证记录

已验证：

- 创建标签：`商品标签`。
- 创建规则并绑定该标签。
- 上传命中接口后：
  - `captured_apis.label_name = 商品标签`
  - `channel_product_records.label_name = 商品标签`
  - `channel_product_records.sku_id = LABELSKU`
- 后端编译、Web 构建、Docker 重建和健康检查均通过。

## 动态标签数据表：字段来自规则拆出的字段

进一步调整后，标签对应的“表字段”不再固定使用 `channel_product_records` 那套字段，而是完全来自规则里的 `field_mapping`。

### 核心变化

新增动态明细表：

```sql
label_data_records(
  id,
  user_id,
  session_id,
  api_id,
  label_id,
  label_name,
  rule_id,
  rule_name,
  row_data JSONB,
  raw_item JSONB,
  created_at
)
```

其中：

```text
row_data
```

就是规则拆出来的动态字段。

### 举例

规则配置：

```json
{
  "response_list_path": "data.items",
  "field_mapping": {
    "商品名": "title",
    "SKU": "sku",
    "价格": "price",
    "店铺": "shop.name",
    "自定义字段X": "extra.x"
  }
}
```

接口响应：

```json
{
  "data": {
    "items": [
      {
        "title": "动态商品",
        "sku": "DYN1",
        "price": "888",
        "shop": { "name": "动态店" },
        "extra": { "x": "abc" }
      }
    ]
  }
}
```

落到 `label_data_records.row_data`：

```json
{
  "商品名": "动态商品",
  "SKU": "DYN1",
  "价格": "888",
  "店铺": "动态店",
  "自定义字段X": "abc"
}
```

也就是说：

```text
规则 field_mapping 的 key 是什么，标签数据表就展示什么字段。
```

### WebPC 动态表

WebPC 左侧新增：

```text
标签数据表
```

使用方式：

1. 选择标签表。
2. 后端返回该标签下数据的动态 columns。
3. 前端按 columns 动态渲染表格。
4. 支持全字段关键词搜索。

### 与旧固定表的关系

当前仍保留：

```text
channel_product_records
```

用于兼容之前固定字段的渠道商品展示。

新的动态标签数据以：

```text
label_data_records
```

为准，更符合“表字段就是规则拆出的字段”的需求。

### 验证记录

已验证：

- 创建标签：`动态商品表`。
- 创建规则绑定该标签。
- 规则映射字段：`商品名/SKU/价格/店铺/自定义字段X`。
- 上传命中接口后返回：`labelRecordCount=1`。
- `/api/label-data/list?labelId=<id>` 返回动态列：
  - `SKU`
  - `价格`
  - `店铺`
  - `商品名`
  - `自定义字段X`
- `row_data` 正确保存规则拆出的字段。

## 本轮质量优化记录（2026-06-04）

### 1. WebPC 构建现在会先做 TypeScript 类型检查

`web-client/package.json` 的 `build` 已调整为：

```bash
tsc --noEmit && vite build
```

原因：Vite 生产构建默认只转译，不一定拦截所有 TypeScript 逻辑错误。本轮发现“标签数据导出”里存在运行时变量引用错误，已修复，并通过 `typecheck` 在构建阶段兜底。

常用检查命令：

```bash
npm --prefix web-client run typecheck
npm --prefix web-client run build
npm --prefix web-client audit
```

### 2. 标签数据导出修复与文件名优化

- 修复“标签数据表 -> 导出当前筛选”点击时报错的问题。
- 导出文件名改为带业务名和时间戳，例如：`淘宝商品列表_20260604_214500.xls`。
- 接口数据、渠道商品数据导出也加入时间戳，避免多次下载覆盖或不好区分。

### 3. 搜索词自动解析增强

后端现在会递归解析以下嵌套结构中的搜索词：

- URL query 中的普通 `keyword/q/query/search` 等字段。
- URL query 中的 JSON 字符串字段，例如淘宝 `data={...}`。
- JSON 字段里再次嵌套的 JSON 字符串，例如 `data.params="{\"keyword\":\"大疆\"}"`。
- request body JSON / 表单字符串。

这能更好适配淘宝、JSONP、h5api 这类接口，把 `search_keyword` 自动落到 `parsed_apis` 和标签数据表里。

### 4. Params 过滤支持嵌套路径

规则的 `params_filter` 现在前后端保持一致，支持嵌套路径，例如：

```json
{
  "data.params.keyword": "大疆"
}
```

匹配逻辑：字段不存在则不命中；字段存在且配置值不为空时，使用字符串包含匹配。没有值或 `{}` 表示不限制 params。

### 5. 本轮回归验证

已验证：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
npm --prefix web-client run typecheck
npm --prefix web-client run build
npm --prefix web-client audit
node --check chrome-extension/popup.js
node --check chrome-extension/injected.js
node --check chrome-extension/content.js
node --check chrome-extension/background.js
curl http://0.0.0.0:3088/api/health
curl http://0.0.0.0:3090/health
```

并做了一次模拟淘宝 JSONP 上传回归：

- `/api/capture/upload` 返回成功。
- `parsed_apis` 正确生成 1 条接口记录。
- 命中规则 `淘宝商品列表`。
- `label_data_records` 正确拆出：`店铺名称 / 商品id / 销量 / search_keyword`。
- `search_keyword` 从嵌套 `data.params.keyword` 中成功解析。

## 本轮体验优化记录（2026-06-04 晚）

### 1. 标签数据表自动加载默认标签

进入 **标签数据表** 页面时，如果当前账号存在标签，会自动选中第一个标签并加载数据，不再默认展示空表。

优化前：用户进入页面后需要手动选择标签，否则容易误以为没有数据。  
优化后：进入页面即可看到默认标签的数据、动态字段筛选和当前总数。

### 2. WebPC 表格与筛选区域防溢出

补充了 UI overflow hardening：

- 页面主体不再被超宽表格撑出横向布局。
- 规则页的双列表单在窄屏下自动变单列。
- URL 输入框、动态字段筛选、规则表格都限制在卡片内滚动/省略。

这主要改善 1280px 左右宽度下规则页、标签页的可读性。

### 3. 修复动态字段筛选按钮文字颜色

之前 `.dynamic-filter-grid span` 选择器范围过大，误伤 Ant Design Button 内部 `span`，导致“查询字段”按钮文字接近不可见。现在只作用于字段 label：

```css
.dynamic-filter-grid label>span { ... }
```

### 4. 插件后台日志收敛

移除了 `chrome-extension/background.js` 中安装时的 `console.log`，让扩展 service worker 控制台更干净。

### 5. 本轮验证

已验证：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
npm --prefix web-client run typecheck
npm --prefix web-client run build
npm --prefix web-client audit
node --check chrome-extension/popup.js
node --check chrome-extension/injected.js
node --check chrome-extension/content.js
node --check chrome-extension/background.js
docker compose ps
curl http://0.0.0.0:3088/api/health
curl http://0.0.0.0:3090/health
```

同时使用浏览器回归查看了：

- 标签数据表：自动加载 `淘宝商品列表`，展示 99 条数据。
- 动态字段筛选按钮：文字恢复白色，可读。
- 表格布局：字段列单行省略，页面未被撑坏。

## 本轮查询体验与插件状态优化（2026-06-04 深夜）

### 1. 修复分页重复请求导致的闪烁

接口数据管理、渠道商品数据的分页切换之前会触发两次请求：

- `Pagination.onChange` 手动调用一次加载。
- `useEffect([page,pageSize])` 又自动加载一次。

现在分页只更新页码和 pageSize，由 `useEffect` 统一加载，减少表格闪烁和重复接口请求。

### 2. 标签数据表增加时间段筛选

`/api/label-data/list` 和 `/api/label-data/export` 新增：

```text
startTime
endTime
```

WebPC 的 **标签数据表** 已加入：

- 入库时间范围选择器
- 今天
- 最近 7 天
- 重置
- 导出当前筛选时同步带上时间范围

适合数据量变大后按采集日期快速缩小范围。

### 3. 插件记录状态更透明

插件实时状态现在显示：

```text
命中 N · 过滤 M · 丢弃 K
```

并且开始记录后会展示本次加载的规则名称，方便判断“为什么有些接口没被记录”：

- 有规则时：只记录命中规则的接口。
- 无规则时：记录全部接口。

### 4. 复制空内容提示优化

WebPC 详情页复制按钮现在对 `null/undefined` 内容会提示“没有可复制的内容”，避免复制空字符串后用户误以为按钮无效。

### 5. 本轮验证

已验证：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
npm --prefix web-client run typecheck
npm --prefix web-client run build
npm --prefix web-client audit
node --check chrome-extension/popup.js
node --check chrome-extension/injected.js
node --check chrome-extension/content.js
node --check chrome-extension/background.js
curl http://0.0.0.0:3088/api/health
curl http://0.0.0.0:3090/health
```

标签数据时间筛选回归：

- `2026-06-04` 当天返回 99 条。
- `2026-01-01` 返回 0 条。
- WebPC 标签数据表可正常显示时间范围筛选与动态字段筛选。

## 本轮标签明细可追溯优化（2026-06-04 深夜追加）

### 1. 标签数据支持单条详情

新增后端接口：

```http
GET /api/label-data/{record_id}
Authorization: Bearer <token>
```

返回当前登录用户自己的标签明细记录，包含：

- `row_data`：规则拆出的动态字段
- `raw_item`：原始响应 item
- `api_id` / `session_id`：可追溯回原接口和采集会话
- `label_name` / `rule_name`：来源标签与规则

接口强制按当前 JWT 用户隔离，不能查看其他用户数据。

### 2. WebPC 标签数据表增加“详情”按钮

**标签数据表** 每行现在有“详情”操作，打开抽屉后可查看：

- 字段数据：动态字段卡片化展示
- 原始 item：完整原始 JSON
- 元信息：标签、规则、API、会话、入库时间

同时提供：

- 复制字段 JSON
- 复制原始 item
- 查看原接口

这让规则调试更顺：看到某行字段异常时，可以直接追到原始接口响应，不需要导出或查库。

### 3. 构建说明

本机 `vite build` 如果遇到 `Killed: 9`，通常是 macOS 当前内存压力过高。本轮观察到 `mds_stores` 占用大量内存。已使用 Docker 构建完成：

```bash
docker compose up -d --build backend web
```

Docker 内部构建已通过 `tsc --noEmit && vite build`。

### 4. 本轮验证

已验证：

```bash
python3 -m py_compile backend/*.py backend/routes/*.py backend/utils/*.py
npm --prefix web-client run typecheck
npm --prefix web-client audit
node --check chrome-extension/popup.js
node --check chrome-extension/injected.js
node --check chrome-extension/content.js
node --check chrome-extension/background.js
curl http://0.0.0.0:3088/api/health
curl http://0.0.0.0:3090/health
```

浏览器回归：

- 标签数据表每行出现“详情”。
- 详情抽屉展示字段数据、原始 item、元信息。
- “查看原接口”按钮可以继续打开接口详情抽屉。


### 2026-06-04 继续优化记录

- WebPC 规则池新增「测试」按钮：可直接拿当前账号最近捕获样本验证 URL / Method / Params / 列表路径 / 字段映射，并预览解析出的动态字段，避免规则写完后只能盲猜。
- 插件侧边栏「实时接口明细」新增本地搜索框和 2xx / 4xx-5xx / 慢接口计数，接口多时可以快速定位 URL、body、response、搜索词。
- WebPC 将 `rollup` 显式别名到 `@rollup/wasm-node`，规避 macOS / Codex Node 24 下 Rollup native 包签名异常；`./scripts/fix-rollup-macos.sh` 可一键恢复本机构建。


## Chrome Debugger Network 捕获模式

关于“为什么会出现 xxx 正在调试此网页”：

- 当前插件已默认使用 `chrome.debugger` + Chrome DevTools Protocol 的 **Network 调试模式**。
- 点击“开始记录”后，Chrome 会显示类似“API Capture 正在调试此网页”的提示，这是正常现象。
- Network 模式会监听 `Network.requestWillBeSent`、`requestWillBeSentExtraInfo`、`responseReceived`、`responseReceivedExtraInfo`、`loadingFinished` 等事件。
- 相比页面注入模式，它能拿到更完整的请求头、请求体、响应头、响应体，包括更多浏览器实际发出的 header。
- 如果 `chrome.debugger` 启动失败，插件会自动回退到页面注入模式，但该模式拿不到浏览器自动附加的所有请求头。
- 停止并上报后，插件会自动 detach 调试连接，提示条会消失。


## Network 级请求头/请求体捕获说明

当前插件优先使用 Chrome Debugger / CDP Network 捕获：

- 请求头：保存到 `captured_apis.request_headers`。
- 请求体：保存到 `captured_apis.request_body_raw`。
- 响应头：保存到 `captured_apis.response_headers`。
- 响应体：保存到 `captured_apis.response_body_raw`，如果是 JSON 也会解析到 `response_body`。

注意：

- `request_params` 为了列表展示和筛选仍可能做脱敏摘要。
- 原始字段 `request_body_raw` / `response_body_raw` / `request_headers` / `response_headers` 会尽量原样保存。
- 某些浏览器/站点安全限制下，极少数响应体可能无法通过 `Network.getResponseBody` 读取，插件会以 `[response body unavailable]` 标记。
- 更新插件代码后必须到 `chrome://extensions/` 点击本扩展的“重新加载”。
