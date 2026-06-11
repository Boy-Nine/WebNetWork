# 部署与使用指南

本文档说明：在另一台电脑拉取本项目后，如何快速启动 WebPC、后端、PostgreSQL 数据库和 Chrome 插件。

## 1. 环境准备

推荐使用 Docker 部署，避免本机 Python / Node / PostgreSQL 版本差异。

需要安装：

- Git
- Docker Desktop / Docker Engine
- Chrome 浏览器

检查 Docker 是否可用：

```bash
docker --version
docker compose version
```

## 2. 拉取代码

```bash
git clone https://github.com/Boy-Nine/WebNetWork.git
cd WebNetWork
```

如果已经拉取过：

```bash
git pull origin main
```

## 3. 配置后端环境变量

新建后端 `.env`：

```bash
cp backend/.env.example backend/.env 2>/dev/null || touch backend/.env
```

最小可运行配置：

```env
DATABASE_URL=postgresql+psycopg2://webgrabber:webgrabber@db:5432/webgrabber
JWT_SECRET_KEY=please-change-this-secret-at-least-32-bytes
JWT_EXPIRE_MINUTES=10080
CORS_ORIGINS=*

# 不测试微信支付时可以先关闭
WECHAT_PAY_ENABLED=false
```

如果要启用微信支付：

```env
WECHAT_PAY_ENABLED=true
WECHAT_PAY_MERCHANT_ID=你的商户号
WECHAT_PAY_API_KEY_V3=你的32字节APIv3密钥
WECHAT_PAY_APP_ID=你的AppID
WECHAT_PAY_NOTIFY_URL=http://localhost:3088/api/membership/wechat/notify
WECHAT_PAY_CERT_PATH=/app/backend/certs/apiclient_cert.pem
WECHAT_PAY_KEY_PATH=/app/backend/certs/apiclient_key.pem
WECHAT_PAY_MCH_SERIAL_NO=
WECHAT_PAY_PLATFORM_CERT_PATH=
WECHAT_PAY_VERIFY_NOTIFY_SIGNATURE=false
```

> `backend/.env` 已被 `.gitignore` 排除，不要提交到 Git。

## 4. 放置微信支付证书（可选）

如果启用微信支付，需要创建目录：

```bash
mkdir -p backend/certs
```

然后把证书放入：

```text
backend/certs/apiclient_cert.pem  # 微信支付商户 API 证书
backend/certs/apiclient_key.pem   # 微信支付商户 API 私钥，严禁公开
```

Docker 容器内对应路径是：

```text
/app/backend/certs/apiclient_cert.pem
/app/backend/certs/apiclient_key.pem
```

注意：

- `apiclient_key.pem` 是商户私钥，不能上传 GitHub。
- `backend/certs/*.pem` 已被 `.gitignore` 排除。
- 线上部署建议使用服务器密钥目录、Docker Secret、K8s Secret 或 CI/CD Secret 注入。

## 5. 启动服务

```bash
docker compose up -d --build
```

查看状态：

```bash
docker compose ps
```

正常情况下会有：

- `db`：PostgreSQL
- `backend`：FastAPI 后端
- `web`：WebPC 前端

访问地址：

```text
WebPC:   http://localhost:3090
Backend: http://localhost:3088
Health:  http://localhost:3088/api/health
```

## 6. 注册/登录 WebPC

打开：

```text
http://localhost:3090
```

注册账号或使用已有账号登录。

## 7. 安装 Chrome 插件

Chrome 打开：

```text
chrome://extensions
```

然后：

1. 开启右上角「开发者模式」
2. 点击「加载已解压的扩展程序」
3. 选择项目目录下的：

```text
chrome-extension
```

插件默认读取：

```js
window.WEB_CAPTURE_CONFIG = {
  API_BASE: 'http://0.0.0.0:3088',
  WEB_BASE: 'http://0.0.0.0:3090'
};
```

如果另一台电脑的地址不同，修改：

```text
chrome-extension/config.js
```

例如：

```js
window.WEB_CAPTURE_CONFIG = {
  API_BASE: 'http://localhost:3088',
  WEB_BASE: 'http://localhost:3090'
};
```

修改后需要在 `chrome://extensions` 点击插件「重新加载」。

## 8. 微信支付本地联调说明

本地开发时，如果：

```env
WECHAT_PAY_NOTIFY_URL=http://localhost:3088/api/membership/wechat/notify
```

微信服务器无法访问你的本机 `localhost`，所以回调不会自动进来。

项目已经做了兜底：

- WebPC 订单列表刷新会主动查微信订单状态。
- 支付弹窗「我已支付，刷新状态」会主动查单。
- 插件会员刷新会先同步订单，再刷新会员信息。

如果要测试微信真实回调，请使用 ngrok / frp / Cloudflare Tunnel 等内网穿透，配置公网 HTTPS 地址：

```env
WECHAT_PAY_NOTIFY_URL=https://你的域名/api/membership/wechat/notify
```

生产环境建议开启微信支付平台证书验签：

```env
WECHAT_PAY_PLATFORM_CERT_PATH=/app/backend/certs/wechatpay_platform_cert.pem
WECHAT_PAY_VERIFY_NOTIFY_SIGNATURE=true
```

## 9. 常用运维命令

查看服务：

```bash
docker compose ps
```

查看后端日志：

```bash
docker compose logs -f backend
```

查看前端日志：

```bash
docker compose logs -f web
```

重启服务：

```bash
docker compose restart
```

重新构建并启动：

```bash
docker compose up -d --build
```

停止服务：

```bash
docker compose down
```

清空数据库并重建：

```bash
docker compose down -v
docker compose up -d --build
```

## 10. 数据库说明

当前默认数据库是 PostgreSQL，不是 MySQL，也不是 SQLite。

Docker Compose 默认配置：

```text
POSTGRES_DB=webgrabber
POSTGRES_USER=webgrabber
POSTGRES_PASSWORD=webgrabber
```

后端连接串：

```env
DATABASE_URL=postgresql+psycopg2://webgrabber:webgrabber@db:5432/webgrabber
```

如需进入数据库：

```bash
docker compose exec db psql -U webgrabber -d webgrabber
```

## 11. 更新代码后的操作

拉取最新代码：

```bash
git pull origin main
```

重新构建：

```bash
docker compose up -d --build
```

如果更新了插件文件：

1. 打开 `chrome://extensions`
2. 找到 `API Capture`
3. 点击「重新加载」
4. 重新打开插件侧边栏
